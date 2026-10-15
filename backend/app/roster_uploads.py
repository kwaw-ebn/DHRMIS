"""Private facility/department copies of paper duty rosters."""
import hashlib, io, os, re, warnings
from datetime import date, datetime
from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from pydantic import BaseModel, ConfigDict, Field
from PIL import Image, ImageOps, UnidentifiedImageError
from sqlalchemy import Boolean, Date, DateTime, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, Session, mapped_column
from .db import Base, get_db
from .models import Employee, Unit, User, uid, now
from .security import current_user, allow, audit, descendants, HR, SCOPED
from .phase2 import storage_client, bucket

class RosterUpload(Base):
    __tablename__='roster_uploads'
    id:Mapped[str]=mapped_column(String(36),primary_key=True,default=uid)
    unit_id:Mapped[str]=mapped_column(ForeignKey('organization_units.id'),index=True)
    title:Mapped[str]=mapped_column(String(180))
    start_date:Mapped[date]=mapped_column(Date,index=True)
    end_date:Mapped[date]=mapped_column(Date)
    object_key:Mapped[str]=mapped_column(String(300),unique=True)
    filename:Mapped[str]=mapped_column(String(180))
    content_type:Mapped[str]=mapped_column(String(80))
    size:Mapped[int]=mapped_column(Integer)
    checksum:Mapped[str]=mapped_column(String(64))
    uploaded_by:Mapped[str]=mapped_column(ForeignKey('users.id'))
    created_at:Mapped[datetime]=mapped_column(DateTime(timezone=True),default=now)
    archived:Mapped[bool]=mapped_column(Boolean,default=False)
    version:Mapped[int]=mapped_column(Integer,default=1)

router=APIRouter(prefix='/api/roster-uploads',tags=['Paper duty roster copies'])
MANAGERS=HR|SCOPED
READERS=MANAGERS|{'director','employee'}
MAX_BYTES=10*1024*1024
class Archive(BaseModel):
    model_config=ConfigDict(extra='forbid',str_strip_whitespace=True)
    version:int=Field(ge=1)
    reason:str=Field(min_length=3,max_length=500)

def allowed_units(db,user):
    allow(user,READERS)
    q=db.query(Unit).filter(Unit.active==True,Unit.kind.in_(['facility','department']))
    if user.role in SCOPED:q=q.filter(Unit.id.in_(descendants(db,user.unit_id)))
    elif user.role=='employee':
        e=db.get(Employee,user.employee_id) if user.employee_id else None;ids=set()
        if e and not e.archived:
            ids.add(e.unit_id);unit=db.get(Unit,e.unit_id)
            if unit and unit.kind=='department' and unit.parent_id:
                parent=db.get(Unit,unit.parent_id)
                if parent and parent.kind=='facility':ids.add(parent.id)
        q=q.filter(Unit.id.in_(ids))
    return q

def visible(db,user,rid,lock=False):
    q=db.query(RosterUpload).filter(RosterUpload.id==rid,RosterUpload.archived==False,RosterUpload.unit_id.in_(allowed_units(db,user).with_entities(Unit.id)))
    if lock:q=q.with_for_update().populate_existing()
    row=q.first()
    if not row:raise HTTPException(404,'Roster copy not found in your scope')
    return row

def view(db,row):
    return {k:getattr(row,k) for k in ['id','unit_id','title','start_date','end_date','filename','content_type','size','created_at','version']}|{'unit_name':db.get(Unit,row.unit_id).name,'uploaded_by_name':db.get(User,row.uploaded_by).name}

def normalize(content):
    if content.startswith(b'%PDF-'):
        if b'%%EOF' not in content[-2048:]:raise HTTPException(400,'The PDF appears incomplete. Upload a complete scan.')
        return content,'application/pdf','.pdf'
    try:
        with warnings.catch_warnings():
            warnings.simplefilter('error',Image.DecompressionBombWarning)
            with Image.open(io.BytesIO(content)) as image:
                if image.format not in {'JPEG','PNG'}:raise HTTPException(415,'Upload PDF, JPEG or PNG')
                if image.width*image.height>25_000_000:raise HTTPException(413,'Photo dimensions exceed 25 megapixels. Use a smaller photo or PDF scan.')
                kind=image.format;image.verify()
            with Image.open(io.BytesIO(content)) as image:
                image=ImageOps.exif_transpose(image);image.thumbnail((6000,6000));clean=Image.new('RGB',image.size,'white')
                if image.mode in {'RGBA','LA'}:
                    rgba=image.convert('RGBA');clean.paste(rgba,mask=rgba.getchannel('A'))
                else:clean.paste(image.convert('RGB'))
                result=io.BytesIO();clean.save(result,format='PNG' if kind=='PNG' else 'JPEG',**({} if kind=='PNG' else {'quality':92}));raw=result.getvalue()
                if len(raw)>MAX_BYTES:raise HTTPException(413,'Processed photo is too large. Upload a smaller image or PDF scan.')
                return (raw,'image/png','.png') if kind=='PNG' else (raw,'image/jpeg','.jpg')
    except HTTPException:raise
    except (UnidentifiedImageError,OSError,ValueError,Image.DecompressionBombWarning,Image.DecompressionBombError):raise HTTPException(400,'Upload a valid PDF, JPEG or PNG scan/photo')

