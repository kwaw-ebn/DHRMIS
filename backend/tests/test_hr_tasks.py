import json
from datetime import date, datetime, timezone, timedelta
from conftest import as_role
from app.models import Employee, User, Setting
from app.phase2_models import Case, LeavePolicy, Holiday, Document, DocumentVersion, Notification
from app.phase3_models import Attendance
from app import hr_tasks
import pytest
TODAY=date(2026,10,20)
@pytest.fixture(autouse=True)
def fixed_today(monkeypatch):monkeypatch.setattr(hr_tasks,'today_local',lambda:TODAY)
def leave(factory,ids,**kwargs):
    with factory() as db:
        creator=db.query(User).filter_by(role='employee').one()
        p=LeavePolicy(name='Annual '+str(db.query(LeavePolicy).count()),reference='Approved rule',requires_balance=False,count_basis='working',working_days='[0,1,2,3,4]',final_role='director');db.add(p);db.flush()
        values=dict(reference='L-'+str(db.query(Case).count()),kind='leave',title='Annual leave',body='Authorized leave',employee_id=ids['e1'],created_by=creator.id,policy_id=p.id,start_date=date(2026,10,1),end_date=date(2026,10,16),days=12,status='in_progress',data='{}');values.update(kwargs)
        c=Case(**values);db.add(c);db.commit();return c.id

def tasks(client,role='hr_admin',**filters):
    r=as_role(client,role).get('/api/hr-tasks',params=filters);assert r.status_code==200,r.text;return r.json()

def test_return_weekends_holidays_and_approved_extensions(world,client):
    factory,ids=world;cid=leave(factory,ids)
    with factory() as db:
        db.add(Holiday(day=date(2026,10,19),name='Configured holiday'));db.commit();assert hr_tasks.expected_return(db,db.get(Case,cid))==TODAY
    t=next(t for t in tasks(client)['items'] if t['kind']=='leave_return');assert t['due_date']=='2026-10-20' and t['priority']=='today' and t['file_number']=='SH-1'
    ext=leave(factory,ids,start_date=TODAY,end_date=date(2026,10,23),status='submitted')
    assert any(t['kind']=='leave_return' for t in tasks(client)['items'])
    with factory() as db:db.get(Case,ext).status='approved';db.commit()
    assert not any(t['kind']=='leave_return' for t in tasks(client)['items'])
    with factory() as db:assert hr_tasks.expected_return(db,db.get(Case,cid))==date(2026,10,26)

def test_ending_overdue_completed_and_scope(world,client):
    factory,ids=world;cid=leave(factory,ids,end_date=date(2026,10,22))
    for role in ['hr_admin','facility_head','employee']:
        assert any(t['kind']=='leave_ending' and t['case_id']==cid for t in tasks(client,role)['items'])
        if role!='hr_admin':assert not any(t['employee_id']==ids['e2'] for t in tasks(client,role)['items'])
    with factory() as db:db.get(Case,cid).end_date=date(2026,10,15);db.commit()
    assert next(t for t in tasks(client)['items'] if t['kind']=='leave_return')['priority']=='overdue'
    with factory() as db:db.get(Case,cid).status='completed';db.commit()
    assert not any(t['case_id']==cid for t in tasks(client)['items'])
    for role in ['platform_admin','auditor']:assert as_role(client,role).get('/api/hr-tasks').status_code==403

def test_return_notifications_deduplicate(world,client):
    factory,ids=world;leave(factory,ids,end_date=date.today()-timedelta(days=10))
    for _ in range(2):assert as_role(client,'employee').get('/api/notifications').status_code==200
    with factory() as db:assert db.query(Notification).filter(Notification.event_key.like('%hr-task:leave_return:%')).count()==1

