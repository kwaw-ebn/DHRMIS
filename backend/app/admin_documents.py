"""Private administrative document register, distinct from personnel files."""
import hashlib, io, os, re, zipfile, zlib
from datetime import date, datetime
from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from sqlalchemy import Boolean, Date, DateTime, ForeignKey, Integer, String, Text, or_
from sqlalchemy.orm import Mapped, Session, mapped_column, aliased
from pydantic import BaseModel, ConfigDict, Field
from .db import Base, get_db
from .models import Unit, User, uid, now
from .security import current_user, allow, audit, descendants, HR, SCOPED
from .phase2 import storage_client, bucket
from .roster_uploads import normalize, Archive, MAX_BYTES

CATEGORIES=['Meeting minutes','Incoming letter','Outgoing letter','Memo','Circular','Report','Policy / guideline','Other']
MANAGERS=HR
READERS=MANAGERS|SCOPED|{'director'}
class AdminDocument(Base):
    __tablename__='administrative_documents'
    id:Mapped[str]=mapped_column(String(36),primary_key=True,default=uid)
    unit_id:Mapped[str]=mapped_column(ForeignKey('organization_units.id'),index=True)
    title:Mapped[str]=mapped_column(String(180))
    category:Mapped[str]=mapped_column(String(40),index=True)
    filing_number:Mapped[str|None]=mapped_column(String(80),unique=True,index=True)
    reference:Mapped[str]=mapped_column(String(150),default='')
    document_date:Mapped[date]=mapped_column(Date,index=True)
    registered_date:Mapped[date]=mapped_column(Date)
    sender:Mapped[str]=mapped_column(String(180),default='')
    recipient:Mapped[str]=mapped_column(String(180),default='')
    notes:Mapped[str]=mapped_column(Text,default='')
    visibility:Mapped[str]=mapped_column(String(30),default='hr_only')
    object_key:Mapped[str]=mapped_column(String(300),unique=True)
    filename:Mapped[str]=mapped_column(String(180))
    content_type:Mapped[str]=mapped_column(String(120))
    size:Mapped[int]=mapped_column(Integer)
    checksum:Mapped[str]=mapped_column(String(64))
    uploaded_by:Mapped[str]=mapped_column(ForeignKey('users.id'))
    created_at:Mapped[datetime]=mapped_column(DateTime(timezone=True),default=now)
    archived:Mapped[bool]=mapped_column(Boolean,default=False)
    version:Mapped[int]=mapped_column(Integer,default=1)
router=APIRouter(prefix='/api/admin-documents',tags=['Administrative document register'])

def filing_code(value):
    value=' '.join(value.strip().upper().split())
    if not re.fullmatch(r'[A-Z0-9][A-Z0-9 /_.-]{0,79}',value):raise HTTPException(400,'Enter a filing number of 1–80 letters, digits, spaces, /, _, . or -')
    return value

def hr_office(db):
    parent=aliased(Unit)
    rows=db.query(Unit).join(parent,Unit.parent_id==parent.id).filter(Unit.active==True,Unit.kind=='department',Unit.name=='Human Resources and Administration',parent.active==True,parent.category=='DHD').all()
    if len(rows)!=1:raise HTTPException(409,'One active HR department under DHD must be configured')
    return rows[0]

class FilingRegistration(BaseModel):
    model_config=ConfigDict(extra='forbid')
    filing_number:str=Field(min_length=1,max_length=80)
    version:int=Field(ge=1)

def units_query(db,user):
    allow(user,READERS)
    q=db.query(Unit).filter(Unit.active==True,Unit.kind.in_(['district','subdistrict','facility','department']))
    if user.role in SCOPED:q=q.filter(Unit.id.in_(descendants(db,user.unit_id)))
    return q

def documents_query(db,user):
    q=db.query(AdminDocument).filter(AdminDocument.archived==False,AdminDocument.unit_id.in_(units_query(db,user).with_entities(Unit.id)))
    if user.role in SCOPED:q=q.filter(or_(AdminDocument.visibility=='unit_management',AdminDocument.uploaded_by==user.id))
    return q

def visible(db,user,did,lock=False):
    q=documents_query(db,user).filter(AdminDocument.id==did)
    if lock:q=q.with_for_update().populate_existing()
    row=q.first()
    if not row:raise HTTPException(404,'Document not found in your scope')
    return row

