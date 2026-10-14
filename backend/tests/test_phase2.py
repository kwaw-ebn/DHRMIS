from datetime import date,timedelta
from conftest import as_role
from app.models import Employee,Assignment,User
from app.phase2_models import Case,DocumentVersion

def policy(client,world,balance=True,basis='calendar',days=None):
    _,ids=world;as_role(client,'hr_admin')
    r=client.post('/api/leave/policies',json={'name':'Pilot test leave','reference':'Synthetic testing policy, not GHS policy','requires_balance':balance,'count_basis':basis,'working_days':days or list(range(7)),'final_role':'director'})
    assert r.status_code==201,r.text
    pid=r.json()['id']
    if balance:
        r=client.post('/api/leave/balances',json={'employee_id':ids['e1'],'policy_id':pid,'year':date.today().year,'granted':20,'note':'Synthetic allocation for workflow testing'})
        assert r.status_code==200,r.text
    return pid

def leave(client,world,pid,start=None,end=None):
    _,ids=world;as_role(client,'employee');start=start or date.today();end=end or start+timedelta(days=2)
    r=client.post('/api/leave/requests',json={'employee_id':ids['e1'],'policy_id':pid,'start_date':str(start),'end_date':str(end),'reason':'Synthetic annual leave test'})
    assert r.status_code==201,r.text
    return r.json()

def action(client,row,role,name,comment='Recorded synthetic decision',expected=200):
    as_role(client,role);r=client.post('/api/cases/'+row['id']+'/actions',json={'action':name,'version':row['version'],'comment':comment})
    assert r.status_code==expected,r.text
    return r.json() if expected==200 else row

def approve(client,row):
    row=action(client,row,'facility_head','recommend');row=action(client,row,'hr_officer','validate');return action(client,row,'director','approve')

def test_leave_reservation_approval_and_return(client,world):
    factory,ids=world;pid=policy(client,world);row=leave(client,world,pid)
    as_role(client,'employee');balance=client.get('/api/leave/balances').json()[0];assert balance['reserved']==3 and balance['available']==17
    row=approve(client,row);as_role(client,'hr_admin');balance=client.get('/api/leave/balances').json()[0];assert balance['used']==3 and balance['reserved']==0
    row=action(client,row,'facility_head','start_leave')
    with factory() as db:assert db.get(Employee,ids['e1']).status=='On approved leave'
    row=action(client,row,'employee','report_return');row=action(client,row,'facility_head','confirm_return');assert row['status']=='completed'
    with factory() as db:assert db.get(Employee,ids['e1']).status=='Active'

def test_no_stage_skipping_stale_decision_and_scope(client,world):
    _,ids=world;pid=policy(client,world);row=leave(client,world,pid)
    action(client,row,'director','approve',expected=409)
    action(client,row,'employee','recommend',expected=403)
    row2=action(client,row,'facility_head','recommend');action(client,row,'facility_head','recommend',expected=409)
    as_role(client,'platform_admin');assert client.get('/api/cases').status_code==403
    as_role(client,'employee');assert client.post('/api/leave/requests',json={'employee_id':ids['e2'],'policy_id':pid,'start_date':str(date.today()),'end_date':str(date.today()),'reason':'Not my staff record'}).status_code==404

def test_overlap_insufficient_grant_and_rejection_release(client,world):
    _,ids=world;pid=policy(client,world);row=leave(client,world,pid)
    as_role(client,'employee');data={'employee_id':ids['e1'],'policy_id':pid,'start_date':str(date.today()),'end_date':str(date.today()+timedelta(days=1)),'reason':'Overlapping test'}
    assert client.post('/api/leave/requests',json=data).status_code==409
    as_role(client,'hr_admin');assert client.post('/api/leave/balances',json={'employee_id':ids['e1'],'policy_id':pid,'year':date.today().year,'granted':1,'note':'Invalid reduction test'}).status_code==409
    action(client,row,'facility_head','reject')
    as_role(client,'employee');assert client.get('/api/leave/balances').json()[0]['reserved']==0

