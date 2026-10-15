"""Workforce administration. No automated employment or eligibility decisions."""
import json
from datetime import date, timedelta
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import or_, update, func
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError
from pydantic import ValidationError
from .db import get_db
from .models import Employee, User, Unit, Setting
from .security import current_user, allow, audit, staff_query, HR, SCOPED, descendants, utc
from .phase2 import require_employee, is_self
from .phase2_models import Case, Notification
from .phase3_models import WorkforceRecord, WorkforceEvent, DutyShift, Attendance, Establishment
from .phase3_schemas import RecordInput, RecordEdit, Action, ShiftInput, AttendanceInput, EstablishmentInput

router=APIRouter(prefix='/api/workforce',tags=['Phase 3 workforce management'])
MANAGERS=HR|SCOPED
READERS=MANAGERS|{'employee','director'}

def flush(db):
    try:db.flush()
    except IntegrityError:
        db.rollback();raise HTTPException(409,'A conflicting record already exists; reload before retrying')

def commit(db):
    try:db.commit()
    except IntegrityError:
        db.rollback();raise HTTPException(409,'A conflicting record already exists; reload before retrying')

def cas(db,model,row,version,values):
    if row.version!=version:raise HTTPException(409,'This record changed; reload and review before retrying')
    count=db.execute(update(model).where(model.id==row.id,model.version==version).values(**values,version=version+1).execution_options(synchronize_session=False)).rowcount
    if count!=1:raise HTTPException(409,'This record changed; reload and review before retrying')
    db.expire(row);db.refresh(row)

def employee_lock(db,user,eid):
    e=require_employee(db,user,eid)
    return db.query(Employee).filter(Employee.id==e.id).with_for_update().populate_existing().one()

def query_records(db,user,kind):
    allow(user,READERS)
    if kind not in {'training','promotion','retirement','appraisal'}:raise HTTPException(400,'Unknown workforce module')
    q=db.query(WorkforceRecord).filter(WorkforceRecord.kind==kind,WorkforceRecord.employee_id.in_(staff_query(db,user).with_entities(Employee.id)))
    if kind=='appraisal':
        own_ids=db.query(Employee.id).filter(or_(Employee.id==user.employee_id,func.lower(Employee.email)==user.email.lower()))
        q=q.filter(or_(WorkforceRecord.employee_id.notin_(own_ids),WorkforceRecord.status.in_(['released','acknowledged'])))
        if user.role=='employee':q=q.filter(WorkforceRecord.status.in_(['released','acknowledged']))
        elif user.role not in HR:q=q.filter(WorkforceRecord.reviewer_id==user.id)
    return q

def record_view(db,user,row):
    result={k:getattr(row,k) for k in ['id','kind','employee_id','title','start_date','end_date','status','reviewer_id','created_by','version','created_at','updated_at']}
    result['employee_name']=db.get(Employee,row.employee_id).full_name
    result['data']=json.loads(row.data)
    result['history']=[{'action':e.action,'comment':e.comment,'created_at':e.created_at} for e in db.query(WorkforceEvent).filter(WorkforceEvent.record_id==row.id).order_by(WorkforceEvent.created_at)]
    return result

def log_event(db,user,row,action,comment):
    db.add(WorkforceEvent(record_id=row.id,actor_id=user.id,action=action,comment=comment))
    audit(db,user,'WORKFORCE_'+action.upper(),row.id,detail=row.kind)
    # Appraisal notifications never contain assessment text or scores.
    if row.kind!='appraisal' or row.status in {'released','acknowledged'}:
        for u in db.query(User).filter(User.employee_id==row.employee_id,User.active==True):
            db.add(Notification(user_id=u.id,title='A workforce administration record has been updated'))

@router.get('/reviewers')
def reviewers(db:Session=Depends(get_db),user:User=Depends(current_user)):
    allow(user,HR)
    return [{'id':u.id,'name':u.name,'role':u.role} for u in db.query(User).filter(User.active==True,User.role.in_(list(MANAGERS|{'director'})))]

