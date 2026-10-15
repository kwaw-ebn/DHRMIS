import io
import pytest
from PIL import Image
from conftest import as_role
from app import photos
from app.models import Employee
from app.photos import StaffPhoto

@pytest.fixture
def storage(monkeypatch):
    class Storage:
        def __init__(self):self.objects={};self.reads=0
        def put_object(self,**kw):self.objects[kw['Key']]=kw['Body'];return {}
        def get_object(self,**kw):self.reads+=1;return {'Body':io.BytesIO(self.objects[kw['Key']])}
    s=Storage();monkeypatch.setattr(photos,'storage_client',lambda:s);return s

def picture(fmt='JPEG'):
    out=io.BytesIO();im=Image.new('RGB',(900,1200),'green');exif=Image.Exif();exif[270]='Private camera metadata';im.save(out,format=fmt,exif=exif);return out.getvalue()
def upload(client,eid,version=0,raw=None,mime='image/jpeg'):
    return client.post('/api/employees/'+eid+'/photo',data={'version':str(version)},files={'file':('passport.jpg',raw if raw is not None else picture(),mime)})

def test_private_photo_optional_normalized_and_metadata_stripped(client,world,storage):
    _,ids=world;as_role(client,'hr_admin');assert client.get('/api/employees/'+ids['e1']+'/photo/meta').json()=={'exists':False,'version':0}
    assert client.get('/api/employees/'+ids['e1']+'/photo').status_code==404
    r=upload(client,ids['e1']);assert r.status_code==201,r.text
    as_role(client,'employee');r=client.get('/api/employees/'+ids['e1']+'/photo');assert r.status_code==200 and r.headers['content-type']=='image/jpeg' and r.headers['cache-control']=='no-store'
    with Image.open(io.BytesIO(r.content)) as im:assert im.size==(600,800) and not im.getexif() and im.format=='JPEG'
    assert client.get('/api/employees/'+ids['e2']+'/photo').status_code==404
    assert upload(client,ids['e1'],1).status_code==403

def test_photo_scope_and_disabled_roles(client,world,storage):
    _,ids=world;as_role(client,'hr_admin');assert upload(client,ids['e1']).status_code==201;assert upload(client,ids['e2']).status_code==201
    as_role(client,'facility_head');assert client.get('/api/employees/'+ids['e1']+'/photo').status_code==200;assert client.get('/api/employees/'+ids['e2']+'/photo').status_code==404
    for role in ['platform_admin','auditor']:
        as_role(client,role);assert client.get('/api/employees/'+ids['e1']+'/photo').status_code==403;assert client.get('/api/employees/'+ids['e1']+'/photo/meta').status_code==403
    client.cookies.clear();assert client.get('/api/employees/'+ids['e1']+'/photo').status_code==401

def test_photo_replacement_stale_version_and_retained_history(client,world,storage):
    factory,ids=world;as_role(client,'hr_admin');assert upload(client,ids['e1']).status_code==201
    assert upload(client,ids['e1']).status_code==409
    assert upload(client,ids['e1'],1,raw=picture('PNG'),mime='image/png').status_code==201
    assert client.get('/api/employees/'+ids['e1']+'/photo/meta').json()['version']==2
    with factory() as db:assert db.query(StaffPhoto).count()==2;assert db.get(Employee,ids['e1']).version==1
    assert len(storage.objects)==2

def test_invalid_oversized_and_spoofed_files_rejected(client,world,storage):
    _,ids=world;as_role(client,'hr_admin')
    assert upload(client,ids['e1'],raw=b'<svg onload="alert(1)"/>',mime='image/svg+xml').status_code==415
    assert upload(client,ids['e1'],raw=b'not a photograph').status_code==400
    assert upload(client,ids['e1'],raw=b'x'*(photos.MAX_BYTES+1)).status_code==413
    assert not storage.objects

def test_storage_failure_keeps_personnel_and_old_photo(client,world,storage,monkeypatch):
    factory,ids=world;as_role(client,'hr_admin');assert upload(client,ids['e1']).status_code==201
    def fail(**kw):raise OSError('Storage unavailable')
    monkeypatch.setattr(storage,'put_object',fail);assert upload(client,ids['e1'],1).status_code==503
    with factory() as db:assert db.query(StaffPhoto).count()==1 and db.get(Employee,ids['e1']) is not None
    assert client.get('/api/employees/'+ids['e1']+'/photo').status_code==200

def test_archived_staff_photo_inaccessible_and_csrf_required(client,world,storage):
    factory,ids=world;as_role(client,'hr_admin');assert upload(client,ids['e1']).status_code==201
    client.headers['x-csrf-token']='invalid';assert upload(client,ids['e1'],1).status_code==403
    with factory() as db:db.get(Employee,ids['e1']).archived=True;db.commit()
    assert client.get('/api/employees/'+ids['e1']+'/photo').status_code==404