def test_approved_cancellation_requires_final_decision(client,world):
    pid=policy(client,world);row=approve(client,leave(client,world,pid))
    action(client,row,'employee','cancel',expected=409)
    row=action(client,row,'employee','request_cancellation');action(client,row,'hr_officer','approve_cancellation',expected=403)
    row=action(client,row,'director','approve_cancellation');assert row['status']=='cancelled'
    as_role(client,'employee');assert client.get('/api/leave/balances').json()[0]['used']==0

def test_cross_year_balance_allocation(client,world):
    _,ids=world;pid=policy(client,world);year=date.today().year
    as_role(client,'hr_admin');assert client.post('/api/leave/balances',json={'employee_id':ids['e1'],'policy_id':pid,'year':year+1,'granted':10,'note':'Next year synthetic test balance'}).status_code==200
    row=leave(client,world,pid,date(year,12,31),date(year+1,1,2));assert row['data']['years']=={str(year):1,str(year+1):2}

def test_holiday_calendar_and_policy_snapshot(client,world):
    pid=policy(client,world,balance=False,basis='working',days=list(range(7)));as_role(client,'hr_admin')
    assert client.post('/api/leave/holidays',json={'day':str(date.today()+timedelta(days=1)),'name':'Synthetic holiday'}).status_code==201
    row=leave(client,world,pid);assert row['days']==2
    as_role(client,'hr_admin');assert client.patch('/api/leave/policies/'+pid,json={'active':False}).status_code==200
    assert client.get('/api/cases/'+row['id']).json()['days']==2

def configure(client):
    as_role(client,'hr_admin');r=client.put('/api/phase2/config',json={'transfer_final_role':'director','policy_reference':'Synthetic pilot workflow authority','letter_heading':'GHS StaffHub — SYNTHETIC PILOT','signatory_name':'Test Signatory','signatory_title':'Pilot officer'});assert r.status_code==200,r.text

def movement(client,world,effective=None):
    _,ids=world;configure(client);as_role(client,'hr_admin');r=client.post('/api/transfers',json={'employee_id':ids['e1'],'target_unit_id':ids['b'],'effective_date':str(effective or date.today()),'movement_type':'Internal transfer','reason':'Synthetic staffing transfer test'});assert r.status_code==201,r.text;return r.json()

def test_movement_acknowledgement_and_assignment_history(client,world):
    factory,ids=world;row=approve(client,movement(client,world))
    action(client,row,'facility_head','acknowledge',expected=403)
    row=action(client,row,'hr_admin','acknowledge');row=action(client,row,'hr_officer','apply');assert row['status']=='applied'
    with factory() as db:
        assert db.get(Employee,ids['e1']).unit_id==ids['b'];assert db.query(Assignment).filter(Assignment.employee_id==ids['e1'],Assignment.end_date==None).count()==1
    as_role(client,'facility_head');assert client.get('/api/employees').json()['total']==0
    action(client,row,'hr_officer','apply',expected=409)

def test_future_movement_cannot_apply_and_creator_cannot_recommend(client,world):
    row=movement(client,world,date.today()+timedelta(days=7));action(client,row,'hr_admin','recommend',expected=403)
    row=approve(client,row);row=action(client,row,'hr_admin','acknowledge');action(client,row,'hr_officer','apply',expected=409)

def test_correspondence_assignment_response_notifications_and_letter(client,world):
    factory,ids=world;configure(client);as_role(client,'employee');r=client.post('/api/administrative-requests',json={'title':'Correction of contact information','body':'Synthetic request details'});assert r.status_code==201;r=r.json()
    with factory() as db:assignee=db.query(User).filter_by(role='hr_officer').one().id
    as_role(client,'hr_admin');r=client.post('/api/cases/'+r['id']+'/actions',json={'action':'assign','version':r['version'],'assigned_to':assignee,'comment':'Assigned for review'}).json()
    r=action(client,r,'hr_officer','respond');r=action(client,r,'hr_officer','close');assert r['status']=='closed'
    as_role(client,'employee');assert client.get('/api/notifications').json();assert client.get('/api/cases/'+r['id']).status_code==200
    as_role(client,'hr_admin');r=client.post('/api/correspondence',json={'title':'Synthetic incoming memorandum','body':'Test memorandum content','direction':'Incoming','correspondent':'Synthetic district office'}).json()
    assert client.get('/api/cases/'+r['id']+'/letter.pdf').content.startswith(b'%PDF-')
    as_role(client,'employee');assert client.get('/api/cases/'+r['id']).status_code==404