def view(db,user,row):
    return {k:getattr(row,k) for k in ['id','unit_id','title','category','filing_number','reference','document_date','registered_date','sender','recipient','notes','visibility','filename','content_type','size','created_at','version']}|{'unit_name':db.get(Unit,row.unit_id).name,'uploaded_by_name':db.get(User,row.uploaded_by).name,'can_archive':user.role in HR}

def office_content(raw):
    if not raw.startswith(b'PK\x03\x04'):return normalize(raw)
    try:
        with zipfile.ZipFile(io.BytesIO(raw)) as archive:
            entries=archive.infolist();names={i.filename for i in entries}
            if len(entries)>2000 or sum(i.file_size for i in entries)>50*1024*1024 or any(i.flag_bits&1 for i in entries):raise HTTPException(400,'Upload an unencrypted DOCX/XLSX file with expanded size under 50 MB')
            if len(names)!=len(entries) or '[Content_Types].xml' not in names or archive.getinfo('[Content_Types].xml').file_size>1024*1024:raise HTTPException(400,'Invalid Office document package')
            if archive.testzip() is not None:raise HTTPException(400,'Office document is damaged')
            types=archive.read('[Content_Types].xml').lower()
            if b'macroenabled' in types or any('vbaproject' in n.lower() for n in names):raise HTTPException(400,'Macro-enabled Office files are not supported. Export a PDF copy.')
            word='word/document.xml' in names and b'wordprocessingml.document.main+xml' in types
            excel='xl/workbook.xml' in names and b'spreadsheetml.sheet.main+xml' in types
            if word and not excel:return raw,'application/vnd.openxmlformats-officedocument.wordprocessingml.document','.docx'
            if excel and not word:return raw,'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet','.xlsx'
    except HTTPException:raise
    except (zipfile.BadZipFile,RuntimeError,ValueError,OSError,NotImplementedError,zlib.error):raise HTTPException(400,'Upload a valid DOCX or XLSX file')
    raise HTTPException(400,'Supported files: PDF, JPEG, PNG, DOCX or XLSX')

@router.get('')
def documents(filing_number:str=Query('',max_length=80),q:str=Query('',max_length=180),category:str='',unit_id:str='',start:date|None=None,end:date|None=None,page:int=Query(1,ge=1),page_size:int=Query(20,ge=1,le=100),db:Session=Depends(get_db),user:User=Depends(current_user)):
    if category and category not in CATEGORIES:raise HTTPException(400,'Choose a valid document category')
    if start and end and end<start:raise HTTPException(400,'End date cannot precede start date')
    query=documents_query(db,user)
    if category:query=query.filter(AdminDocument.category==category)
    if unit_id:query=query.filter(AdminDocument.unit_id==unit_id)
    if start:query=query.filter(AdminDocument.document_date>=start)
    if end:query=query.filter(AdminDocument.document_date<=end)
    if q:raise HTTPException(400,'Use the filing-number lookup')
    if filing_number:query=query.filter(AdminDocument.filing_number==filing_code(filing_number))
    total=query.count();rows=query.order_by(AdminDocument.document_date.desc(),AdminDocument.created_at.desc(),AdminDocument.id).offset((page-1)*page_size).limit(page_size).all()
    audit(db,user,'ADMIN_DOCUMENTS_READ');db.commit()
    return {'items':[view(db,user,r) for r in rows],'total':total,'categories':CATEGORIES}

