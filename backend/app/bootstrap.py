import os,json
from datetime import date,timedelta
from .db import SessionLocal
from .models import Unit, Employee, Assignment, User, Setting
from .security import ph

def bootstrap():
    with SessionLocal() as db:
        if db.query(User).first(): return
        email=os.environ.get('ADMIN_EMAIL');password=os.environ.get('ADMIN_PASSWORD')
        if not email or not password or len(password)<12: raise RuntimeError('Set ADMIN_EMAIL and a strong ADMIN_PASSWORD (at least 12 characters) for first startup')
        organization=Unit(name='Ghana Health Service',kind='organization');db.add(organization);db.flush()
        district=Unit(name='Agona East District Health Directorate',kind='district',parent_id=organization.id);db.add(district);db.flush()
        dhd=Unit(name='District Health Directorate',kind='facility',category='DHD',parent_id=district.id);db.add(dhd);db.flush()
        departments=[]
        for name in ['Human Resources and Administration','Nutrition','Public Health','Health Information','Finance and Accounts']:
            dep=Unit(name=name,kind='department',parent_id=dhd.id);db.add(dep);departments.append(dep)
        db.flush()
        cadres=['Nutrition Officer','Nurse','Midwife','Medical Officer','Health Information Officer','Administrative Officer','Community Health Nurse','Disease Control Officer']
        grades=['Pilot Grade A','Pilot Grade B','Pilot Grade C'] if os.getenv('SEED_SYNTHETIC','false').lower()=='true' else ['Senior','Principal','Deputy Chief','Chief']
        db.add_all([Setting(key='cadres',value=json.dumps(cadres)),Setting(key='grades',value=json.dumps(grades)),Setting(key='district_name',value=json.dumps(district.name))])
        db.add(User(email=email.lower(),name='Pilot HR Administrator',password_hash=ph.hash(password),role='hr_admin'))
        if os.getenv('SEED_SYNTHETIC','false').lower()=='true':
            for name in ['Demo North Sub-District','Demo South Sub-District']:
                sub=Unit(name=name,kind='subdistrict',parent_id=district.id);db.add(sub);db.flush()
                for suffix,category in [('Health Centre','Health Centre'),('CHPS','CHPS')]:
                    facility=Unit(name=name.replace('Sub-District','')+suffix,kind='facility',category=category,parent_id=sub.id);db.add(facility);departments.append(facility)
            db.flush()
            for i in range(24):
                emp=Employee(staff_id=f'SH-DEMO-{i+1:03}',full_name=f'Synthetic Staff {i+1:02}',job_title=cadres[i%len(cadres)],cadre=cadres[i%len(cadres)],grade=grades[i%3],unit_id=departments[i%len(departments)].id,employment_date=date(2021+i%4,1,1),status='On approved leave' if i%9==0 else 'Active',verified=i%5!=0,licence_expiry=date.today()+timedelta(days=(i-2)*15) if i%2==0 else None)
                db.add(emp);db.flush();db.add(Assignment(employee_id=emp.id,unit_id=emp.unit_id,effective_date=emp.employment_date,reason='Synthetic pilot seed'))
        db.commit()
if __name__=='__main__':bootstrap()