def test_document_private_access_versions_and_verification(client,world,monkeypatch):
    _,ids=world
    class Storage:
        def put_object(self,**kwargs):pass
        def generate_presigned_url(self,*args,**kwargs):return 'https://storage.test/signed-document'
    monkeypatch.setattr('app.phase2.storage_client',lambda:Storage())
    as_role(client,'hr_admin');data={'employee_id':ids['e1'],'title':'Synthetic appointment','category':'Appointment letter','employee_visible':'false'}
    r=client.post('/api/documents',data=data,files={'file':('letter.pdf',b'%PDF-1.4\nsynthetic')});assert r.status_code==201,r.text;doc=r.json();vid=doc['versions'][0]['id']
    as_role(client,'employee');assert not client.get('/api/documents').json()['items'];assert client.get(f"/api/documents/{doc['id']}/versions/{vid}/download").status_code==404
    as_role(client,'hr_admin');assert client.patch('/api/documents/'+doc['id'],json={'employee_visible':True}).status_code==200
    data['document_id']=doc['id'];r=client.post('/api/documents',data=data,files={'file':('letter.pdf',b'%PDF-1.4\nversion2')});assert r.status_code==201;assert len(r.json()['versions'])==2
    assert client.patch(f"/api/documents/{doc['id']}/versions/{vid}/verify").status_code==200
    as_role(client,'employee');assert client.get(f"/api/documents/{doc['id']}/versions/{vid}/download").json()['expires_in']==60
    assert client.post('/api/documents',data=data,files={'file':('letter.pdf',b'%PDF-1.4\nnot allowed')}).status_code==403
    as_role(client,'facility_head');assert client.get('/api/documents').status_code==403

def test_invalid_document_signature_is_rejected(client,world):
    _,ids=world;as_role(client,'hr_admin');r=client.post('/api/documents',data={'employee_id':ids['e1'],'title':'Invalid document','category':'Other'},files={'file':('image.pdf',b'<script>not a PDF</script>')});assert r.status_code==400

def test_expiry_reminders_are_scoped_and_deduplicated(client,world,monkeypatch):
    _,ids=world
    class Storage:
        def put_object(self,**kwargs):pass
    monkeypatch.setattr('app.phase2.storage_client',lambda:Storage())
    as_role(client,'hr_admin');r=client.post('/api/documents',data={'employee_id':ids['e2'],'title':'Private licence test','category':'Professional licence','expiry_date':str(date.today()+timedelta(days=7))},files={'file':('licence.pdf',b'%PDF-1.4\nsynthetic')});assert r.status_code==201
    first=client.get('/api/notifications').json();second=client.get('/api/notifications').json();assert len(first)==len(second)==1
    as_role(client,'employee');assert not client.get('/api/notifications').json()

def test_submitter_cannot_final_approve_own_movement(client,world):
    factory,ids=world;configure(client)
    from app.models import Setting
    import json
    with factory() as db:
        config=db.get(Setting,'workflows');data=json.loads(config.value);data['transfer_final_role']='hr_admin';config.value=json.dumps(data);db.commit()
    as_role(client,'hr_admin');r=client.post('/api/transfers',json={'employee_id':ids['e1'],'target_unit_id':ids['b'],'effective_date':str(date.today()),'movement_type':'Internal transfer','reason':'Synthetic self-approval separation test'}).json()
    r=action(client,r,'facility_head','recommend');r=action(client,r,'hr_officer','validate');action(client,r,'hr_admin','approve',expected=403)

def test_calendar_policy_does_not_require_working_weekdays(client,world):
    as_role(client,'hr_admin');data={'name':'Calendar day pilot policy','reference':'Synthetic calendar policy reference','requires_balance':False,'count_basis':'calendar','working_days':[],'final_role':'director'}
    assert client.post('/api/leave/policies',json=data).status_code==201
    data['name']='Working day pilot policy';data['count_basis']='working';assert client.post('/api/leave/policies',json=data).status_code==422
