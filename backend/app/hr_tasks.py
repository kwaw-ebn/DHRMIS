"""Live, scoped in-app HR reminders. No employment decisions or outbound messaging."""
import calendar, csv, io, json
from collections import Counter
from datetime import date, datetime, timedelta, timezone
from fastapi import APIRouter, Depends, HTTPException, Query, Response
from pydantic import BaseModel, ConfigDict, Field, model_validator
from sqlalchemy.orm import Session
from .db import get_db
from .models import Employee, User, Setting
from .security import current_user, allow, audit, staff_query, HR, SCOPED, utc
from .phase2 import case_query, document_query, require_employee, parsed, PENDING, CATEGORIES
from .phase2_models import Case, LeavePolicy, Holiday, Document, DocumentVersion
from .phase3_models import Attendance
from .photos import StaffPhoto

router = APIRouter(prefix='/api/hr-tasks', tags=['HR automation and reminders'])
READERS = HR | SCOPED | {'director', 'employee'}
INACTIVE = {'Retired', 'Separated', 'Transferred out', 'Deceased'}
OPEN_LEAVE = {'approved', 'in_progress', 'return_reported', 'cancellation_requested'}
FIELDS = ['date_of_birth', 'gender', 'phone', 'emergency_contact', 'grade', 'employment_date']

class Rules(BaseModel):
    model_config = ConfigDict(extra='forbid')
    version: int = Field(default=0, ge=0)
    leave_notice_days: int = Field(default=3, ge=0, le=90)
    document_notice_days: int = Field(default=90, ge=0, le=365)
    review_notice_days: int = Field(default=30, ge=0, le=365)
    pending_days: int = Field(default=7, ge=1, le=365)
    return_working_days: list[int] = Field(default_factory=lambda:[0,1,2,3,4], min_length=1, max_length=7)
    required_fields: list[str] = Field(default_factory=lambda:FIELDS.copy(), max_length=len(FIELDS))
    require_photo: bool = True
    required_documents: list[str] = Field(default_factory=list, max_length=len(CATEGORIES))
    @model_validator(mode='after')
    def validate_lists(self):
        if len(set(self.return_working_days))!=len(self.return_working_days) or any(d<0 or d>6 for d in self.return_working_days):raise ValueError('Choose unique weekdays, Monday 0 to Sunday 6')
        if len(set(self.required_fields))!=len(self.required_fields) or set(self.required_fields)-set(FIELDS):raise ValueError('Unsupported required staff field')
        if len(set(self.required_documents))!=len(self.required_documents) or set(self.required_documents)-set(CATEGORIES):raise ValueError('Unsupported required document category')
        return self

class ReviewDates(BaseModel):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True)
    version: int = Field(default=0, ge=0)
    probation_date: date | None = None
    promotion_date: date | None = None
    reference: str = Field(min_length=5, max_length=250)
    assigned_to: str | None = None

class ReportReview(BaseModel):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True)
    note: str = Field(min_length=5, max_length=500)

def today_local():return datetime.now(timezone.utc).date() # Africa/Accra is UTC year-round.
def rules(db):
    row=db.get(Setting,'hr_automation_rules')
    return Rules.model_validate_json(row.value) if row else Rules()

def workdays(policy,cfg):
    selected=parsed(policy.working_days) if policy else []
    return set(selected or cfg.return_working_days)

def next_workday(db, day, weekdays):
    # A bounded window prevents malformed configuration causing a hanging request.
    holidays={h.day for h in db.query(Holiday).filter(Holiday.day>=day,Holiday.day<=day+timedelta(days=370))}
    for offset in range(371):
        candidate=day+timedelta(days=offset)
        if candidate.weekday() in weekdays and candidate not in holidays:return candidate
    raise HTTPException(409,'No return workday found within 370 days. Review the holiday calendar.')

def expected_return(db, row, cfg=None):
    cfg=cfg or rules(db); policy=db.get(LeavePolicy,row.policy_id) if row.policy_id else None
    days=workdays(policy,cfg)
    result=next_workday(db,row.end_date+timedelta(days=1),days)
    # Approved contiguous extensions/other leave suppress a false overdue alert.
    others=db.query(Case).filter(Case.kind=='leave',Case.employee_id==row.employee_id,Case.id!=row.id,Case.status.in_(OPEN_LEAVE)).all()
    for _ in range(len(others)+1):
        covering=[c for c in others if c.start_date and c.end_date and c.start_date<=result<=c.end_date]
        if not covering:return result
        result=next_workday(db,max(c.end_date for c in covering)+timedelta(days=1),days)
    return result

