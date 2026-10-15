from datetime import date
from conftest import as_role
from app.models import User,Employee

def create(client,world,kind='training',reviewer=None):
    _,ids=world
    data={'training':{'provider':'Test provider','hours':4,'credits':2},'promotion':{'target_grade':'Pilot A','policy_reference':'Test authority','evidence':'Reviewed test evidence'},'retirement':{'policy_reference':'Test authority','reason':'Authorized test exit','checklist':['Handover','Return property']},'appraisal':{'objectives':'Test objectives'}}[kind]
    r=client.post('/api/workforce/records',json={'kind':kind,'employee_id':ids['e1'],'title':'Test '+kind,'start_date':str(date.today()),'end_date':str(date.today()),'reviewer_id':reviewer,'data':data})
    assert r.status_code==201,r.text
    return r.json()
def act(client,row,role,action,extra=None,expected=200):
    as_role(client,role);r=client.post('/api/workforce/records/'+row['id']+'/actions',json={'version':row['version'],'action':action,'comment':'Test decision explanation',**(extra or {})})
    assert r.status_code==expected,r.text
    return r.json() if expected==200 else row

def test_training_verification_and_concurrent_action(client,world):
    as_role(client,'employee');r=create(client,world);r=act(client,r,'employee','submit');act(client,r,'employee','verify',expected=403)
    old=r;r=act(client,r,'hr_officer','verify');assert r['status']=='verified';act(client,old,'hr_officer','verify',expected=409)
    as_role(client,'auditor');assert client.get('/api/workforce/records?kind=training').status_code==403
    as_role(client,'hr_admin');r=create(client,world);r=act(client,r,'hr_admin','submit');act(client,r,'hr_admin','verify',expected=403)

def test_appraisal_confidentiality_release(client,world):
    factory,ids=world
    with factory() as db:reviewer=db.query(User).filter(User.role=='facility_head').one().id
    as_role(client,'hr_admin');r=create(client,world,'appraisal',reviewer)
    for role in ['employee','director']:
        as_role(client,role);assert client.get('/api/workforce/records?kind=appraisal').json()['items']==[]
    payload={'version':1,'title':r['title'],'start_date':r['start_date'],'end_date':r['end_date'],'data':{'objectives':'Test objectives','assessment':'Confidential test assessment'}}
    as_role(client,'hr_admin');assert client.put('/api/workforce/records/'+r['id'],json=payload).status_code==403
    as_role(client,'facility_head');edit=client.put('/api/workforce/records/'+r['id'],json=payload);assert edit.status_code==200,edit.text;r=edit.json()
    r=act(client,r,'facility_head','submit');r=act(client,r,'hr_admin','release')
    as_role(client,'employee');assert client.get('/api/workforce/records?kind=appraisal').json()['items'][0]['data']['assessment']=='Confidential test assessment'
    assert act(client,r,'employee','acknowledge')['status']=='acknowledged'

def test_promotion_exit_human_decisions(client,world):
    factory,ids=world;as_role(client,'hr_admin');r=create(client,world,'promotion');r=act(client,r,'hr_admin','submit');act(client,r,'hr_officer','approve',expected=403);assert act(client,r,'director','approve')['status']=='approved'
    as_role(client,'hr_admin');r=create(client,world,'retirement');r=act(client,r,'hr_admin','submit');r=act(client,r,'director','approve');act(client,r,'hr_admin','complete',expected=409)
    r=act(client,r,'hr_admin','checklist',{'completed_items':['Handover','Return property']});assert act(client,r,'hr_admin','complete')['status']=='completed'
    with factory() as db:assert db.get(Employee,ids['e1']).status=='Active'

def test_roster_overlap_scope_publication(client,world):
    _,ids=world;as_role(client,'facility_head');day=str(date.today());p={'employee_id':ids['e1'],'starts_at':day+'T08:00:00Z','ends_at':day+'T16:00:00Z','duty':'Day shift'}
    r=client.post('/api/workforce/roster',json=p);assert r.status_code==201,r.text;r=r.json()
    assert client.post('/api/workforce/roster',json=p).status_code==409
    assert client.post('/api/workforce/roster',json={**p,'employee_id':ids['e2']}).status_code==404
    as_role(client,'employee');assert client.get('/api/workforce/roster',params={'start':day,'end':day}).json()==[]
    as_role(client,'facility_head');assert client.post('/api/workforce/roster/'+r['id']+'/actions',json={'action':'publish','version':1,'comment':'Roster authorized'}).status_code==200
    as_role(client,'employee');assert len(client.get('/api/workforce/roster',params={'start':day,'end':day}).json())==1

def test_attendance_conflict_separate_verification(client,world):
    _,ids=world;as_role(client,'employee');p={'employee_id':ids['e1'],'day':str(date.today()),'outcome':'present','note':'Manual test entry'}
    r=client.put('/api/workforce/attendance',json=p);assert r.status_code==200,r.text;r=r.json();assert client.put('/api/workforce/attendance',json=p).status_code==409
    as_role(client,'facility_head');a={'action':'verify','version':1,'comment':'Checked duty register'};v=client.post('/api/workforce/attendance/'+r['id']+'/actions',json=a);assert v.status_code==200,v.text
    assert client.put('/api/workforce/attendance',json={**p,'version':2}).status_code==409
    assert client.post('/api/workforce/attendance/'+r['id']+'/actions',json={**a,'action':'reopen','version':1}).status_code==409
    assert client.post('/api/workforce/attendance/'+r['id']+'/actions',json={**a,'action':'reopen','version':2}).status_code==200
    as_role(client,'employee');assert client.put('/api/workforce/attendance',json={**p,'version':3,'outcome':'late'}).status_code==200