def test_return_report_without_commencement_and_independent_confirmation(world,client):
    factory,ids=world;cid=leave(factory,ids,status='approved',start_date=date.today()-timedelta(days=4),end_date=date.today()-timedelta(days=1))
    r=as_role(client,'employee').post(f'/api/cases/{cid}/actions',json={'action':'report_return','version':1,'comment':'Returned to duty'});assert r.status_code==200,r.text
    assert r.json()['status']=='return_reported'
    assert any(t['kind']=='return_confirmation' for t in tasks(client)['items'])
    r=as_role(client,'facility_head').post(f'/api/cases/{cid}/actions',json={'action':'confirm_return','version':2,'comment':'Return confirmed'});assert r.status_code==200,r.text
    assert r.json()['status']=='completed'
    with factory() as db:
        assert db.get(Employee,ids['e1']).status=='Active'
        assert 'return_confirmed_date' in json.loads(db.get(Case,cid).data)
    with factory() as db:
        hr=db.query(User).filter_by(role='hr_admin').one();cid2=hr.id
    cid=leave(factory,ids,status='return_reported',created_by=cid2)
    assert as_role(client,'hr_admin').post(f'/api/cases/{cid}/actions',json={'action':'confirm_return','version':1}).status_code==403

def test_rules_review_dates_validation_and_version(world,client):
    factory,ids=world;cfg=as_role(client,'hr_admin').get('/api/hr-tasks/rules').json()['rules']
    assert as_role(client,'employee').put('/api/hr-tasks/rules',json=cfg).status_code==403
    assert as_role(client,'hr_admin').put('/api/hr-tasks/rules',json={**cfg,'return_working_days':[]}).status_code==422
    assert as_role(client,'hr_admin').put('/api/hr-tasks/rules',json={**cfg,'required_fields':['salary']}).status_code==422
    assert as_role(client,'hr_admin').put('/api/hr-tasks/rules',json=cfg).status_code==200
    assert as_role(client,'hr_admin').put('/api/hr-tasks/rules',json=cfg).status_code==409
    payload={'version':0,'probation_date':'2026-10-25','promotion_date':'2026-10-19','reference':'Approved review calendar'}
    assert as_role(client,'hr_officer').put('/api/hr-tasks/review-dates/'+ids['e1'],json=payload).status_code==200
    assert as_role(client,'hr_admin').put('/api/hr-tasks/review-dates/'+ids['e1'],json=payload).status_code==409
    assert as_role(client,'employee').get('/api/hr-tasks/review-dates').status_code==403
    assert len([t for t in tasks(client)['items'] if t['kind'] in {'probation_date','promotion_date'}])==2
    assert not any(t['kind']=='promotion_date' for t in tasks(client,'employee')['items'])
    assert any(t['kind']=='promotion_date' for t in tasks(client,'facility_head')['items'])
    assert tasks(client,kind='promotion_date')['total']==1
    assert as_role(client,'hr_admin').put('/api/hr-tasks/review-dates/'+ids['e1'],json={**payload,'version':1,'probation_date':None,'promotion_date':None}).status_code==200
    assert not any(t['kind'] in {'probation_date','promotion_date'} for t in tasks(client)['items'])

def test_private_documents_latest_version_completeness_and_retirement(world,client):
    factory,ids=world
    with factory() as db:
        uid=db.query(User).filter_by(role='hr_admin').one().id
        d=Document(employee_id=ids['e1'],title='Private licence',category='Professional licence',created_by=uid,employee_visible=False);db.add(d);db.flush()
        for n,expiry in [(1,date(2026,10,10)),(2,date(2028,1,1))]:db.add(DocumentVersion(document_id=d.id,number=n,object_key=f'key{n}',filename='doc.pdf',content_type='application/pdf',size=100,checksum='a'*64,uploaded_by=uid,expiry_date=expiry))
        db.add(Setting(key='retirement_policy',value=json.dumps({'version':1,'age_years':60,'notice_days':90,'reference':'Approved retirement policy'})));db.get(Employee,ids['e1']).date_of_birth=date(1966,11,1);db.commit()
    items=tasks(client)['items'];assert any(t['kind']=='retirement' for t in items);assert not any(t['kind']=='document_expiry' for t in items)
    assert any(t['kind']=='incomplete_file' and 'passport photo' in t['detail'] for t in items)
    with factory() as db:db.query(DocumentVersion).filter_by(number=2).one().expiry_date=TODAY;db.commit()
    assert any(t['kind']=='document_expiry' for t in tasks(client)['items'])
    for role in ['employee','facility_head','director']:assert not any(t['kind']=='document_expiry' for t in tasks(client,role)['items'])
    with factory() as db:db.query(Document).one().employee_visible=True;db.commit()
    assert any(t['kind']=='document_expiry' for t in tasks(client,'employee')['items'])