@router.get('/rules')
def get_rules(db:Session=Depends(get_db),user:User=Depends(current_user)):
    allow(user,READERS)
    return {'rules':rules(db).model_dump(),'field_choices':FIELDS,'document_choices':CATEGORIES}

@router.put('/rules')
def put_rules(data:Rules,db:Session=Depends(get_db),user:User=Depends(current_user)):
    allow(user,{'hr_admin'})
    # Serialize all automation configuration updates on an existing shared row.
    db.query(User).filter(User.id==user.id).with_for_update().populate_existing().one()
    row=db.query(Setting).filter(Setting.key=='hr_automation_rules').with_for_update().populate_existing().first()
    current=rules(db)
    if data.version!=current.version:raise HTTPException(409,'Reminder rules changed; reload before saving')
    value=data.model_dump();value['version']+=1
    if row:row.value=json.dumps(value)
    else:db.add(Setting(key='hr_automation_rules',value=json.dumps(value)))
    audit(db,user,'HR_REMINDER_RULES_CONFIGURED');db.commit();return value

@router.get('/review-dates')
def review_dates(db:Session=Depends(get_db),user:User=Depends(current_user)):
    allow(user,HR)
    employees=staff_query(db,user).order_by(Employee.full_name).all()
    schedules={s.key.removeprefix('hr_review:'):json.loads(s.value) for s in db.query(Setting).filter(Setting.key.like('hr_review:%'))}
    return [{'employee_id':e.id,'employee_name':e.full_name,'file_number':e.staff_id,**schedules.get(e.id,{'version':0,'probation_date':None,'promotion_date':None,'reference':'','assigned_to':None})} for e in employees]

@router.put('/review-dates/{eid}')
def save_review(eid:str,data:ReviewDates,db:Session=Depends(get_db),user:User=Depends(current_user)):
    allow(user,HR);require_employee(db,user,eid)
    db.query(Employee).filter(Employee.id==eid).with_for_update().populate_existing().one()
    if data.assigned_to:
        owner=db.get(User,data.assigned_to)
        if not owner or not owner.active or owner.role not in HR:raise HTTPException(400,'Choose an active HR officer')
    key='hr_review:'+eid;row=db.query(Setting).filter(Setting.key==key).with_for_update().populate_existing().first()
    if data.version!=(json.loads(row.value)['version'] if row else 0):raise HTTPException(409,'Review dates changed; reload before saving')
    value=data.model_dump(mode='json');value['version']+=1
    if row:row.value=json.dumps(value)
    else:db.add(Setting(key=key,value=json.dumps(value)))
    audit(db,user,'HR_REVIEW_DATES_CONFIGURED',eid,detail=data.reference);db.commit();return value

def previous_month(today):return (today.replace(day=1)-timedelta(days=1)).strftime('%Y-%m')