@router.post('',status_code=201)
async def upload(filing_number:str=Form(...),unit_id:str=Form(''),title:str=Form(...),category:str=Form(...),document_date:date=Form(...),registered_date:date=Form(...),reference:str=Form(''),sender:str=Form(''),recipient:str=Form(''),notes:str=Form(''),visibility:str=Form('hr_only'),file:UploadFile=File(...),db:Session=Depends(get_db),user:User=Depends(current_user)):
    allow(user,MANAGERS)
    unit=hr_office(db)
    if unit_id and unit_id!=unit.id:raise HTTPException(400,'Administrative documents must be filed under HR')
    db.query(Unit).filter(Unit.id==unit.id).with_for_update().populate_existing().one()
    filing_number=filing_code(filing_number)
    if db.query(AdminDocument).filter(AdminDocument.filing_number==filing_number).first():raise HTTPException(409,'This filing number is already registered, including archived documents')
    if not 3<=len(title.strip())<=180 or category not in CATEGORIES or visibility not in {'hr_only','unit_management'}:raise HTTPException(400,'Choose a valid title, category and access level')
    if len(reference)>150 or len(sender)>180 or len(recipient)>180 or len(notes)>2000:raise HTTPException(400,'Document details exceed the allowed length')
    if category=='Incoming letter' and not sender.strip():raise HTTPException(400,'Enter the sender of the incoming letter')
    if category=='Outgoing letter' and not recipient.strip():raise HTTPException(400,'Enter the recipient of the outgoing letter')
    raw=await file.read(MAX_BYTES+1)
    if not raw or len(raw)>MAX_BYTES:raise HTTPException(413,'Upload a non-empty file up to 10 MB')
    content,mime,ext=office_content(raw);checksum=hashlib.sha256(content).hexdigest()
    if db.query(AdminDocument).filter_by(unit_id=unit.id,category=category,document_date=document_date,checksum=checksum,archived=False).first():raise HTTPException(409,'This document is already filed for this unit, category and date')
    filename=re.sub(r'[^A-Za-z0-9._-]','_',os.path.basename(file.filename or 'document'))[:150]
    if not filename.lower().endswith(ext):filename='administrative-document'+ext
    key='administration/'+uid()+ext
    row=AdminDocument(filing_number=filing_number,unit_id=unit.id,title=title.strip(),category=category,document_date=document_date,registered_date=registered_date,reference=reference.strip(),sender=sender.strip(),recipient=recipient.strip(),notes=notes.strip(),visibility=visibility,object_key=key,filename=filename,content_type=mime,size=len(content),checksum=checksum,uploaded_by=user.id)
    client=storage_client()
    try:client.put_object(Bucket=bucket(),Key=key,Body=content,ContentType=mime,CacheControl='private, no-store')
    except Exception:raise HTTPException(503,'Private storage upload failed. Retry later.')
    try:
        db.add(row);db.flush();audit(db,user,'ADMIN_DOCUMENT_UPLOADED',row.id,detail=category);db.commit()
    except Exception:
        db.rollback()
        try:client.delete_object(Bucket=bucket(),Key=key)
        except Exception:pass
        raise
    return view(db,user,row)

@router.patch('/{did}/filing-number')
def register_filing(did:str,data:FilingRegistration,db:Session=Depends(get_db),user:User=Depends(current_user)):
    allow(user,HR);row=visible(db,user,did,lock=True)
    if row.version!=data.version:raise HTTPException(409,'Document changed; reload before registering')
    if row.filing_number:raise HTTPException(409,'The filing number is permanent and already registered')
    code=filing_code(data.filing_number)
    if db.query(AdminDocument).filter(AdminDocument.filing_number==code).first():raise HTTPException(409,'This filing number is already registered')
    row.filing_number=code;row.version+=1;audit(db,user,'DOCUMENT_FILING_REGISTERED',row.id);db.commit();return view(db,user,row)

@router.get('/{did}/download')
def download(did:str,db:Session=Depends(get_db),user:User=Depends(current_user)):
    row=visible(db,user,did)
    try:url=storage_client().generate_presigned_url('get_object',Params={'Bucket':bucket(),'Key':row.object_key,'ResponseContentDisposition':f'attachment; filename="{row.filename}"'},ExpiresIn=60)
    except Exception:raise HTTPException(503,'Private storage temporarily unavailable')
    audit(db,user,'ADMIN_DOCUMENT_DOWNLOADED',row.id);db.commit();return {'url':url,'expires_in':60}

@router.post('/{did}/archive')
def archive(did:str,data:Archive,db:Session=Depends(get_db),user:User=Depends(current_user)):
    allow(user,MANAGERS);row=visible(db,user,did,lock=True)
    if user.role not in HR and row.uploaded_by!=user.id:raise HTTPException(403,'Only HR or the uploader can archive this document')
    if row.version!=data.version:raise HTTPException(409,'This document changed. Reload before acting.')
    row.archived=True;row.version+=1;audit(db,user,'ADMIN_DOCUMENT_ARCHIVED',row.id,detail=data.reason);db.commit();return {'ok':True}
