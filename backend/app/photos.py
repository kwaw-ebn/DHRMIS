"""Private HR-managed passport photographs; no public object URLs."""
import io, hashlib, warnings
from datetime import datetime
from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, Response
from PIL import Image, ImageOps, UnidentifiedImageError
from sqlalchemy import ForeignKey, String, Integer, DateTime, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, Session
from .db import Base, get_db
from .models import Employee, User, uid, now
from .security import current_user, allow, audit, HR, staff_query
from .phase2 import storage_client, bucket

class StaffPhoto(Base):
    __tablename__='staff_photo_versions'
    __table_args__=(UniqueConstraint('employee_id','version',name='uq_staff_photo_version'),)
    id:Mapped[str]=mapped_column(String(36),primary_key=True,default=uid)
    employee_id:Mapped[str]=mapped_column(ForeignKey('employees.id'),index=True)
    version:Mapped[int]=mapped_column(Integer)
    object_key:Mapped[str]=mapped_column(String(300),unique=True)
    checksum:Mapped[str]=mapped_column(String(64))
    created_by:Mapped[str]=mapped_column(ForeignKey('users.id'))
    created_at:Mapped[datetime]=mapped_column(DateTime(timezone=True),default=now)

router=APIRouter(prefix='/api/employees',tags=['Private staff photographs'])
MAX_BYTES=2*1024*1024
MAX_PIXELS=16_000_000

def staff(db,user,eid):
    e=staff_query(db,user).filter(Employee.id==eid).first()
    if not e:raise HTTPException(404,'Staff record not found in your scope')
    return e

def latest(db,eid):
    return db.query(StaffPhoto).filter(StaffPhoto.employee_id==eid).order_by(StaffPhoto.version.desc()).first()

def normalize(raw):
    try:
        with warnings.catch_warnings():
            warnings.simplefilter('error',Image.DecompressionBombWarning)
            with Image.open(io.BytesIO(raw)) as source:
                if source.format not in {'JPEG','PNG'}:raise HTTPException(415,'Upload a genuine JPEG or PNG photograph')
                if source.width*source.height>MAX_PIXELS:raise HTTPException(413,'Image dimensions are too large (maximum 16 megapixels)')
                source.verify()
            with Image.open(io.BytesIO(raw)) as source:
                image=ImageOps.exif_transpose(source);image.thumbnail((600,800))
                rgba=image.convert('RGBA');clean=Image.new('RGB',rgba.size,'white');clean.paste(rgba,mask=rgba.getchannel('A'))
                output=io.BytesIO();clean.save(output,format='JPEG',quality=88,optimize=True)
                return output.getvalue()
    except HTTPException:raise
    except (UnidentifiedImageError,OSError,ValueError,SyntaxError,Image.DecompressionBombError,Image.DecompressionBombWarning):raise HTTPException(400,'The photograph is invalid, damaged or unsafe to process')

@router.get('/{employee_id}/photo/meta')
def photo_meta(employee_id:str,db:Session=Depends(get_db),user:User=Depends(current_user)):
    staff(db,user,employee_id);row=latest(db,employee_id)
    return {'exists':bool(row),'version':row.version if row else 0}

@router.post('/{employee_id}/photo',status_code=201)
async def upload_photo(employee_id:str,version:int=Form(...,ge=0),file:UploadFile=File(...),db:Session=Depends(get_db),user:User=Depends(current_user)):
    allow(user,HR);e=staff(db,user,employee_id)
    if file.content_type not in {'image/jpeg','image/png'}:raise HTTPException(415,'Use a JPEG or PNG photograph')
    raw=await file.read(MAX_BYTES+1)
    if not raw:raise HTTPException(400,'Choose a photograph')
    if len(raw)>MAX_BYTES:raise HTTPException(413,'Photographs must be 2 MB or smaller')
    content=normalize(raw)
    db.query(Employee).filter(Employee.id==e.id).with_for_update().populate_existing().one()
    current=latest(db,e.id)
    if version!=(current.version if current else 0):raise HTTPException(409,'The passport photo changed. Reopen the form before replacing it.')
    key='staff-photos/'+e.id+'/'+uid()+'.jpg'
    try:storage_client().put_object(Bucket=bucket(),Key=key,Body=content,ContentType='image/jpeg',CacheControl='private, no-store')
    except HTTPException:raise
    except Exception:raise HTTPException(503,'Private photo storage is unavailable. The staff record is saved; retry the photo later.')
    row=StaffPhoto(employee_id=e.id,version=version+1,object_key=key,checksum=hashlib.sha256(content).hexdigest(),created_by=user.id)
    db.add(row);audit(db,user,'STAFF_PHOTO_UPLOADED',e.id,detail='Photo version '+str(row.version));db.commit()
    return {'exists':True,'version':row.version}

@router.get('/{employee_id}/photo')
def view_photo(employee_id:str,db:Session=Depends(get_db),user:User=Depends(current_user)):
    staff(db,user,employee_id);row=latest(db,employee_id)
    if not row:raise HTTPException(404,'No passport photo has been uploaded')
    try:
        obj=storage_client().get_object(Bucket=bucket(),Key=row.object_key);body=obj['Body']
        try:content=body.read(MAX_BYTES+1)
        finally:body.close()
    except HTTPException:raise
    except Exception:raise HTTPException(503,'Private photo storage is temporarily unavailable')
    if len(content)>MAX_BYTES or hashlib.sha256(content).hexdigest()!=row.checksum:raise HTTPException(503,'Photo integrity verification failed')
    audit(db,user,'STAFF_PHOTO_VIEWED',employee_id);db.commit()
    return Response(content,media_type='image/jpeg',headers={'Cache-Control':'private, no-store, max-age=0','X-Content-Type-Options':'nosniff','Content-Disposition':'inline; filename="passport-photo.jpg"'})