def build_tasks(db,user,today):
    allow(user,READERS);cfg=rules(db);items=[];warnings=[]
    employees={e.id:e for e in staff_query(db,user).filter(Employee.status.notin_(INACTIVE))}
    users={u.id:u for u in db.query(User).filter(User.active==True)}
    linked={u.employee_id:u for u in users.values() if u.employee_id}
    def add(kind,key,title,due,eid=None,case=None,target='staff',detail='',owner='HR team'):
        e=employees.get(eid)
        if eid and not e:return
        items.append({'id':kind+':'+key,'kind':kind,'title':title,'due_date':due,'priority':'overdue' if due and due<today else 'today' if due==today else 'upcoming', 'employee_id':eid,'employee_name':e.full_name if e else None,'file_number':e.staff_id if e else None,'case_id':case.id if case else None,'case_version':case.version if case else None,'case_status':case.status if case else None,'target':target,'detail':detail,'owner':owner})
    visible_cases=case_query(db,user).filter(Case.status.notin_(['cancelled','rejected','closed','completed'])).all()
    for c in visible_cases:
        if c.employee_id and c.employee_id not in employees:continue
        owner=users[c.assigned_to].name if c.assigned_to in users else (str(c.final_role).replace('_',' ').title() if c.status in {'hr_validated','cancellation_requested'} and c.final_role else 'Supervisor / HR' if c.status=='submitted' and c.kind in {'leave','transfer'} else 'HR team')
        if c.kind=='leave' and c.status in OPEN_LEAVE and c.end_date:
            returned=expected_return(db,c,cfg);e=employees.get(c.employee_id)
            supervisor=linked.get(e.supervisor_id) if e else None
            responsible=(supervisor.name if supervisor else 'Supervisor / HR')
            if c.status=='return_reported':
                add('return_confirmation',c.id,'Confirm reported return to work',returned,c.employee_id,c,'leave','Return has been reported; an authorized supervisor or HR must confirm it.',responsible)
            elif today>=returned:
                label='Return due today' if today==returned else 'Return overdue — follow up'
                add('leave_return',c.id,label,returned,c.employee_id,c,'leave','Expected return '+str(returned)+'. Check attendance, authorized extensions and the holiday calendar before taking action.',responsible)
            elif c.end_date-timedelta(days=cfg.leave_notice_days)<=today<=c.end_date:
                add('leave_ending',c.id,'Leave ending — prepare to return',c.end_date,c.employee_id,c,'leave','Leave ends '+str(c.end_date)+'; expected return '+str(returned)+'. Based on configured workdays and public holidays.','Staff member + '+responsible)
        if c.kind=='leave' and c.status=='approved' and c.start_date and c.start_date<=today+timedelta(days=cfg.leave_notice_days) and today<=c.end_date:
            add('leave_start',c.id,'Review approved leave commencement',c.start_date,c.employee_id,c,'leave','HR or supervisor must record commencement.','Supervisor / HR')
        if user.role!='employee' and c.status in PENDING|{'assigned','responded','cancellation_requested','acknowledged'}:
            pending_due=utc(c.updated_at).date()+timedelta(days=cfg.pending_days)
            due=min(c.due_date,pending_due) if c.due_date else pending_due
            if due<=today or c.due_date and c.due_date<=today+timedelta(days=cfg.review_notice_days):
                target={'leave':'leave','transfer':'transfers','request':'requests','correspondence':'correspondence'}[c.kind]
                add('pending_action',c.id,'Pending action: '+c.reference,due,c.employee_id,c,target,'Status: '+c.status+'. Review without bypassing the approval workflow.',owner)
        if user.role!='employee' and c.kind=='transfer' and c.status=='applied' and c.end_date and c.end_date<=today+timedelta(days=cfg.review_notice_days):
            add('placement_end',c.id,'Temporary placement ending — review',c.end_date,c.employee_id,c,'transfers','No automatic reassignment.',owner)
    # Private documents are visible only under the existing HR/self document rules.
    if user.role in HR|{'employee'}:
        documents=list(document_query(db,user).filter(Document.employee_id.in_(employees))) if employees else []
        latest={}
        ids=[d.id for d in documents]
        for v in db.query(DocumentVersion).filter(DocumentVersion.document_id.in_(ids)).order_by(DocumentVersion.number.desc()):latest.setdefault(v.document_id,v)
        categories={eid:set() for eid in employees}
        for d in documents:
            v=latest.get(d.id)
            if v:categories[d.employee_id].add(d.category)
            if v and v.expiry_date and v.expiry_date<=today+timedelta(days=cfg.document_notice_days):
                add('document_expiry',v.id,'Document expiry: '+d.title,v.expiry_date,d.employee_id,target='documents',detail='Latest version expires '+str(v.expiry_date)+'. Review and upload the renewed document.')
        if user.role in HR:
            photos={eid for (eid,) in db.query(StaffPhoto.employee_id).filter(StaffPhoto.employee_id.in_(employees)).distinct()}
            for e in employees.values():
                missing=[f.replace('_',' ') for f in cfg.required_fields if not getattr(e,f)]
                if cfg.require_photo and e.id not in photos:missing.append('passport photo')
                missing+=['document: '+cat for cat in cfg.required_documents if cat not in categories[e.id]]
                if missing:add('incomplete_file',e.id,'Complete staff file',today,e.id,detail='Missing '+', '.join(missing)+'.')
                if e.licence_expiry and e.licence_expiry<=today+timedelta(days=cfg.document_notice_days):add('licence_expiry',e.id,'Professional licence expiry',e.licence_expiry,e.id,detail='Recorded licence expiry; verify the renewed licence before updating the file.')
    if user.role in HR|SCOPED|{'director'}:
        from .phase3 import query_records
        for record_kind in ['training','promotion','retirement','appraisal']:
            for record in query_records(db,user,record_kind).filter_by(status='submitted'):
                due=utc(record.updated_at).date()+timedelta(days=cfg.pending_days)
                if due<=today:
                    payload=parsed(record.data)
                    owner=users[record.reviewer_id].name if record.reviewer_id in users else str(payload.get('final_role') or 'HR team').replace('_',' ').title()
                    add('pending_workforce',record.id,'Pending '+record_kind+' review',due,record.employee_id,target=record_kind,detail='Submitted record awaiting authorized review. No approval is applied automatically.',owner=owner)
        scheduled=set()
        for s in db.query(Setting).filter(Setting.key.like('hr_review:%')):
            eid=s.key.removeprefix('hr_review:')
            if eid not in employees:continue
            data=json.loads(s.value);owner=users[data['assigned_to']].name if data.get('assigned_to') in users else 'HR team'
            for key,label in [('probation_date','Probation review'),('promotion_date','Promotion review')]:
                if data.get(key):
                    scheduled.add((eid,key));due=date.fromisoformat(data[key])
                    if due<=today+timedelta(days=cfg.review_notice_days):add(key,eid,label,due,eid,target='promotion' if key=='promotion_date' else 'staff',detail='HR-scheduled review. Reference: '+data['reference']+'. Review eligibility and record the next date; no automatic decision.',owner=owner)
        if user.role in HR:
            missing=sum(1 for eid in employees if not any((eid,key) in scheduled for key in ['probation_date','promotion_date']))
            if missing:warnings.append(f'{missing} staff have no scheduled probation or promotion review date. HR can add applicable dates under Review dates.')
        retirement=db.get(Setting,'retirement_policy')
        if retirement:
            policy=json.loads(retirement.value)
            for e in employees.values():
                if not e.date_of_birth:continue
                year=e.date_of_birth.year+policy['age_years']
                due=e.date_of_birth.replace(year=year,day=min(e.date_of_birth.day,calendar.monthrange(year,e.date_of_birth.month)[1]))
                notice=due-timedelta(days=policy['notice_days'])
                if notice<=today:add('retirement',e.id,'Retirement planning review',notice,e.id,target='retirement',detail='Indicative date '+str(due)+' under '+policy['reference']+'. Validate rules, exceptions and official dates; no automatic retirement.')
        elif user.role in HR|{'director'}:warnings.append('Retirement alerts need an approved retirement policy under Retirement & exit.')
    if user.role in HR|{'director'}:
        month=previous_month(today)
        if not db.get(Setting,'hr_report_review:'+month):add('monthly_report',month,'Review monthly HR report: '+month,today.replace(day=1),target='monthly_report',detail='Prepared from current records; HR must review before institutional use.')
    if not db.query(Holiday).first():warnings.append('No public holidays are configured. Return dates use the selected workweek; HR must maintain the holiday calendar.')
    return sorted(items,key=lambda t:({'overdue':0,'today':1,'upcoming':2}[t['priority']],str(t['due_date']),t['id'])),warnings