@router.get('/records')
def records(kind:str,page:int=Query(1,ge=1),page_size:int=Query(50,ge=1,le=100),db:Session=Depends(get_db),user:User=Depends(current_user)):
    q=query_records(db,user,kind);total=q.count()
    rows=q.order_by(WorkforceRecord.created_at.desc(),WorkforceRecord.id).offset((page-1)*page_size).limit(page_size).all()
    audit(db,user,'WORKFORCE_READ',detail=kind);commit(db)
    return {'items':[record_view(db,user,r) for r in rows],'total':total}

@router.post('/records',status_code=201)
def create_record(data:RecordInput,db:Session=Depends(get_db),user:User=Depends(current_user)):
    allow(user,READERS if data.kind=='training' else HR)
    e=employee_lock(db,user,data.employee_id)
    if data.kind=='appraisal':
        if data.data.get('assessment'):raise HTTPException(400,'The assigned reviewer completes the assessment after creation')
        reviewer=db.get(User,data.reviewer_id) if data.reviewer_id else None
        if not reviewer or not reviewer.active or reviewer.role not in MANAGERS|{'director'}:raise HTTPException(400,'Assign an active authorized reviewer')
        if is_self(reviewer,e):raise HTTPException(400,'An employee cannot review their own appraisal')
        if reviewer.role in SCOPED and e.unit_id not in descendants(db,reviewer.unit_id):raise HTTPException(400,'Reviewer is outside the staff reporting scope')
        overlap=db.query(WorkforceRecord).filter(WorkforceRecord.kind=='appraisal',WorkforceRecord.employee_id==e.id,WorkforceRecord.status!='cancelled',WorkforceRecord.start_date<=data.end_date,WorkforceRecord.end_date>=data.start_date).first()
        if overlap:raise HTTPException(409,'An appraisal already covers part of this period')
    elif data.reviewer_id:raise HTTPException(400,'Reviewer assignment applies only to appraisals')
    if data.kind=='training' and data.end_date>date.today():raise HTTPException(400,'Record completed training after its end date')
    if data.kind=='promotion':
        grades=db.get(Setting,'grades')
        if not grades or data.data['target_grade'] not in json.loads(grades.value):raise HTTPException(400,'Select an HR-configured target grade')
    row=WorkforceRecord(**data.model_dump(exclude={'data'}),data=json.dumps(data.data),created_by=user.id)
    db.add(row);flush(db);log_event(db,user,row,'created','Workforce record created');commit(db)
    return record_view(db,user,row)

@router.put('/records/{rid}')
def edit_record(rid:str,data:RecordEdit,db:Session=Depends(get_db),user:User=Depends(current_user)):
    row=db.get(WorkforceRecord,rid)
    if not row:raise HTTPException(404,'Record not found')
    row=query_records(db,user,row.kind).filter(WorkforceRecord.id==rid).first()
    if not row:raise HTTPException(404,'Record not found in your scope')
    if row.status!='draft':raise HTTPException(409,'Only draft records can be edited')
    if row.kind=='appraisal':
        if user.id!=row.reviewer_id:raise HTTPException(403,'Only the assigned reviewer can write the assessment')
    elif user.id!=row.created_by and user.role not in HR:raise HTTPException(403,'You cannot edit this record')
    try:validated=RecordInput(kind=row.kind,employee_id=row.employee_id,reviewer_id=row.reviewer_id,**data.model_dump(exclude={'version'}))
    except ValidationError:raise HTTPException(422,'Invalid record fields or date range')
    if row.kind=='appraisal' and (validated.start_date!=row.start_date or validated.end_date!=row.end_date):raise HTTPException(400,'Appraisal periods are immutable; cancel and create the correct period')
    cas(db,WorkforceRecord,row,data.version,{'title':validated.title,'start_date':validated.start_date,'end_date':validated.end_date,'data':json.dumps(validated.data)})
    log_event(db,user,row,'edited','Draft updated');commit(db);return record_view(db,user,row)

