import json
from conftest import as_role
from app.models import Setting,Employee,User
from app.phase2_models import Document
from app.phase3_models import WorkforceRecord
from datetime import date

def payload(ids,**extra):
    return {'staff_id':'ae/00017','full_name':'New File Staff','job_title':'Nurse','cadre':'Nurse','grade':'Pilot A','unit_id':ids['a'],**extra}

def test_manual_staff_id_is_file_number_and_permanent(client,world):
    _,ids=world;as_role(client,'hr_admin');r=client.post('/api/employees',json=payload(ids));assert r.status_code==201,r.text;r=r.json()
    assert r['staff_id']==r['file_number']=='AE/00017'
    result=client.get('/api/employees',params={'q':'ae/00017'}).json();assert result['total']==1
    f=client.get('/api/employees/'+r['id']+'/file');assert f.status_code==200 and f.json()['file_number']=='AE/00017'
    assert client.put('/api/employees/'+r['id'],json=payload(ids,staff_id='NEW/00017',version=1)).status_code==400
    assert client.post('/api/employees',json=payload(ids,staff_id='AE/00017',full_name='Duplicate ID Staff')).status_code==409
    assert client.put('/api/employees/'+r['id'],json=payload(ids,staff_id='AE/00017',full_name='Renamed Staff',version=1)).status_code==200

def test_new_grade_choices(client,world):
    factory,ids=world;grades=['Senior','Principal','Deputy Chief','Chief']
    with factory() as db:db.get(Setting,'grades').value=json.dumps(grades);db.commit()
    as_role(client,'hr_admin');assert client.get('/api/settings').json()['grades']==grades
    for n,grade in enumerate(grades):
        r=client.post('/api/employees',json=payload(ids,staff_id=str(100+n),full_name='Grade Test '+str(n),grade=grade));assert r.status_code==201,r.text
    assert client.post('/api/employees',json=payload(ids,grade='Unconfigured grade')).status_code==400

def test_file_scope_and_confidential_sections(client,world):
    factory,ids=world
    with factory() as db:
        admin=db.query(User).filter(User.role=='hr_admin').one();emp=db.query(User).filter(User.role=='employee').one();head=db.query(User).filter(User.role=='facility_head').one()
        db.add_all([Document(employee_id=ids['e1'],title='Private appointment letter',category='Appointment letter',employee_visible=False,created_by=admin.id),Document(employee_id=ids['e1'],title='Employee training certificate',category='Training certificate',employee_visible=True,created_by=emp.id),Document(employee_id=ids['e2'],title='Another staff letter',category='Appointment letter',employee_visible=False,created_by=admin.id)])
        db.add(WorkforceRecord(kind='appraisal',employee_id=ids['e1'],title='Confidential draft review',start_date=date.today(),end_date=date.today(),created_by=admin.id,reviewer_id=head.id,data='{}'));db.commit()
    as_role(client,'employee');f=client.get('/api/employees/'+ids['e1']+'/file').json();assert len(f['documents'])==1 and f['documents'][0]['can_add_version'] and not f['workforce']['appraisal']
    assert client.get('/api/employees/'+ids['e2']+'/file').status_code==404
    as_role(client,'facility_head');f=client.get('/api/employees/'+ids['e1']+'/file').json();assert f['documents_allowed'] is False and f['document_total'] is None and not f['documents'];assert len(f['workforce']['appraisal'])==1
    as_role(client,'director');assert not client.get('/api/employees/'+ids['e1']+'/file').json()['workforce']['appraisal']
    as_role(client,'hr_admin');assert len(client.get('/api/employees/'+ids['e1']+'/file').json()['documents'])==2
    for role in ['platform_admin','auditor']:
        as_role(client,role);assert client.get('/api/employees/'+ids['e1']+'/file').status_code==403

def test_csv_duplicate_file_numbers_are_atomic(client,world):
    _,ids=world;as_role(client,'hr_admin');text='staff_id,full_name,job_title,cadre,grade,unit_id\nae/00018,CSV Staff One,Nurse,Nurse,Pilot A,'+ids['a']+'\nAE/00018,CSV Staff Two,Nurse,Nurse,Pilot A,'+ids['a']+'\n'
    assert client.post('/api/employees/import',files={'file':('staff.csv',text,'text/csv')}).status_code==400
    assert client.get('/api/employees').json()['total']==2
    one=text.split('AE/00018,CSV')[0];assert client.post('/api/employees/import',files={'file':('staff.csv',one,'text/csv')}).status_code==200
    assert client.get('/api/employees',params={'q':'AE/00018'}).json()['items'][0]['file_number']=='AE/00018'