@router.get('')
def tasks(kind:str='',priority:str='',page:int=Query(1,ge=1),page_size:int=Query(50,ge=1,le=100),db:Session=Depends(get_db),user:User=Depends(current_user)):
    today=today_local();items,warnings=build_tasks(db,user,today)
    counts=dict(Counter(i['priority'] for i in items));kinds=dict(Counter(i['kind'] for i in items))
    selected=[i for i in items if (not kind or i['kind']==kind) and (not priority or i['priority']==priority)]
    return {'as_of':today,'generated_at':datetime.now(timezone.utc),'items':selected[(page-1)*page_size:page*page_size],'total':len(selected),'counts':counts,'kinds':kinds,'warnings':warnings,'channel':'in_app','refresh_seconds':60}

def report_data(db,user,month):
    allow(user,HR|{'director'})
    try:
        start=date.fromisoformat(month+'-01')
        if start.strftime('%Y-%m')!=month:raise ValueError()
    except ValueError:raise HTTPException(422,'Use YYYY-MM for the report month')
    if start>today_local().replace(day=1):raise HTTPException(422,'Choose the current or a past month')
    end=start.replace(day=calendar.monthrange(start.year,start.month)[1])
    staff=list(staff_query(db,user));ids=[e.id for e in staff]
    leaves=case_query(db,user).filter(Case.kind=='leave',Case.employee_id.in_(ids),Case.start_date<=end,Case.end_date>=start,Case.status.in_(OPEN_LEAVE|{'completed'})).all()
    leave_days=0
    for c in leaves:
        policy=db.get(LeavePolicy,c.policy_id)
        if policy:
            from .phase2 import day_breakdown
            leave_days+=sum(day_breakdown(db,policy,max(start,c.start_date),min(end,c.end_date)).values())
    attendance=db.query(Attendance).filter(Attendance.employee_id.in_(ids),Attendance.day>=start,Attendance.day<=end).all()
    transfers=case_query(db,user).filter(Case.kind=='transfer',Case.employee_id.in_(ids),Case.status=='applied',Case.start_date>=start,Case.start_date<=end).count()
    reviewed=db.get(Setting,'hr_report_review:'+month)
    audit(db,user,'MONTHLY_HR_REPORT_PREPARED',detail=month);db.commit()
    return {'month':month,'generated_at':datetime.now(timezone.utc),'staffing_snapshot_date':today_local(),'staffing_total':len(staff),'staffing_by_status':dict(Counter(e.status for e in staff)),'staffing_by_cadre':dict(Counter(e.cadre for e in staff)), 'leave_requests_overlapping_month':len(leaves),'leave_chargeable_days_in_month':leave_days,'attendance_verified':dict(Counter(a.outcome for a in attendance if a.status=='verified')),'attendance_unverified':sum(a.status!='verified' for a in attendance),'transfers_applied_effective_in_month':transfers,'review':json.loads(reviewed.value) if reviewed else None,'notes':['Staffing is a current snapshot, not reconstructed historical headcount.','Leave days are recalculated for the selected month using the current policy and holiday calendar; original request charges remain unchanged.','Attendance summaries include verified entries only; missing days are not inferred as absence.','Only currently accessible, non-archived staff are included.']}