@router.get('')
def list_uploads(start:date,end:date,unit_id:str='',page:int=Query(1,ge=1),page_size:int=Query(20,ge=1,le=100),db:Session=Depends(get_db),user:User=Depends(current_user)):
    if end<start or (end-start).days>366:raise HTTPException(400,'Select a valid period of at most 367 days')
    allowed=allowed_units(db,user)
    q=db.query(RosterUpload).filter(RosterUpload.archived==False,RosterUpload.unit_id.in_(allowed.with_entities(Unit.id)),RosterUpload.start_date<=end,RosterUpload.end_date>=start)
    if unit_id:q=q.filter(RosterUpload.unit_id==unit_id)
    total=q.count();rows=q.order_by(RosterUpload.created_at.desc(),RosterUpload.id).offset((page-1)*page_size).limit(page_size).all();audit(db,user,'PAPER_ROSTERS_READ');db.commit()
    return {'items':[view(db,r) for r in rows],'total':total}

@router.post('',status_code=201)
async def upload(unit_id:str=Form(...),title:str=Form(...),start_date:date=Form(...),end_date:date=Form(...),file:UploadFile=File(...),db:Session=Depends(get_db),user:User=Depends(current_user)):
    allow(user,MANAGERS)
    unit=allowed_units(db,user).filter(Unit.id==unit_id).with_for_update().populate_existing().first()
    if not unit:raise HTTPException(404,'Choose an active facility or department in your scope')
    if not 3<=len(title.strip())<=180:raise HTTPException(400,'Enter a title of 3–180 characters')
    if end_date<start_date or (end_date-start_date).days>366:raise HTTPException(400,'Choose a roster period of at most 367 days')
    raw=await file.read(MAX_BYTES+1)
    if not raw or len(raw)>MAX_BYTES:raise HTTPException(413,'Upload a non-empty PDF, JPEG or PNG up to 10 MB')
    content,mime,extension=normalize(raw);checksum=hashlib.sha256(content).hexdigest()
    if db.query(RosterUpload).filter_by(unit_id=unit.id,start_date=start_date,end_date=end_date,checksum=checksum,archived=False).first():raise HTTPException(409,'This copy is already uploaded for this unit and period')
    filename=re.sub(r'[^A-Za-z0-9._-]','_',os.path.basename(file.filename or 'roster'))[:150]
    if not filename.lower().endswith(extension):filename='duty-roster'+extension
    key='rosters/'+uid()+extension;row=RosterUpload(unit_id=unit.id,title=title.strip(),start_date=start_date,end_date=end_date,object_key=key,filename=filename,content_type=mime,size=len(content),checksum=checksum,uploaded_by=user.id)
    client=storage_client()
    try:client.put_object(Bucket=bucket(),Key=key,Body=content,ContentType=mime,CacheControl='private, no-store')
    except Exception:raise HTTPException(503,'Private storage upload failed. Retry later.')
    try:
        db.add(row);db.flush();audit(db,user,'PAPER_ROSTER_UPLOADED',row.id,detail=f'Period {start_date} to {end_date}');db.commit()
    except Exception:
        db.rollback()
        try:client.delete_object(Bucket=bucket(),Key=key)
        except Exception:pass
        raise
    return view(db,row)

@router.get('/{rid}/download')
def download(rid:str,db:Session=Depends(get_db),user:User=Depends(current_user)):
    row=visible(db,user,rid)
    try:url=storage_client().generate_presigned_url('get_object',Params={'Bucket':bucket(),'Key':row.object_key,'ResponseContentDisposition':f'attachment; filename="{row.filename}"'},ExpiresIn=60)
    except Exception:raise HTTPException(503,'Private storage temporarily unavailable')
    audit(db,user,'PAPER_ROSTER_DOWNLOADED',row.id);db.commit();return {'url':url,'expires_in':60}

@router.post('/{rid}/archive')
def archive(rid:str,data:Archive,db:Session=Depends(get_db),user:User=Depends(current_user)):
    allow(user,MANAGERS);row=visible(db,user,rid,lock=True)
    if row.version!=data.version:raise HTTPException(409,'This roster copy changed. Reload before acting.')
    row.archived=True;row.version+=1;audit(db,user,'PAPER_ROSTER_ARCHIVED',row.id,detail=data.reason);db.commit();return {'ok':True}