@router.post('/records/{rid}/actions')
def record_action(rid:str,data:Action,db:Session=Depends(get_db),user:User=Depends(current_user)):
    base=db.get(WorkforceRecord,rid)
    if not base:raise HTTPException(404,'Record not found')
    row=query_records(db,user,base.kind).filter(WorkforceRecord.id==rid).with_for_update().populate_existing().first()
    if not row:raise HTTPException(404,'Record not found in your scope')
    e=employee_lock(db,user,row.employee_id);self_action=is_self(user,e);values={};payload=json.loads(row.data)
    if row.kind=='appraisal':
        if data.action=='submit' and row.status=='draft':
            if user.id!=row.reviewer_id:raise HTTPException(403,'Only the assigned reviewer may submit')
            if not payload.get('assessment','').strip():raise HTTPException(400,'Complete the assessment before submitting')
            target='submitted'
        elif data.action=='release' and row.status=='submitted':
            allow(user,HR)
            if self_action or user.id==row.reviewer_id:raise HTTPException(403,'A separate HR officer must release this appraisal')
            target='released'
        elif data.action=='return' and row.status=='submitted':
            allow(user,HR)
            if self_action or user.id==row.reviewer_id:raise HTTPException(403,'A separate HR officer must return this appraisal')
            target='draft'
        elif data.action=='cancel' and row.status=='draft':
            allow(user,HR);target='cancelled'
        elif data.action=='acknowledge' and row.status=='released':
            if not self_action:raise HTTPException(403,'Only the employee may acknowledge their appraisal')
            target='acknowledged'
        else:raise HTTPException(409,'Action is not available in this state')
    elif data.action=='submit' and row.status=='draft':
        if user.id!=row.created_by and user.role not in HR:raise HTTPException(403,'Only the creator or HR may submit')
        if row.kind=='training' and row.end_date>date.today():raise HTTPException(400,'Training has not ended')
        target='submitted'
    elif data.action in {'verify','approve','reject'} and row.status=='submitted':
        if row.kind!='training' and not payload.get('final_role'):raise HTTPException(409,'This legacy record has no authorized final role; HR review is required')
        allow(user,HR if row.kind=='training' else {payload['final_role']})
        if self_action or user.id==row.created_by:raise HTTPException(403,'A separate officer must record this decision')
        if (data.action=='verify' and row.kind!='training') or (data.action=='approve' and row.kind=='training'):raise HTTPException(400,'Invalid decision for this module')
        target='rejected' if data.action=='reject' else 'verified' if row.kind=='training' else 'approved'
    elif data.action=='checklist' and row.kind=='retirement' and row.status=='approved':
        allow(user,HR)
        if data.completed_items is None or not set(data.completed_items).issubset(payload['checklist']):raise HTTPException(400,'Select valid checklist items')
        payload['completed_items']=list(dict.fromkeys(data.completed_items));values['data']=json.dumps(payload);target='approved'
    elif data.action=='complete' and row.kind=='retirement' and row.status=='approved':
        allow(user,HR)
        if self_action:raise HTTPException(403,'An employee cannot complete their own exit')
        if date.today()<row.end_date:raise HTTPException(409,'The approved exit date has not arrived')
        if set(payload.get('completed_items',[]))!=set(payload['checklist']):raise HTTPException(409,'Complete all approved exit checklist items first')
        target='completed'
    elif data.action=='cancel' and row.status=='draft':
        if user.id!=row.created_by and user.role not in HR:raise HTTPException(403,'Only the creator or HR may cancel')
        target='cancelled'
    else:raise HTTPException(409,'Action is not available in this state')
    values['status']=target;cas(db,WorkforceRecord,row,data.version,values)
    log_event(db,user,row,data.action,data.comment);commit(db);return record_view(db,user,row)