@router.get('/monthly-report')
def monthly_report(month:str,db:Session=Depends(get_db),user:User=Depends(current_user)):
    return report_data(db,user,month)

@router.get('/monthly-report.csv')
def monthly_csv(month:str,db:Session=Depends(get_db),user:User=Depends(current_user)):
    data=report_data(db,user,month);out=io.StringIO();writer=csv.writer(out);writer.writerow(['Section','Metric','Value'])
    for key,value in data.items():
        if isinstance(value,dict):
            for metric,v in value.items():writer.writerow([key,metric,str(v)])
        elif isinstance(value,list):
            for v in value:writer.writerow([key,'',v])
        else:writer.writerow([key,'',str(value) if value is not None else ''])
    # Prevent spreadsheet formula interpretation of free-text labels.
    raw=out.getvalue();safe=io.StringIO();w=csv.writer(safe)
    for cells in csv.reader(io.StringIO(raw)):w.writerow(["'"+c if c.lstrip().startswith(('=','+','-','@')) else c for c in cells])
    return Response(safe.getvalue(),media_type='text/csv',headers={'Content-Disposition':f'attachment; filename="hr-report-{month}.csv"'})

@router.post('/monthly-report/review')
def mark_report(month:str,data:ReportReview,db:Session=Depends(get_db),user:User=Depends(current_user)):
    allow(user,HR);report_data(db,user,month)
    if month>=today_local().strftime('%Y-%m'):raise HTTPException(409,'Review a completed month')
    db.query(User).filter(User.role=='hr_admin').order_by(User.id).with_for_update().first()
    key='hr_report_review:'+month;row=db.get(Setting,key)
    value={'reviewed_at':datetime.now(timezone.utc).isoformat(),'reviewed_by':user.name,'note':data.note}
    if row:row.value=json.dumps(value)
    else:db.add(Setting(key=key,value=json.dumps(value)))
    audit(db,user,'MONTHLY_HR_REPORT_REVIEWED',detail=month);db.commit();return value