def test_pending_owner_and_scope(world,client):
    factory,ids=world
    with factory() as db:
        u=db.query(User).filter_by(role='hr_officer').one();db.add(Case(reference='PENDING-1',kind='request',title='Pending request',body='Details',created_by=u.id,assigned_to=u.id,employee_id=ids['e2'],status='assigned',updated_at=datetime(2026,10,1,tzinfo=timezone.utc)));db.commit()
    t=next(t for t in tasks(client)['items'] if t['kind']=='pending_action');assert t['owner']=='hr_officer' and t['priority']=='overdue'
    assert not any(t['kind']=='pending_action' for t in tasks(client,'facility_head')['items'])

def test_monthly_report_counts_review_and_export(world,client):
    factory,ids=world;leave(factory,ids,start_date=date(2026,9,28),end_date=date(2026,10,2),status='completed')
    with factory() as db:
        u=db.query(User).filter_by(role='hr_officer').one()
        db.add_all([Attendance(employee_id=ids['e1'],day=date(2026,9,1),outcome='present',note='Register',status='verified',created_by=u.id),Attendance(employee_id=ids['e1'],day=date(2026,9,2),outcome='absent',note='Unverified',status='submitted',created_by=u.id)])
        db.add(Case(reference='TR-1',kind='transfer',title='Authorized transfer',body='Approved',employee_id=ids['e1'],created_by=u.id,start_date=date(2026,9,15),status='applied'));db.commit()
    r=as_role(client,'hr_admin').get('/api/hr-tasks/monthly-report?month=2026-09');assert r.status_code==200,r.text
    d=r.json();assert d['staffing_total']==2 and d['leave_chargeable_days_in_month']==3 and d['attendance_verified']=={'present':1} and d['attendance_unverified']==1 and d['transfers_applied_effective_in_month']==1
    assert any(t['kind']=='monthly_report' for t in tasks(client)['items'])
    for role in ['employee','facility_head','platform_admin','auditor']:assert as_role(client,role).get('/api/hr-tasks/monthly-report?month=2026-09').status_code==403
    for month in ['2026-13','2026-11','2026-1']:assert as_role(client,'hr_admin').get('/api/hr-tasks/monthly-report?month='+month).status_code==422
    assert as_role(client,'hr_officer').post('/api/hr-tasks/monthly-report/review?month=2026-09',json={'note':'Reviewed with district records'}).status_code==200
    assert not any(t['kind']=='monthly_report' for t in tasks(client)['items'])
    assert as_role(client,'hr_admin').post('/api/hr-tasks/monthly-report/review?month=2026-10',json={'note':'Reviewed with district records'}).status_code==409
    r=as_role(client,'hr_admin').get('/api/hr-tasks/monthly-report.csv?month=2026-09');assert r.status_code==200 and 'attachment' in r.headers['content-disposition'] and 'attendance_verified,present,1' in r.text

def test_custom_workweek_required_files_and_workforce_scope(world,client):
    from app.phase3_models import WorkforceRecord
    factory,ids=world;cid=leave(factory,ids,end_date=date(2026,10,16))
    with factory() as db:
        p=db.get(LeavePolicy,db.get(Case,cid).policy_id);p.working_days='[5]';db.commit()
        assert hr_tasks.expected_return(db,db.get(Case,cid))==date(2026,10,17)
        p.working_days='[]';db.add(Setting(key='hr_automation_rules',value=json.dumps(hr_tasks.Rules(required_documents=['Appointment letter'],return_working_days=[6]).model_dump())));db.commit()
        assert hr_tasks.expected_return(db,db.get(Case,cid))==date(2026,10,18)
        u=db.query(User).filter_by(role='hr_admin').one()
        db.add(WorkforceRecord(kind='promotion',employee_id=ids['e2'],title='Private submitted promotion',start_date=date(2026,1,1),end_date=date(2026,10,1),status='submitted',created_by=u.id,updated_at=datetime(2026,10,1,tzinfo=timezone.utc),data='{"final_role":"director"}'));db.commit()
    assert any('document: Appointment letter' in t['detail'] for t in tasks(client)['items'] if t['kind']=='incomplete_file')
    assert any(t['kind']=='pending_workforce' and t['owner']=='Director' for t in tasks(client)['items'])
    assert not any(t['kind']=='pending_workforce' for t in tasks(client,'facility_head')['items'])