@router.get('/roster')
def roster(start:date,end:date,db:Session=Depends(get_db),user:User=Depends(current_user)):
    allow(user,READERS)
    if end<start or (end-start).days>93:raise HTTPException(400,'Select at most 93 days')
    q=db.query(DutyShift).filter(DutyShift.employee_id.in_(staff_query(db,user).with_entities(Employee.id)),DutyShift.starts_at<end+timedelta(days=1),DutyShift.ends_at>=start)
    if user.role=='employee':q=q.filter(DutyShift.status=='published')
    rows=q.order_by(DutyShift.starts_at).limit(1000).all();audit(db,user,'ROSTER_READ');commit(db)
    return [shift_view(db,r) for r in rows]
def shift_view(db,r):
    return {k:getattr(r,k) for k in ['id','employee_id','unit_id','starts_at','ends_at','duty','status','version']}|{'employee_name':db.get(Employee,r.employee_id).full_name}

@router.post('/roster',status_code=201)
def add_shift(data:ShiftInput,db:Session=Depends(get_db),user:User=Depends(current_user)):
    allow(user,MANAGERS);e=employee_lock(db,user,data.employee_id)
    if db.query(DutyShift).filter(DutyShift.employee_id==e.id,DutyShift.status!='cancelled',DutyShift.starts_at<data.ends_at,DutyShift.ends_at>data.starts_at).first():raise HTTPException(409,'This shift overlaps an existing shift')
    row=DutyShift(**data.model_dump(),unit_id=e.unit_id,created_by=user.id);db.add(row);flush(db);audit(db,user,'SHIFT_CREATED',row.id);commit(db);return shift_view(db,row)

@router.post('/roster/{rid}/actions')
def shift_action(rid:str,data:Action,db:Session=Depends(get_db),user:User=Depends(current_user)):
    allow(user,MANAGERS);row=db.get(DutyShift,rid)
    if not row:raise HTTPException(404,'Shift not found')
    e=employee_lock(db,user,row.employee_id)
    if data.action=='publish' and row.status=='draft':
        first=utc(row.starts_at).date();last=(utc(row.ends_at)-timedelta(microseconds=1)).date()
        if db.query(Case).filter(Case.kind=='leave',Case.employee_id==e.id,Case.status.in_(['approved','in_progress','return_reported','cancellation_requested']),Case.start_date<=last,Case.end_date>=first).first():raise HTTPException(409,'The shift conflicts with approved leave')
        target='published'
    elif data.action=='cancel' and row.status in {'draft','published'}:target='cancelled'
    else:raise HTTPException(409,'Action is not available in this state')
    cas(db,DutyShift,row,data.version,{'status':target});audit(db,user,'SHIFT_'+target.upper(),rid,detail=data.comment);commit(db);return shift_view(db,row)

@router.get('/attendance')
def attendance(start:date,end:date,db:Session=Depends(get_db),user:User=Depends(current_user)):
    allow(user,READERS)
    if end<start or (end-start).days>93:raise HTTPException(400,'Select at most 93 days')
    rows=db.query(Attendance).filter(Attendance.employee_id.in_(staff_query(db,user).with_entities(Employee.id)),Attendance.day>=start,Attendance.day<=end).order_by(Attendance.day.desc()).limit(1000).all()
    audit(db,user,'ATTENDANCE_READ');commit(db)
    return [attendance_view(db,r) for r in rows]
def attendance_view(db,r):
    return {k:getattr(r,k) for k in ['id','employee_id','day','outcome','note','status','version','created_by','verified_by']}|{'employee_name':db.get(Employee,r.employee_id).full_name}