def test_establishment_gaps_role_restrictions(client,world):
    _,ids=world;as_role(client,'hr_admin');r=client.post('/api/workforce/establishments',json={'unit_id':ids['a'],'cadre':'Nurse','positions':3,'reference':'Test approved register','effective_date':str(date.today())});assert r.status_code==201,r.text;r=r.json()
    assert client.get('/api/workforce/establishments').json()[0]['vacancies'] is None
    as_role(client,'director');assert client.post('/api/workforce/establishments/'+r['id']+'/actions',json={'version':1,'action':'approve','comment':'Authority register checked'}).status_code==200
    result=client.get('/api/workforce/establishments').json()[0];assert result['filled']==1 and result['vacancies']==2
    as_role(client,'employee');assert client.get('/api/workforce/establishments').status_code==403
    as_role(client,'platform_admin');assert client.get('/api/workforce/attendance',params={'start':str(date.today()),'end':str(date.today())}).status_code==403

def test_retirement_policy_no_default_and_forecast(client,world):
    from datetime import date
    factory,ids=world;as_role(client,'hr_admin')
    assert client.get('/api/workforce/retirement-forecast').json()['configured'] is False
    with factory() as db:
        db.get(Employee,ids['e1']).date_of_birth=date(date.today().year-55,1,1);db.commit()
    policy={'version':0,'reference':'TEST ONLY policy reference','age_years':55,'notice_days':90}
    assert client.put('/api/workforce/retirement-policy',json=policy).status_code==200
    assert client.put('/api/workforce/retirement-policy',json=policy).status_code==409
    result=client.get('/api/workforce/retirement-forecast').json();assert result['items'][0]['employee_id']==ids['e1'] and result['items'][0]['review_required'] and result['missing_dates']==1
    as_role(client,'facility_head');assert client.get('/api/workforce/retirement-forecast').status_code==403

def test_appraisal_self_access_and_malformed_edit(client,world):
    factory,ids=world
    with factory() as db:
        reviewer=db.query(User).filter(User.role=='facility_head').one().id
        db.query(User).filter(User.role=='employee').one().employee_id=None;db.flush()
        db.query(User).filter(User.role=='hr_admin').one().employee_id=ids['e1'];db.commit()
    as_role(client,'hr_admin');r=create(client,world,'appraisal',reviewer)
    assert client.get('/api/workforce/records?kind=appraisal').json()['total']==0
    as_role(client,'facility_head')
    assert client.put('/api/workforce/records/'+r['id'],json={'version':1,'title':'Invalid test edit','start_date':r['start_date'],'end_date':r['end_date'],'data':{'unexpected':'field'}}).status_code==422
    assert client.put('/api/workforce/records/'+r['id'],json={'version':1,'title':'Valid test edit','start_date':r['start_date'],'end_date':r['end_date'],'data':{'objectives':'Test objectives','assessment':'Reviewed result'}}).status_code==200

def test_roster_leave_conflicts_in_both_directions(client,world):
    from app.phase2_models import Case
    from app.models import uid
    factory,ids=world;day=str(date.today());as_role(client,'facility_head')
    payload={'employee_id':ids['e1'],'starts_at':day+'T08:00:00Z','ends_at':day+'T16:00:00Z','duty':'Test duty'}
    shift=client.post('/api/workforce/roster',json=payload).json()
    with factory() as db:
        creator=db.query(User).filter(User.role=='employee').one().id
        row=Case(kind='leave',employee_id=ids['e1'],reference=uid(),title='Test leave',body='Test',created_by=creator,start_date=date.today(),end_date=date.today(),status='approved',final_role='director');db.add(row);db.commit();cid=row.id
    assert client.post('/api/workforce/roster/'+shift['id']+'/actions',json={'action':'publish','version':1,'comment':'Test publication'}).status_code==409
    with factory() as db:db.get(Case,cid).status='hr_validated';db.commit()
    assert client.post('/api/workforce/roster/'+shift['id']+'/actions',json={'action':'publish','version':1,'comment':'Test publication'}).status_code==200
    as_role(client,'director');assert client.post('/api/cases/'+cid+'/actions',json={'action':'approve','version':1,'comment':'Test leave decision'}).status_code==409

def test_correction_cannot_be_self_verified(client,world):
    _,ids=world;as_role(client,'employee');p={'employee_id':ids['e1'],'day':str(date.today()),'outcome':'present','note':'Manual test record'}
    r=client.put('/api/workforce/attendance',json=p).json()
    as_role(client,'hr_officer');r=client.put('/api/workforce/attendance',json={**p,'version':1,'outcome':'late'}).json()
    assert client.post('/api/workforce/attendance/'+r['id']+'/actions',json={'version':2,'action':'verify','comment':'Cannot verify own correction'}).status_code==403
    as_role(client,'hr_admin');assert client.post('/api/workforce/attendance/'+r['id']+'/actions',json={'version':2,'action':'verify','comment':'Independent review completed'}).status_code==200
