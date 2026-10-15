import io
from datetime import date
import pytest
from PIL import Image
from reportlab.pdfgen import canvas
from conftest import as_role
from app import roster_uploads as mod
from app.models import Unit,Employee,User

class Store:
    def __init__(self):self.objects={};self.deleted=[];self.links=[]
    def put_object(self,**kw):self.objects[kw['Key']]=kw
    def delete_object(self,**kw):self.deleted.append(kw['Key']);self.objects.pop(kw['Key'],None)
    def generate_presigned_url(self,*args,**kw):self.links.append(kw);return 'https://example.test/private?temporary=1'
@pytest.fixture
def storage(monkeypatch):
    s=Store();monkeypatch.setattr(mod,'storage_client',lambda:s);return s

def pdf():
    f=io.BytesIO();c=canvas.Canvas(f);c.drawString(50,700,'Synthetic roster test only');c.save();return f.getvalue()
def send(client,ids,role='hr_admin',body=None,content=None):
    data={'unit_id':ids['a'],'title':'October duty roster','start_date':'2026-10-01','end_date':'2026-10-31'};data.update(body or {})
    return as_role(client,role).post('/api/roster-uploads',data=data,files={'file':('roster.pdf',pdf() if content is None else content,'application/pdf')})
def listing(client,role='hr_admin',**query):return as_role(client,role).get('/api/roster-uploads',params={'start':'2026-10-01','end':'2026-10-31',**query})

def test_upload_and_read_scope_no_object_keys(world,client,storage):
    factory,ids=world;r=send(client,ids,'facility_head');assert r.status_code==201,r.text
    d=r.json();rid=d['id'];assert d['unit_name']=='Facility A' and 'object_key' not in d and 'checksum' not in d
    assert len(storage.objects)==1 and next(iter(storage.objects)).startswith('rosters/')
    for role in ['employee','hr_officer','director','facility_head']:
        assert listing(client,role).json()['total']==1
        link=as_role(client,role).get(f'/api/roster-uploads/{rid}/download');assert link.status_code==200 and link.json()['expires_in']==60
    for role in ['employee','director','platform_admin','auditor']:assert send(client,ids,role).status_code==403
    assert send(client,ids,'facility_head',{'unit_id':ids['b']}).status_code==404
    other=send(client,ids,body={'unit_id':ids['b']}).json()['id']
    for role in ['facility_head','employee']:
        assert listing(client,role).json()['total']==1
        assert as_role(client,role).get(f'/api/roster-uploads/{other}/download').status_code==404
    for role in ['platform_admin','auditor']:assert listing(client,role).status_code==403
    assert storage.links[0]['Params']['ResponseContentDisposition'].startswith('attachment;')

def test_duplicates_archive_and_stale_version(world,client,storage):
    _,ids=world;raw=pdf();r=send(client,ids,content=raw);rid=r.json()['id']
    assert send(client,ids,content=raw).status_code==409
    assert as_role(client,'employee').post(f'/api/roster-uploads/{rid}/archive',json={'version':1,'reason':'Superseded copy'}).status_code==403
    assert as_role(client,'hr_admin').post(f'/api/roster-uploads/{rid}/archive',json={'version':2,'reason':'Superseded copy'}).status_code==409
    assert as_role(client,'facility_head').post(f'/api/roster-uploads/{rid}/archive',json={'version':1,'reason':'Superseded copy'}).status_code==200
    assert listing(client).json()['total']==0
    assert as_role(client,'hr_admin').get(f'/api/roster-uploads/{rid}/download').status_code==404
    assert len(storage.objects)==1 # archived original retained privately
    with world[0]() as db:assert db.get(mod.RosterUpload,rid).archived is True

def test_validation_period_files_and_active_unit(world,client,storage):
    factory,ids=world
    for content in [b'not a scan',b'%PDF-1.7\ntruncated',b'\x89PNG\r\n\x1a\nwrong']:
        assert send(client,ids,content=content).status_code==400
    assert send(client,ids,content=b'').status_code==413
    assert send(client,ids,content=b'x'*(10*1024*1024+1)).status_code==413
    assert send(client,ids,body={'end_date':'2026-09-01'}).status_code==400
    assert send(client,ids,body={'end_date':'2028-01-01'}).status_code==400
    assert send(client,ids,body={'unit_id':ids['district']}).status_code==404
    with factory() as db:db.get(Unit,ids['a']).active=False;db.commit()
    assert send(client,ids).status_code==404
    assert storage.objects=={}

def test_image_reencode_and_metadata_removed(world,client,storage):
    _,ids=world;image=Image.new('RGB',(1200,800),'white');f=io.BytesIO();exif=Image.Exif();exif[270]='Private camera metadata';image.save(f,format='JPEG',exif=exif)
    r=send(client,ids,content=f.getvalue());assert r.status_code==201,r.text
    assert r.json()['content_type']=='image/jpeg' and r.json()['filename'].endswith('.jpg')
    raw=next(iter(storage.objects.values()))['Body']
    with Image.open(io.BytesIO(raw)) as result:assert not result.getexif() and result.size==(1200,800)

def test_period_overlap_and_pagination(world,client,storage):
    _,ids=world
    assert send(client,ids,body={'start_date':'2026-09-20','end_date':'2026-10-05'}).status_code==201
    assert send(client,ids,body={'unit_id':ids['b'],'start_date':'2026-11-01','end_date':'2026-11-30'}).status_code==201
    r=listing(client,page_size=1);assert r.json()['total']==1 and len(r.json()['items'])==1
    assert listing(client,unit_id=ids['b']).json()['total']==0
    assert listing(client,start='2026-11-01',end='2026-10-01').status_code==400

def test_department_staff_read_facility_but_not_other_department(world,client,storage):
    factory,ids=world
    with factory() as db:
        dept=Unit(name='Nutrition',kind='department',parent_id=ids['a']);other=Unit(name='Finance',kind='department',parent_id=ids['a']);db.add_all([dept,other]);db.flush()
        db.get(Employee,ids['e1']).unit_id=dept.id
        head=db.query(User).filter_by(role='facility_head').one();head.role='department_head';head.unit_id=dept.id;db.commit();dep_id=dept.id;other_id=other.id
    own=send(client,ids).json()['id'];other=send(client,ids,body={'unit_id':other_id}).json()['id'];department=send(client,ids,'facility_head',{'unit_id':dep_id});assert department.status_code==201,department.text
    assert listing(client,'employee').json()['total']==2
    assert as_role(client,'employee').get(f'/api/roster-uploads/{own}/download').status_code==200
    assert as_role(client,'employee').get(f'/api/roster-uploads/{other}/download').status_code==404
    assert send(client,ids,'facility_head').status_code==404
    assert listing(client,'facility_head').json()['total']==1

def test_storage_failure_and_commit_failure_cleanup(world,client,storage,monkeypatch):
    factory,ids=world
    def fail(**kw):raise RuntimeError('Unavailable')
    monkeypatch.setattr(storage,'put_object',fail)
    assert send(client,ids).status_code==503
    with factory() as db:assert db.query(mod.RosterUpload).count()==0
    monkeypatch.setattr(storage,'put_object',lambda **kw:storage.objects.update({kw['Key']:kw}))
    def fail_audit(*args,**kw):raise RuntimeError('Simulated transaction failure')
    monkeypatch.setattr(mod,'audit',fail_audit)
    with pytest.raises(RuntimeError):send(client,ids)
    assert len(storage.deleted)==1 and not storage.objects
    with factory() as db:assert db.query(mod.RosterUpload).count()==0