@router.put('/attendance')
def save_attendance(data:AttendanceInput,db:Session=Depends(get_db),user:User=Depends(current_user)):
    allow(user,MANAGERS|{'employee'});e=employee_lock(db,user,data.employee_id)
    if data.day>date.today():raise HTTPException(400,'Cannot record attendance for a future date')
    row=db.query(Attendance).filter(Attendance.employee_id==e.id,Attendance.day==data.day).first()
    if row:
        if data.version==0 or row.version!=data.version:raise HTTPException(409,'Attendance already exists or has changed; reload and explicitly reconcile your entry')
        if row.status=='verified':raise HTTPException(409,'Ask an authorized officer to reopen verified attendance with a reason')
        if user.role=='employee' and row.created_by!=user.id:raise HTTPException(403,'You cannot overwrite an officer-recorded entry')
        cas(db,Attendance,row,data.version,{'outcome':data.outcome,'note':data.note,'status':'submitted','verified_by':None,'created_by':user.id})
    else:
        if data.version:raise HTTPException(409,'The original attendance entry no longer exists')
        row=Attendance(**data.model_dump(exclude={'version'}),created_by=user.id);db.add(row);db.flush()
    audit(db,user,'ATTENDANCE_RECORDED',row.id,detail='Manual entry; not proof of physical presence');commit(db);return attendance_view(db,row)

@router.post('/attendance/{rid}/actions')
def attendance_action(rid:str,data:Action,db:Session=Depends(get_db),user:User=Depends(current_user)):
    allow(user,MANAGERS);row=db.get(Attendance,rid)
    if not row:raise HTTPException(404,'Attendance not found')
    e=employee_lock(db,user,row.employee_id)
    if is_self(user,e) or user.id==row.created_by:raise HTTPException(403,'Verification requires a separate officer')
    if data.action=='verify' and row.status=='submitted':values={'status':'verified','verified_by':user.id}
    elif data.action=='reopen' and row.status=='verified':values={'status':'submitted','verified_by':None}
    else:raise HTTPException(409,'Action is not available in this state')
    cas(db,Attendance,row,data.version,values);audit(db,user,'ATTENDANCE_'+data.action.upper(),rid,detail=data.comment);commit(db);return attendance_view(db,row)

@router.get('/establishments')
def establishments(db:Session=Depends(get_db),user:User=Depends(current_user)):
    allow(user,MANAGERS|{'director'});q=db.query(Establishment)
    if user.role in SCOPED:q=q.filter(Establishment.unit_id.in_(descendants(db,user.unit_id)))
    result=[]
    for row in q.order_by(Establishment.cadre).all():
        filled=staff_query(db,user).filter(Employee.unit_id.in_(descendants(db,row.unit_id)),Employee.cadre==row.cadre,Employee.status.notin_(['Retired','Separated','Transferred out','Deceased'])).count()
        effective=row.status=='approved' and row.effective_date<=date.today()
        result.append({k:getattr(row,k) for k in ['id','unit_id','cadre','positions','reference','effective_date','status','version','created_by','final_role']}|{'unit_name':db.get(Unit,row.unit_id).name,'filled':filled,'vacancies':max(0,row.positions-filled) if effective else None,'surplus':max(0,filled-row.positions) if effective else None})
    audit(db,user,'ESTABLISHMENTS_READ');commit(db);return result

@router.post('/establishments',status_code=201)
def create_establishment(data:EstablishmentInput,db:Session=Depends(get_db),user:User=Depends(current_user)):
    allow(user,HR);unit=db.get(Unit,data.unit_id);vocab=db.get(Setting,'cadres')
    if not unit or not unit.active:raise HTTPException(400,'Select an active organizational unit')
    if not vocab or data.cadre not in json.loads(vocab.value):raise HTTPException(400,'Select an HR-configured cadre')
    row=Establishment(**data.model_dump(),created_by=user.id);db.add(row);flush(db);audit(db,user,'ESTABLISHMENT_CREATED',row.id);commit(db);return {'id':row.id,'version':row.version}

