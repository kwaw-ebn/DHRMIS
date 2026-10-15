import io,zipfile
import pytest
from conftest import as_role
from test_roster_uploads import Store,pdf
from app import admin_documents as mod

@pytest.fixture
def storage(monkeypatch):
    s=Store();monkeypatch.setattr(mod,'storage_client',lambda:s);return s

def upload(client,ids,role='hr_admin',values=None,raw=None):
    data={'title':'District management meeting','unit_id':ids['a'],'category':'Meeting minutes','document_date':'2026-10-01','registered_date':'2026-10-02','reference':'DHD/MIN/01'};data.update(values or {})
    return as_role(client,role).post('/api/admin-documents',data=data,files={'file':('document.pdf',pdf() if raw is None else raw,'application/pdf')})
def listing(client,role='hr_admin',**params):return as_role(client,role).get('/api/admin-documents',params=params)
def office(kind='docx',macro=False):
    b=io.BytesIO()
    with zipfile.ZipFile(b,'w',zipfile.ZIP_DEFLATED) as z:
        content='application/vnd.openxmlformats-officedocument.'+('wordprocessingml.document.main+xml' if kind=='docx' else 'spreadsheetml.sheet.main+xml')
        z.writestr('[Content_Types].xml',f'<Types><Override ContentType="{content}"/></Types>')
        z.writestr('word/document.xml' if kind=='docx' else 'xl/workbook.xml','<document>Test minutes</document>')
        if macro:z.writestr('word/vbaProject.bin',b'macro')
    return b.getvalue()

def test_default_confidentiality_and_manager_scopes(world,client,storage):
    _,ids=world;r=upload(client,ids);assert r.status_code==201,r.text
    d=r.json();rid=d['id'];assert 'object_key' not in d and 'checksum' not in d and d['visibility']=='hr_only'
    for role in ['hr_officer','director']:assert listing(client,role).json()['total']==1
    assert listing(client,'facility_head').json()['total']==0
    assert listing(client,'facility_head',q='District').json()['total']==0
    assert as_role(client,'facility_head').get(f'/api/admin-documents/{rid}/download').status_code==404
    shared=upload(client,ids,values={'visibility':'unit_management'}).json()['id']
    assert listing(client,'facility_head').json()['total']==1
    assert as_role(client,'facility_head').get(f'/api/admin-documents/{shared}/download').status_code==200
    assert as_role(client,'facility_head').post(f'/api/admin-documents/{shared}/archive',json={'version':1,'reason':'Incorrect copy'}).status_code==403
    other=upload(client,ids,values={'unit_id':ids['b'],'visibility':'unit_management'}).json()['id']
    assert as_role(client,'facility_head').get(f'/api/admin-documents/{other}/download').status_code==404
    for role in ['employee','platform_admin','auditor']:
        assert listing(client,role).status_code==403
        assert upload(client,ids,role).status_code==403
        assert as_role(client,role).get(f'/api/admin-documents/{rid}/download').status_code==403
    assert upload(client,ids,'director').status_code==403

def test_head_upload_archive_duplicate_and_stale_version(world,client,storage):
    factory,ids=world;raw=pdf();r=upload(client,ids,'facility_head',raw=raw);assert r.status_code==201,r.text
    rid=r.json()['id'];assert listing(client,'facility_head').json()['total']==1
    assert upload(client,ids,'facility_head',raw=raw).status_code==409
    assert upload(client,ids,'facility_head',{'unit_id':ids['b']}).status_code==404
    assert as_role(client,'facility_head').post(f'/api/admin-documents/{rid}/archive',json={'version':2,'reason':'Corrected minutes'}).status_code==409
    assert as_role(client,'facility_head').post(f'/api/admin-documents/{rid}/archive',json={'version':1,'reason':'Corrected minutes'}).status_code==200
    assert listing(client).json()['total']==0
    assert as_role(client,'hr_admin').get(f'/api/admin-documents/{rid}/download').status_code==404
    with factory() as db:assert db.get(mod.AdminDocument,rid).archived
    assert storage.objects # retained privately

def test_letter_fields_search_and_dates(world,client,storage):
    _,ids=world
    assert upload(client,ids,values={'category':'Incoming letter'}).status_code==400
    assert upload(client,ids,values={'category':'Outgoing letter'}).status_code==400
    r=upload(client,ids,values={'title':'Regional circular','category':'Incoming letter','sender':'Regional Health Directorate','reference':'RHD/44'});assert r.status_code==201,r.text
    assert listing(client,q='RHD/44').json()['total']==1
    assert listing(client,q='Regional Health').json()['total']==1
    assert listing(client,category='Outgoing letter').json()['total']==0
    assert listing(client,start='2026-10-03').json()['total']==0
    assert listing(client,end='2026-09-30').json()['total']==0
    assert listing(client,start='2026-10-03',end='2026-10-01').status_code==400
    assert listing(client,category='Unconfigured').status_code==400
    assert upload(client,ids,values={'visibility':'public'}).status_code==400
    assert upload(client,ids,values={'notes':'x'*2001}).status_code==400

def test_office_files_and_reject_macros_or_arbitrary_zip(world,client,storage):
    _,ids=world
    for kind in ['docx','xlsx']:
        r=upload(client,ids,values={'category':'Report'},raw=office(kind));assert r.status_code==201,r.text
        assert r.json()['filename'].endswith('.'+kind)
        assert 'openxmlformats' in r.json()['content_type']
    assert upload(client,ids,raw=office(macro=True)).status_code==400
    assert upload(client,ids,raw=b'PK\x03\x04broken').status_code==400
    z=io.BytesIO()
    with zipfile.ZipFile(z,'w') as archive:archive.writestr('hello.txt','Not an office document')
    assert upload(client,ids,raw=z.getvalue()).status_code==400
    assert upload(client,ids,raw=b'').status_code==413
    assert upload(client,ids,raw=b'x'*(10*1024*1024+1)).status_code==413

def test_signed_download_and_pagination(world,client,storage):
    _,ids=world;rid=upload(client,ids).json()['id']
    upload(client,ids,values={'category':'Other'})
    r=listing(client,page_size=1);assert r.json()['total']==2 and len(r.json()['items'])==1
    d=as_role(client,'director').get(f'/api/admin-documents/{rid}/download');assert d.status_code==200 and d.json()['expires_in']==60
    assert storage.links[-1]['Params']['ResponseContentDisposition'].startswith('attachment;')
    assert listing(client,unit_id=ids['b']).json()['total']==0

def test_storage_failure_and_rollback_cleanup(world,client,storage,monkeypatch):
    factory,ids=world
    def fail(**kw):raise RuntimeError('Unavailable')
    monkeypatch.setattr(storage,'put_object',fail)
    assert upload(client,ids).status_code==503
    with factory() as db:assert db.query(mod.AdminDocument).count()==0
    monkeypatch.setattr(storage,'put_object',lambda **kw:storage.objects.update({kw['Key']:kw}))
    def fail_audit(*args,**kw):raise RuntimeError('Simulated transaction error')
    monkeypatch.setattr(mod,'audit',fail_audit)
    with pytest.raises(RuntimeError):upload(client,ids)
    assert storage.deleted and not storage.objects
    with factory() as db:assert db.query(mod.AdminDocument).count()==0
