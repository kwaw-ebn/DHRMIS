import os
os.environ['COOKIE_SECURE']='false'
os.environ['DATABASE_URL']='sqlite://'
os.environ['MFA_ENCRYPTION_KEY']='MDAwMDAwMDAwMDAwMDAwMDAwMDAwMDAwMDAwMDAwMDA='
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from fastapi.testclient import TestClient
from app.db import Base,get_db
from app.models import Unit,Employee,User,Setting,Assignment,Session as LoginSession
from app.security import ph,digest
from app.main import app
from app import phase2_models
from datetime import datetime,timedelta,timezone
import json

@pytest.fixture
def world():
    engine=create_engine('sqlite://',connect_args={'check_same_thread':False},poolclass=StaticPool)
    Base.metadata.create_all(engine);factory=sessionmaker(engine,expire_on_commit=False)
    with factory() as db:
        org=Unit(name='GHS',kind='organization');db.add(org);db.flush()
        district=Unit(name='District',kind='district',parent_id=org.id);db.add(district);db.flush()
        a=Unit(name='Facility A',kind='facility',category='CHPS',parent_id=district.id);b=Unit(name='Facility B',kind='facility',category='CHPS',parent_id=district.id);db.add_all([a,b]);db.flush()
        e1=Employee(staff_id='SH-1',full_name='Person One',job_title='Nurse',cadre='Nurse',grade='Pilot A',unit_id=a.id,ghs_number='GHS-1',payroll_number='PAY-1')
        e2=Employee(staff_id='SH-2',full_name='Person Two',job_title='Nurse',cadre='Nurse',grade='Pilot A',unit_id=b.id);db.add_all([e1,e2]);db.flush()
        from datetime import date
        db.add_all([Assignment(employee_id=e1.id,unit_id=a.id,effective_date=date(2020,1,1),reason='Initial test assignment'),Assignment(employee_id=e2.id,unit_id=b.id,effective_date=date(2020,1,1),reason='Initial test assignment')])
        for role,unit,eid in [('hr_admin',None,None),('hr_officer',None,None),('director',None,None),('facility_head',a.id,None),('employee',None,e1.id),('auditor',None,None),('platform_admin',None,None)]:
            u=User(email=role+'@example.com',name=role,password_hash=ph.hash('StrongPilotPassword1!'),role=role,unit_id=unit,employee_id=eid,must_change_password=False)
            db.add(u);db.flush();db.add(LoginSession(id=digest(role),user_id=u.id,expires_at=datetime.now(timezone.utc)+timedelta(hours=1),authenticated=True,csrf_token='test-csrf'))
        db.add_all([Setting(key='cadres',value=json.dumps(['Nurse'])),Setting(key='grades',value=json.dumps(['Pilot A']))]);db.commit()
        ids={'a':a.id,'b':b.id,'e1':e1.id,'e2':e2.id,'district':district.id}
    def override():
        with factory() as db:yield db
    app.dependency_overrides[get_db]=override
    yield factory,ids
    app.dependency_overrides.clear();engine.dispose()

@pytest.fixture
def client(world):
    with TestClient(app) as c:yield c

def as_role(client,role):
    client.cookies.set('staffhub_session',role);client.headers['x-csrf-token']='test-csrf';return client
