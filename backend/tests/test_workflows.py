import csv,io,json,pyotp
from datetime import datetime,timedelta,timezone
from conftest import as_role
from app.models import Employee,User,Session,Audit
from app.security import digest,encrypt

def payload(ids,**changes):
    return {'full_name':'New Staff','job_title':'Nurse','cadre':'Nurse','grade':'Pilot A','unit_id':ids['a'],**changes}

def test_employee_isolation(client,world):
    _,ids=world;as_role(client,'employee')
    assert client.get('/api/employees').json()['total']==1
    assert client.get('/api/employees/'+ids['e2']).status_code==404
    assert client.post('/api/employees',json=payload(ids)).status_code==403
    assert client.get('/api/users').status_code==403
    assert client.get('/api/employees/export').status_code==403

def test_facility_scope_and_masking(client,world):
    _,ids=world;as_role(client,'facility_head')
    d=client.get('/api/employees').json();assert d['total']==1
    assert 'payroll_number' not in d['items'][0]
    assert client.get('/api/dashboard?unit_id='+ids['b']).json()['total']==0
    assert client.get('/api/employees/'+ids['e2']).status_code==404
    assert ids['b'] not in [u['id'] for u in client.get('/api/units').json()]

def test_technical_and_auditor_restrictions(client,world):
    as_role(client,'platform_admin');assert client.get('/api/employees').status_code==403
    assert client.get('/api/dashboard').status_code==403
    as_role(client,'auditor');assert client.get('/api/audit').status_code==200
    assert client.get('/api/employees').status_code==403
    assert client.get('/api/users').status_code==403

def test_crud_duplicate_and_stale_edit(client,world):
    factory,ids=world;as_role(client,'hr_admin')
    r=client.post('/api/employees',json=payload(ids,ghs_number='NEW-1'));assert r.status_code==201,r.text
    row=r.json();data=payload(ids,ghs_number='NEW-1',full_name='Updated Staff',version=row['version'])
    r=client.put('/api/employees/'+row['id'],json=data);assert r.status_code==200,r.text
    assert client.put('/api/employees/'+row['id'],json=data).status_code==409
    assert client.post('/api/employees',json=payload(ids,full_name='Other Staff',ghs_number='NEW-1')).status_code==409
    assert client.put('/api/employees/'+row['id'],json=payload(ids,unit_id=ids['b'],version=2)).status_code==400
    assert client.delete('/api/employees/'+row['id']).status_code==200
    assert client.get('/api/employees/'+row['id']).status_code==404
    with factory() as db:assert db.get(Employee,row['id']).archived

def test_csv_atomicity_and_formula_protection(client,world):
    _,ids=world;as_role(client,'hr_admin')
    content='full_name,job_title,cadre,grade,unit_id\nImported Staff,Nurse,Nurse,Pilot A,'+ids['a']+'\nBroken Staff,Nurse,Invalid,Pilot A,'+ids['a']+'\n'
    assert client.post('/api/employees/import',files={'file':('staff.csv',content,'text/csv')}).status_code==400
    assert client.get('/api/employees').json()['total']==2
    good=content.split('Broken Staff')[0]
    assert client.post('/api/employees/import',files={'file':('staff.csv',good,'text/csv')}).json()['imported']==1
    assert client.post('/api/employees',json=payload(ids,full_name='=DANGEROUS')).status_code==201
    rows=list(csv.DictReader(io.StringIO(client.get('/api/employees/export').text)))
    assert any(r['full_name']=="'=DANGEROUS" for r in rows)

def test_csrf_origin_and_expiry(client,world):
    factory,ids=world;as_role(client,'hr_admin');client.headers.pop('x-csrf-token')
    assert client.post('/api/employees',json=payload(ids)).status_code==403
    client.headers['x-csrf-token']='test-csrf'
    assert client.post('/api/employees',json=payload(ids),headers={'origin':'https://evil.example'}).status_code==403
    with factory() as db:
        s=db.get(Session,digest('hr_admin'));s.expires_at=datetime.now(timezone.utc)-timedelta(seconds=1);db.commit()
    assert client.get('/api/employees').status_code==401

def test_mfa_login_and_replay(client,world):
    factory,_=world
    r=client.post('/api/auth/login',json={'email':'hr_admin@example.com','password':'StrongPilotPassword1!'})
    assert r.status_code==200;assert r.json()['mfa_required']
    client.headers['x-csrf-token']=r.json()['csrf_token']
    assert client.get('/api/employees').status_code==403
    r=client.get('/api/auth/mfa/setup');assert r.status_code==200
    secret=r.json()['secret'];code=pyotp.TOTP(secret).now()
    assert client.post('/api/auth/mfa/verify',json={'code':code}).status_code==200
    assert client.get('/api/employees').status_code==200
    assert client.post('/api/auth/mfa/verify',json={'code':code}).status_code==401
    with factory() as db:
        u=db.query(User).filter(User.role=='hr_admin').one();assert secret not in u.totp_secret

def test_lockout(client,world):
    for _ in range(5):assert client.post('/api/auth/login',json={'email':'hr_admin@example.com','password':'bad'}).status_code==401
    assert client.post('/api/auth/login',json={'email':'hr_admin@example.com','password':'StrongPilotPassword1!'}).status_code==429

def test_account_creation_disable_and_reset(client,world):
    _,ids=world;as_role(client,'hr_admin')
    data={'email':'new@example.com','name':'New employee','password':'TemporarySecret123!','role':'employee','employee_id':ids['e2']}
    r=client.post('/api/users',json=data);assert r.status_code==201,r.text
    uid=r.json()['id'];assert client.post('/api/users',json={**data,'email':'nope@example.com','role':'platform_admin','employee_id':None}).status_code==403
    assert client.patch('/api/users/'+uid,json={'active':False}).status_code==200
    client.cookies.clear();assert client.post('/api/auth/login',json={'email':'new@example.com','password':data['password']}).status_code==401
    as_role(client,'hr_admin');assert client.patch('/api/users/'+uid,json={'active':True}).status_code==200
    assert len(client.post('/api/users/'+uid+'/reset-password').json()['temporary_password'])>=12

def test_password_change_gate(client,world):
    factory,_=world
    with factory() as db:
        u=db.query(User).filter(User.role=='employee').one();u.must_change_password=True;db.commit()
    as_role(client,'employee');assert client.get('/api/employees').status_code==403
    assert client.post('/api/auth/password',json={'current_password':'StrongPilotPassword1!','new_password':'NewStrongPassword123!'}).status_code==200
    assert client.get('/api/employees').status_code==200

def test_hierarchy_vocabulary_and_audit(client,world):
    _,ids=world;as_role(client,'hr_admin')
    assert client.post('/api/units',json={'name':'Invalid','kind':'facility','parent_id':ids['a'],'category':'CHPS'}).status_code==400
    r=client.post('/api/units',json={'name':'New CHPS','kind':'facility','parent_id':ids['district'],'category':'CHPS'});assert r.status_code==201
    uid=r.json()['id'];assert client.patch('/api/units/'+uid,json={'name':'Renamed CHPS'}).status_code==200
    assert client.delete('/api/units/'+ids['a']).status_code==409
    assert client.delete('/api/units/'+uid).status_code==200
    assert client.put('/api/settings/vocabulary',json={'cadres':['Doctor'],'grades':['Pilot A']}).status_code==409
    assert client.get('/api/audit').json()['total']>=3