@router.post('/establishments/{rid}/actions')
def establishment_action(rid:str,data:Action,db:Session=Depends(get_db),user:User=Depends(current_user)):
    allow(user,HR|{'director'});row=db.get(Establishment,rid)
    if not row:raise HTTPException(404,'Establishment not found')
    if not row.final_role:raise HTTPException(409,'HR must revise this proposal to specify its authorized approval role')
    allow(user,{row.final_role})
    if row.status!='draft' or data.action not in {'approve','reject'}:raise HTTPException(409,'Action is not available in this state')
    if row.created_by==user.id:raise HTTPException(403,'A separate officer must approve the establishment')
    cas(db,Establishment,row,data.version,{'status':'approved' if data.action=='approve' else 'rejected','approved_by':user.id})
    audit(db,user,'ESTABLISHMENT_'+data.action.upper(),rid,detail=data.comment);commit(db);return {'id':rid,'status':row.status,'version':row.version}

@router.put('/establishments/{rid}')
def revise_establishment(rid:str,data:EstablishmentInput,version:int=Query(ge=1),db:Session=Depends(get_db),user:User=Depends(current_user)):
    allow(user,HR);row=db.get(Establishment,rid)
    if not row:raise HTTPException(404,'Establishment not found')
    if row.status not in {'draft','rejected'}:raise HTTPException(409,'Approved establishments are immutable in this pilot; amendments require a reviewed migration')
    if data.unit_id!=row.unit_id or data.cadre!=row.cadre:raise HTTPException(400,'Unit and cadre are immutable')
    cas(db,Establishment,row,version,{'positions':data.positions,'reference':data.reference,'effective_date':data.effective_date,'status':'draft','approved_by':None,'created_by':user.id,'final_role':data.final_role})
    audit(db,user,'ESTABLISHMENT_REVISED',rid);commit(db);return {'id':rid,'version':row.version}

from .phase3_schemas import RetirementPolicy
@router.get('/retirement-policy')
def retirement_policy(db:Session=Depends(get_db),user:User=Depends(current_user)):
    allow(user,HR|{'director'});row=db.get(Setting,'retirement_policy')
    return json.loads(row.value) if row else {'version':0,'reference':'','age_years':None,'notice_days':None}

@router.put('/retirement-policy')
def save_retirement_policy(data:RetirementPolicy,db:Session=Depends(get_db),user:User=Depends(current_user)):
    allow(user,{'hr_admin'});row=db.query(Setting).filter(Setting.key=='retirement_policy').with_for_update().populate_existing().first()
    current=json.loads(row.value) if row else {'version':0}
    if data.version!=current['version']:raise HTTPException(409,'Policy changed; reload before saving')
    value=data.model_dump();value['version']+=1
    if row:row.value=json.dumps(value)
    else:db.add(Setting(key='retirement_policy',value=json.dumps(value)))
    audit(db,user,'RETIREMENT_POLICY_CONFIGURED',detail=data.reference);commit(db);return value

@router.get('/retirement-forecast')
def retirement_forecast(days:int=Query(365,ge=1,le=3650),db:Session=Depends(get_db),user:User=Depends(current_user)):
    allow(user,HR|{'director'});row=db.get(Setting,'retirement_policy')
    if not row:return {'configured':False,'items':[],'missing_dates':None}
    policy=json.loads(row.value);items=[];missing=0;cutoff=date.today()+timedelta(days=days)
    for e in staff_query(db,user).filter(Employee.status.notin_(['Retired','Separated','Transferred out','Deceased'])):
        if not e.date_of_birth:missing+=1;continue
        year=e.date_of_birth.year+policy['age_years']
        try:expected=e.date_of_birth.replace(year=year)
        except ValueError:expected=date(year,2,28)
        if expected<=cutoff:items.append({'employee_id':e.id,'employee_name':e.full_name,'indicative_date':expected,'notice_due':expected-timedelta(days=policy['notice_days']),'review_required':True})
    audit(db,user,'RETIREMENT_FORECAST_READ');commit(db)
    return {'configured':True,'policy_reference':policy['reference'],'items':sorted(items,key=lambda i:i['indicative_date']),'missing_dates':missing,'note':'Indicative dates only. Officers must validate applicable rules, exceptions and official dates.'}
