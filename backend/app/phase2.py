import io,json,os,secrets,hashlib,re
from datetime import date,timedelta,datetime,timezone
from fastapi import APIRouter,Depends,HTTPException,UploadFile,File,Form,Response
from sqlalchemy.orm import Session
from sqlalchemy import or_,func
from .db import get_db
from .models import Employee,User,Unit,Setting,Assignment,uid
from .phase2_models import LeavePolicy,LeaveBalance,Holiday,Case,Approval,Notification,Document,DocumentVersion
from .phase2_schemas import *
from .security import current_user,allow,audit,staff_query,HR,SCOPED,descendants
router=APIRouter(prefix='/api',tags=['Phase 2 HR administration'])
PENDING={'submitted','recommended','hr_validated'}
CHARGED={'approved','in_progress','return_reported','completed','cancellation_requested'}
OPERATIONS=HR|{'director'}|SCOPED|{'employee'}

def parsed(value):return json.loads(value or '{}')
def config(db):
    row=db.get(Setting,'workflows');return parsed(row.value) if row else {}
def require_employee(db,user,eid):
    row=staff_query(db,user).filter(Employee.id==eid).first()
    if not row:raise HTTPException(404,'Staff record not found in your scope')
    return row

def is_self(user,employee):return user.employee_id==employee.id or bool(employee.email and employee.email.lower()==user.email.lower())
def case_query(db,user):
    allow(user,OPERATIONS)
    query=db.query(Case)
    if user.role in HR or user.role=='director':return query
    if user.role=='employee':
        if not user.employee_id:return query.filter(Case.created_by==user.id)
        return query.filter(or_(Case.created_by==user.id,Case.employee_id==user.employee_id))
    staff_ids=[e.id for e in staff_query(db,user).all()]
    scope=descendants(db,user.unit_id)
    return query.filter(or_(Case.employee_id.in_(staff_ids),Case.created_by==user.id,Case.assigned_to==user.id,(Case.kind=='transfer') & (Case.source_unit_id.in_(scope)),(Case.kind=='transfer') & (Case.target_unit_id.in_(scope)) & Case.status.in_(['approved','acknowledged','applied'])))

def visible_case(db,user,cid,lock=False):
    row=case_query(db,user).filter(Case.id==cid)
    if lock:row=row.with_for_update().populate_existing()
    row=row.first()
    if not row:raise HTTPException(404,'Request not found in your scope')
    return row

def notify(db,row):
    recipients={row.created_by,row.assigned_to}
    if row.employee_id:
        recipients.update(u.id for u in db.query(User).filter(User.employee_id==row.employee_id,User.active==True))
    if row.status in PENDING or row.status=='cancellation_requested':recipients.update(u.id for u in db.query(User).filter(User.role.in_(list(HR|{row.final_role})),User.active==True))
    if row.status=='submitted' and row.employee_id:
        employee=db.get(Employee,row.employee_id)
        for u in db.query(User).filter(User.role.in_(list(SCOPED)),User.active==True):
            if employee.unit_id in descendants(db,u.unit_id):recipients.add(u.id)
    if row.kind=='transfer' and row.status=='approved':
        for u in db.query(User).filter(User.role.in_(list(SCOPED)),User.active==True):
            if row.target_unit_id in descendants(db,u.unit_id):recipients.add(u.id)
    for user_id in recipients-{None}:db.add(Notification(user_id=user_id,case_id=row.id,title='An HR request requires your attention' if row.status in PENDING else 'An HR request has been updated'))

def record(db,user,row,action,comment=''):
    db.add(Approval(case_id=row.id,actor_id=user.id,action=action,comment=comment));audit(db,user,'WORKFLOW_'+action.upper(),row.id);notify(db,row)
def new_case(db,user,kind,title,body,**fields):
    row=Case(kind=kind,title=title,body=body,created_by=user.id,reference='AE-'+kind[:3].upper()+'-'+date.today().strftime('%Y')+'-'+secrets.token_hex(4).upper(),**fields)
    db.add(row);db.flush();record(db,user,row,'submitted');return row

def view_case(db,row):
    result={k:getattr(row,k) for k in ['id','reference','kind','title','body','employee_id','created_by','assigned_to','policy_id','source_unit_id','target_unit_id','start_date','end_date','due_date','days','status','final_role','version','created_at','updated_at']}
    employee=db.get(Employee,row.employee_id) if row.employee_id else None
    result['employee_name']=employee.full_name if employee else None
    result['data']=parsed(row.data)
    result['history']=[{'action':a.action,'actor':db.get(User,a.actor_id).name,'comment':a.comment,'created_at':a.created_at} for a in db.query(Approval).filter(Approval.case_id==row.id).order_by(Approval.created_at)]
    return result

def usage(db,eid,pid,year):
    reserved=used=0
    for row in db.query(Case).filter(Case.kind=='leave',Case.employee_id==eid,Case.policy_id==pid,Case.status.in_(list(PENDING|CHARGED))):
        days=parsed(row.data).get('years',{}).get(str(year),0)
        if row.status in PENDING:reserved+=days
        else:used+=days
    return reserved,used

def day_breakdown(db,policy,start,end):
    holidays={h.day for h in db.query(Holiday).filter(Holiday.day>=start,Holiday.day<=end)}
    workdays=set(parsed(policy.working_days));result={};day=start
    while day<=end:
        if policy.count_basis=='calendar' or (day.weekday() in workdays and day not in holidays):result[str(day.year)]=result.get(str(day.year),0)+1
        day+=timedelta(days=1)
    return result

@router.get('/phase2/config')
def get_config(db:Session=Depends(get_db),user:User=Depends(current_user)):
    allow(user,OPERATIONS)
    return {'workflow':config(db),'policies':[{k:getattr(p,k) for k in ['id','name','reference','requires_balance','count_basis','final_role','active']}|{'working_days':parsed(p.working_days)} for p in db.query(LeavePolicy).order_by(LeavePolicy.name)],'holidays':[{'id':h.id,'day':h.day,'name':h.name} for h in db.query(Holiday).order_by(Holiday.day)],'storage_enabled':bool(os.getenv('AWS_ENDPOINT_URL_S3') and os.getenv('AWS_ACCESS_KEY_ID'))}

@router.put('/phase2/config')
def save_config(data:WorkflowConfig,db:Session=Depends(get_db),user:User=Depends(current_user)):
    allow(user,{'hr_admin'});row=db.get(Setting,'workflows')
    if row:row.value=json.dumps(data.model_dump())
    else:db.add(Setting(key='workflows',value=json.dumps(data.model_dump())))
    audit(db,user,'WORKFLOW_CONFIGURED',detail='Approval authority and institutional letter template');db.commit();return {'ok':True}

@router.post('/leave/policies',status_code=201)
def create_policy(data:PolicyInput,db:Session=Depends(get_db),user:User=Depends(current_user)):
    allow(user,{'hr_admin'});values=data.model_dump();values['working_days']=json.dumps(values['working_days']);row=LeavePolicy(**values);db.add(row);db.flush();audit(db,user,'LEAVE_POLICY_CREATED',row.id);db.commit();return {'id':row.id}

@router.patch('/leave/policies/{pid}')
def toggle_policy(pid:str,data:dict,db:Session=Depends(get_db),user:User=Depends(current_user)):
    allow(user,{'hr_admin'})
    if set(data)!={'active'} or not isinstance(data['active'],bool):raise HTTPException(400,'Provide an active boolean; policy rules are immutable')
    row=db.get(LeavePolicy,pid)
    if not row:raise HTTPException(404,'Policy not found')
    row.active=data['active'];audit(db,user,'LEAVE_POLICY_STATUS',pid);db.commit();return {'ok':True}

@router.post('/leave/holidays',status_code=201)
def holiday(data:HolidayInput,db:Session=Depends(get_db),user:User=Depends(current_user)):
    allow(user,{'hr_admin'});row=Holiday(**data.model_dump());db.add(row);db.flush();audit(db,user,'HOLIDAY_CONFIGURED',row.id);db.commit();return {'id':row.id}

@router.post('/leave/balances')
def grant_balance(data:BalanceInput,db:Session=Depends(get_db),user:User=Depends(current_user)):
    allow(user,HR);require_employee(db,user,data.employee_id)
    db.query(Employee).filter(Employee.id==data.employee_id).with_for_update().populate_existing().one()
    policy=db.get(LeavePolicy,data.policy_id)
    if not policy or not policy.requires_balance:raise HTTPException(400,'Choose a policy that tracks balances')
    reserved,used=usage(db,data.employee_id,data.policy_id,data.year)
    if data.granted<reserved+used:raise HTTPException(409,'Grant cannot fall below used and reserved days')
    row=db.query(LeaveBalance).filter_by(employee_id=data.employee_id,policy_id=data.policy_id,year=data.year).first()
    if row:row.granted=data.granted;row.note=data.note
    else:row=LeaveBalance(**data.model_dump());db.add(row)
    audit(db,user,'LEAVE_BALANCE_SET',data.employee_id,detail=f'Year {data.year}; documented adjustment');db.commit();return {'ok':True}

@router.get('/leave/balances')
def balances(employee_id:str='',db:Session=Depends(get_db),user:User=Depends(current_user)):
    staff=[e.id for e in staff_query(db,user)]
    if employee_id:require_employee(db,user,employee_id);staff=[employee_id]
    result=[]
    for row in db.query(LeaveBalance).filter(LeaveBalance.employee_id.in_(staff)):
        reserved,used=usage(db,row.employee_id,row.policy_id,row.year)
        result.append({'id':row.id,'employee_id':row.employee_id,'employee_name':db.get(Employee,row.employee_id).full_name,'policy_id':row.policy_id,'policy':db.get(LeavePolicy,row.policy_id).name,'year':row.year,'granted':row.granted,'used':used,'reserved':reserved,'available':row.granted-used-reserved,'note':row.note})
    return result

@router.post('/leave/requests',status_code=201)
def request_leave(data:LeaveInput,db:Session=Depends(get_db),user:User=Depends(current_user)):
    allow(user,HR|{'employee'});employee=require_employee(db,user,data.employee_id)
    employee=db.query(Employee).filter(Employee.id==employee.id).with_for_update().populate_existing().one()
    if employee.archived:raise HTTPException(409,'Staff record was archived')
    policy=db.get(LeavePolicy,data.policy_id)
    if not policy or not policy.active:raise HTTPException(400,'Choose an active, HR-validated leave policy')
    if employee.status in {'Retired','Separated','Deceased','Transferred out'}:raise HTTPException(409,'Employee is not in an active employment category')
    overlap=db.query(Case).filter(Case.kind=='leave',Case.employee_id==employee.id,Case.status.in_(list(PENDING|CHARGED)),Case.start_date<=data.end_date,Case.end_date>=data.start_date).first()
    if overlap:raise HTTPException(409,'This period overlaps another leave application')
    years=day_breakdown(db,policy,data.start_date,data.end_date);days=sum(years.values())
    if not days:raise HTTPException(400,'The period contains no chargeable days under this policy')
    if policy.requires_balance:
        for year,charge in years.items():
            balance=db.query(LeaveBalance).filter_by(employee_id=employee.id,policy_id=policy.id,year=int(year)).first()
            reserved,used=usage(db,employee.id,policy.id,int(year))
            if not balance or balance.granted-used-reserved<charge:raise HTTPException(409,f'Insufficient configured balance for {year}')
    row=new_case(db,user,'leave',policy.name,data.reason,employee_id=employee.id,source_unit_id=employee.unit_id,policy_id=policy.id,start_date=data.start_date,end_date=data.end_date,days=days,final_role=policy.final_role,data=json.dumps({'years':years,'policy_reference':policy.reference,'count_basis':policy.count_basis}))
    db.commit();return view_case(db,row)

@router.post('/transfers',status_code=201)
def transfer(data:TransferInput,db:Session=Depends(get_db),user:User=Depends(current_user)):
    allow(user,HR);employee=require_employee(db,user,data.employee_id)
    employee=db.query(Employee).filter(Employee.id==employee.id).with_for_update().populate_existing().one()
    if employee.archived:raise HTTPException(409,'Staff record was archived')
    cfg=config(db)
    if cfg.get('transfer_final_role') not in {'director','hr_admin'}:raise HTTPException(400,'HR must configure a verified transfer approval authority first')
    target=db.get(Unit,data.target_unit_id)
    if not target or not target.active or target.kind not in {'facility','department'} or target.id==employee.unit_id:raise HTTPException(400,'Choose a different active facility or department')
    if db.query(Case).filter(Case.kind=='transfer',Case.employee_id==employee.id,Case.status.in_(list(PENDING|{'approved','acknowledged'}))).first():raise HTTPException(409,'Another movement is already pending for this employee')
    row=new_case(db,user,'transfer',data.movement_type,data.reason,employee_id=employee.id,source_unit_id=employee.unit_id,target_unit_id=target.id,start_date=data.effective_date,end_date=data.end_date,final_role=cfg['transfer_final_role'],data=json.dumps({'policy_reference':cfg['policy_reference'],'movement_type':data.movement_type}))
    db.commit();return view_case(db,row)

@router.post('/administrative-requests',status_code=201)
def administrative_request(data:AdminInput,db:Session=Depends(get_db),user:User=Depends(current_user)):
    allow(user,OPERATIONS)
    eid=user.employee_id if user.role=='employee' else data.employee_id
    if data.employee_id and user.role=='employee' and data.employee_id!=user.employee_id:raise HTTPException(403,'Personal requests only')
    if eid:require_employee(db,user,eid)
    row=new_case(db,user,'request',data.title,data.body,employee_id=eid,due_date=data.due_date);db.commit();return view_case(db,row)

@router.post('/correspondence',status_code=201)
def correspondence(data:CorrespondenceInput,db:Session=Depends(get_db),user:User=Depends(current_user)):
    allow(user,HR);row=new_case(db,user,'correspondence',data.title,data.body,due_date=data.due_date,data=json.dumps({'direction':data.direction,'correspondent':data.correspondent,'external_reference':data.external_reference}));db.commit();return view_case(db,row)

@router.get('/cases')
def cases(kind:str='',status:str='',q:str='',db:Session=Depends(get_db),user:User=Depends(current_user)):
    query=case_query(db,user)
    if kind:query=query.filter(Case.kind==kind)
    if status:query=query.filter(Case.status==status)
    if q:query=query.filter(or_(Case.reference.ilike('%'+q+'%'),Case.title.ilike('%'+q+'%')))
    rows=query.order_by(Case.created_at.desc()).limit(300).all()
    return {'items':[view_case(db,r) for r in rows],'total':query.count()}

@router.get('/cases/{cid}')
def case_detail(cid:str,db:Session=Depends(get_db),user:User=Depends(current_user)):
    row=visible_case(db,user,cid);audit(db,user,'WORKFLOW_VIEWED',row.id);db.commit();return view_case(db,row)

@router.get('/workflow-assignees')
def assignees(db:Session=Depends(get_db),user:User=Depends(current_user)):
    allow(user,HR|{'director'})
    return [{'id':u.id,'name':u.name,'role':u.role} for u in db.query(User).filter(User.active==True,User.role.in_(list(HR)))]

@router.post('/cases/{cid}/actions')
def transition(cid:str,data:ActionInput,db:Session=Depends(get_db),user:User=Depends(current_user)):
    row=visible_case(db,user,cid,lock=True)
    if row.version!=data.version:raise HTTPException(409,'The request has changed. Reload before acting.')
    action=data.action;employee=db.get(Employee,row.employee_id) if row.employee_id else None
    if employee:employee=db.query(Employee).filter(Employee.id==employee.id).with_for_update().populate_existing().one()
    def no_self():
        if user.id==row.created_by or employee and is_self(user,employee):raise HTTPException(403,'You cannot approve your own request')
    def final_authority():
        if user.role!=row.final_role:raise HTTPException(403,'This action requires the configured final approval role')
        no_self()
    def recommender():
        allow(user,SCOPED|HR);no_self()
        if user.role in SCOPED and (not employee or employee.unit_id not in descendants(db,user.unit_id)):raise HTTPException(403,'Originating supervisor scope required')
        if user.role in HR and len(data.comment)<5:raise HTTPException(400,'Record the external supervisor recommendation in a comment')
    if action in {'assign','respond','close'}:
        if row.kind not in {'request','correspondence'}:raise HTTPException(400,'This is not an administrative task')
        allow(user,HR)
        if row.status in {'closed','cancelled'}:raise HTTPException(409,'The task is already closed')
        if action=='assign':
            target=db.get(User,data.assigned_to) if data.assigned_to else None
            if not target or not target.active or target.role not in HR:raise HTTPException(400,'Choose an active HR assignee')
            row.assigned_to=target.id;row.status='assigned'
        elif action=='respond':
            if len(data.comment)<5:raise HTTPException(400,'Enter a response')
            row.status='responded'
        else:row.status='closed'
    elif action=='recommend':
        if row.kind not in {'leave','transfer'} or row.status!='submitted':raise HTTPException(409,'Only submitted leave or movement requests can be recommended')
        recommender();row.status='recommended'
    elif action=='validate':
        allow(user,HR)
        if row.status!='recommended':raise HTTPException(409,'Supervisor recommendation is required first')
        row.status='hr_validated'
    elif action=='approve':
        if row.status!='hr_validated':raise HTTPException(409,'HR validation is required first')
        final_authority();row.status='approved'
    elif action=='reject':
        if row.status not in PENDING:raise HTTPException(409,'Only pending requests can be rejected')
        allow(user,HR|SCOPED|{row.final_role});no_self()
        if user.role in SCOPED:recommender()
        if len(data.comment)<5:raise HTTPException(400,'A rejection reason is required')
        row.status='rejected'
    elif action=='cancel':
        if row.status not in PENDING|{'assigned','responded'}:raise HTTPException(409,'Approved leave requires a cancellation decision')
        if row.created_by!=user.id and user.role not in HR:raise HTTPException(403,'Only the submitter or HR may cancel this request')
        row.status='cancelled'
    elif action=='request_cancellation':
        if row.kind!='leave' or row.status!='approved':raise HTTPException(409,'Cancellation requests apply to approved, unstarted leave')
        if row.created_by!=user.id and not(employee and is_self(user,employee)) and user.role not in HR:raise HTTPException(403,'Cannot request cancellation')
        if len(data.comment)<5:raise HTTPException(400,'Give a cancellation reason')
        row.status='cancellation_requested'
    elif action=='approve_cancellation':
        if row.status!='cancellation_requested':raise HTTPException(409,'No cancellation request is pending')
        final_authority();row.status='cancelled'
    elif action=='start_leave':
        allow(user,HR|SCOPED)
        if row.kind!='leave' or row.status!='approved' or not(row.start_date<=date.today()<=row.end_date):raise HTTPException(409,'Leave must be approved and within its scheduled period')
        if employee.archived or employee.status not in {'Active','On secondment'}:raise HTTPException(409,'The current employment status does not permit leave commencement')
        payload=parsed(row.data);payload['previous_status']=employee.status;row.data=json.dumps(payload);employee.status='On approved leave';employee.version+=1;row.status='in_progress'
    elif action=='report_return':
        if row.kind!='leave' or row.status!='in_progress':raise HTTPException(409,'Leave is not in progress')
        if not is_self(user,employee) and user.role not in HR:raise HTTPException(403,'Only the employee or HR may report return')
        row.status='return_reported'
    elif action=='confirm_return':
        allow(user,HR|SCOPED)
        if row.kind!='leave' or row.status!='return_reported':raise HTTPException(409,'A return report is required first')
        if employee.status=='On approved leave':employee.status=parsed(row.data).get('previous_status','Active');employee.version+=1
        row.status='completed'
    elif action=='acknowledge':
        if row.kind!='transfer' or row.status!='approved':raise HTTPException(409,'A final approved movement is required')
        allow(user,SCOPED|{'hr_admin'})
        if user.role in SCOPED and row.target_unit_id not in descendants(db,user.unit_id):raise HTTPException(403,'Receiving unit scope required')
        if user.role=='hr_admin' and len(data.comment)<5:raise HTTPException(400,'Record receiving officer acknowledgement')
        row.status='acknowledged'
    elif action=='apply':
        allow(user,HR)
        if row.kind!='transfer' or row.status!='acknowledged':raise HTTPException(409,'Receiving acknowledgement is required first')
        if row.start_date>date.today():raise HTTPException(409,'The effective date has not arrived')
        if employee.archived or employee.unit_id!=row.source_unit_id:raise HTTPException(409,'The source assignment changed; initiate a new approved request')
        if employee.status not in {'Active','On secondment'}:raise HTTPException(409,'Resolve the current employment status before applying a movement')
        target=db.get(Unit,row.target_unit_id)
        if not target or not target.active:raise HTTPException(409,'Receiving unit is no longer active')
        current=db.query(Assignment).filter(Assignment.employee_id==employee.id,Assignment.end_date==None).all()
        if any(a.effective_date>row.start_date for a in current):raise HTTPException(409,'Movement cannot precede the current assignment')
        for assignment in current:assignment.end_date=row.start_date
        db.add(Assignment(employee_id=employee.id,unit_id=row.target_unit_id,effective_date=row.start_date,reason=row.reference+' '+row.title))
        employee.unit_id=row.target_unit_id;employee.posting_date=row.start_date;employee.supervisor_id=None;employee.version+=1
        if row.title=='Secondment':employee.status='On secondment'
        row.status='applied'
    else:raise HTTPException(400,'Unsupported workflow action')
    row.version+=1;record(db,user,row,action,data.comment);db.commit();return view_case(db,row)

@router.get('/notifications')
def notifications(db:Session=Depends(get_db),user:User=Depends(current_user)):
    refresh_reminders(db,user)
    rows=db.query(Notification).filter(Notification.user_id==user.id).order_by(Notification.created_at.desc()).limit(100)
    return [{'id':r.id,'case_id':r.case_id,'document_id':r.document_id,'title':r.title,'read':r.read,'created_at':r.created_at} for r in rows]

@router.post('/notifications/{nid}/read')
def read_notification(nid:str,db:Session=Depends(get_db),user:User=Depends(current_user)):
    row=db.query(Notification).filter_by(id=nid,user_id=user.id).first()
    if not row:raise HTTPException(404,'Notification not found')
    row.read=True;db.commit();return {'ok':True}

@router.get('/cases/{cid}/letter.pdf')
def letter(cid:str,db:Session=Depends(get_db),user:User=Depends(current_user)):
    from reportlab.platypus import SimpleDocTemplate,Spacer
    from reportlab.lib.pagesizes import A4
    from reportlab.platypus import Paragraph
    from reportlab.lib.styles import getSampleStyleSheet
    from xml.sax.saxutils import escape
    row=visible_case(db,user,cid)
    if row.kind not in {'leave','transfer','correspondence'}:raise HTTPException(400,'No letter template for this request')
    if row.kind!='correspondence' and row.status not in CHARGED|{'acknowledged','applied'}:raise HTTPException(409,'Final approval is required')
    cfg=config(db)
    if not cfg.get('letter_heading'):raise HTTPException(400,'Configure the institutional letter template first')
    lines=[cfg['letter_heading'],'PILOT ADMINISTRATIVE COPY — authorized signature required','Reference: '+row.reference+' | Generated: '+date.today().isoformat(),row.title]
    if row.employee_id:
        employee=db.get(Employee,row.employee_id);lines.append(employee.full_name+' | '+employee.staff_id)
    if row.kind=='leave':lines.append(f'Period: {row.start_date} to {row.end_date}. Chargeable days: {row.days}. Status: {row.status}.')
    elif row.kind=='transfer':lines.extend(['From: '+db.get(Unit,row.source_unit_id).name,'To: '+db.get(Unit,row.target_unit_id).name,'Effective date: '+str(row.start_date),'Status: '+row.status])
    else:lines.extend(['DRAFT' if row.status!='closed' else 'Administrative copy',row.body])
    lines.extend([cfg['signatory_name'],cfg['signatory_title'],'Signature: __________________________','This pilot copy is not a digital signature or evidence of institutional authorization.'])
    content=io.BytesIO();styles=getSampleStyleSheet();story=[]
    for i,line in enumerate(lines):
        story.extend([Paragraph(escape(line).replace('\n','<br/>'),styles['Title'] if i==0 else styles['Normal']),Spacer(1,16)])
    SimpleDocTemplate(content,pagesize=A4,leftMargin=55,rightMargin=55,topMargin=55,bottomMargin=55).build(story)
    audit(db,user,'LETTER_EXPORTED',row.id);db.commit()
    return Response(content.getvalue(),media_type='application/pdf',headers={'Content-Disposition':f'attachment; filename="{row.reference}.pdf"'})

CATEGORIES=['Appointment letter','Posting letter','Transfer letter','Promotion letter','Professional licence','Academic certificate','Training certificate','Leave approval letter','Performance appraisal','Correspondence','Other']
EMPLOYEE_CATEGORIES={'Professional licence','Academic certificate','Training certificate','Other'}
def storage_client():
    import boto3
    from botocore.config import Config
    if not all(os.getenv(k) for k in ['AWS_ENDPOINT_URL_S3','AWS_ACCESS_KEY_ID','AWS_SECRET_ACCESS_KEY']):raise HTTPException(503,'Private document storage is not configured')
    return boto3.client('s3',endpoint_url=os.environ['AWS_ENDPOINT_URL_S3'],aws_access_key_id=os.environ['AWS_ACCESS_KEY_ID'],aws_secret_access_key=os.environ['AWS_SECRET_ACCESS_KEY'],region_name=os.getenv('AWS_REGION','eu-central-1'),config=Config(signature_version='s3v4',s3={'addressing_style':'path'},connect_timeout=10,read_timeout=20,retries={'max_attempts':2}))
def bucket():return os.getenv('DOCUMENT_BUCKET','personnel-documents')
def document_query(db,user):
    allow(user,HR|{'employee'})
    query=db.query(Document).filter(Document.archived==False)
    if user.role=='employee':query=query.filter(Document.employee_id==user.employee_id,or_(Document.employee_visible==True,Document.created_by==user.id))
    return query

def doc_view(db,row):
    versions=db.query(DocumentVersion).filter(DocumentVersion.document_id==row.id).order_by(DocumentVersion.number.desc()).all()
    return {'id':row.id,'employee_id':row.employee_id,'employee_name':db.get(Employee,row.employee_id).full_name,'title':row.title,'category':row.category,'employee_visible':row.employee_visible,'versions':[{k:getattr(v,k) for k in ['id','number','filename','content_type','size','verified','expiry_date','created_at']} for v in versions]}

@router.get('/documents')
def documents(employee_id:str='',q:str='',category:str='',db:Session=Depends(get_db),user:User=Depends(current_user)):
    query=document_query(db,user)
    if employee_id:query=query.filter(Document.employee_id==employee_id)
    if q:query=query.filter(Document.title.ilike('%'+q+'%'))
    if category:query=query.filter(Document.category==category)
    return {'items':[doc_view(db,r) for r in query.order_by(Document.title).limit(200)],'categories':CATEGORIES}

@router.post('/documents',status_code=201)
async def upload_document(employee_id:str=Form(...),title:str=Form(...),category:str=Form(...),employee_visible:bool=Form(False),expiry_date:date|None=Form(None),document_id:str|None=Form(None),file:UploadFile=File(...),db:Session=Depends(get_db),user:User=Depends(current_user)):
    allow(user,HR|{'employee'});require_employee(db,user,employee_id)
    if not 2<=len(title.strip())<=180 or category not in CATEGORIES:raise HTTPException(400,'Choose a document title and valid category')
    if user.role=='employee' and category not in EMPLOYEE_CATEGORIES:raise HTTPException(403,'Only HR may upload official letters or appraisal documents')
    row=None
    if document_id:
        row=document_query(db,user).filter(Document.id==document_id).with_for_update().populate_existing().first()
        if not row or row.employee_id!=employee_id:raise HTTPException(404,'Document not found')
        if user.role=='employee' and row.created_by!=user.id:raise HTTPException(403,'Cannot replace an HR-issued document')
        if row.category!=category or row.title!=title:raise HTTPException(400,'Version uploads must retain title and category')
    content=await file.read(10*1024*1024+1)
    if not content or len(content)>10*1024*1024:raise HTTPException(413,'Upload a non-empty PDF, JPEG or PNG up to 10 MB')
    if content.startswith(b'%PDF-'):mime='application/pdf';extension='.pdf'
    elif content.startswith(b'\x89PNG\r\n\x1a\n'):mime='image/png';extension='.png'
    elif content.startswith(b'\xff\xd8\xff'):mime='image/jpeg';extension='.jpg'
    else:raise HTTPException(400,'Only PDF, JPEG and PNG file signatures are accepted')
    if not row:row=Document(employee_id=employee_id,title=title.strip(),category=category,employee_visible=employee_visible if user.role in HR else True,created_by=user.id);db.add(row);db.flush()
    number=(db.query(func.max(DocumentVersion.number)).filter(DocumentVersion.document_id==row.id).scalar() or 0)+1
    key=f'personnel/{employee_id}/{row.id}/{uid()}{extension}'
    clean=re.sub(r'[^A-Za-z0-9._-]','_',os.path.basename(file.filename or 'document'))[:160]
    if not clean.lower().endswith(extension):clean='document'+extension
    version=DocumentVersion(document_id=row.id,number=number,object_key=key,filename=clean,content_type=mime,size=len(content),checksum=hashlib.sha256(content).hexdigest(),uploaded_by=user.id,expiry_date=expiry_date)
    client=storage_client()
    try:client.put_object(Bucket=bucket(),Key=key,Body=content,ContentType=mime,CacheControl='private, no-store')
    except Exception:raise HTTPException(503,'Private storage upload failed. Retry later.')
    try:
        db.add(version);db.flush();audit(db,user,'DOCUMENT_UPLOADED',row.id,detail=f'Version {number}');db.commit()
    except Exception:
        db.rollback()
        try:client.delete_object(Bucket=bucket(),Key=key)
        except Exception:pass
        raise
    return doc_view(db,row)

@router.get('/documents/{did}/versions/{vid}/download')
def document_link(did:str,vid:str,db:Session=Depends(get_db),user:User=Depends(current_user)):
    row=document_query(db,user).filter(Document.id==did).first();version=db.query(DocumentVersion).filter_by(id=vid,document_id=did).first()
    if not row or not version:raise HTTPException(404,'Document not found')
    try:url=storage_client().generate_presigned_url('get_object',Params={'Bucket':bucket(),'Key':version.object_key,'ResponseContentDisposition':f'attachment; filename="{version.filename}"'},ExpiresIn=60)
    except Exception:raise HTTPException(503,'Private storage temporarily unavailable')
    audit(db,user,'DOCUMENT_DOWNLOAD',row.id,detail=f'Version {version.number}');db.commit();return {'url':url,'expires_in':60}

@router.patch('/documents/{did}/versions/{vid}/verify')
def verify_document(did:str,vid:str,db:Session=Depends(get_db),user:User=Depends(current_user)):
    allow(user,HR);row=document_query(db,user).filter(Document.id==did).first();version=db.query(DocumentVersion).filter_by(id=vid,document_id=did).first()
    if not row or not version:raise HTTPException(404,'Document not found')
    version.verified=True;audit(db,user,'DOCUMENT_VERIFIED',row.id,detail=f'Version {version.number}');db.commit();return {'ok':True}

@router.patch('/documents/{did}')
def document_visibility(did:str,data:dict,db:Session=Depends(get_db),user:User=Depends(current_user)):
    allow(user,HR);row=document_query(db,user).filter(Document.id==did).first()
    if not row:raise HTTPException(404,'Document not found')
    if set(data)!={'employee_visible'} or not isinstance(data['employee_visible'],bool):raise HTTPException(400,'Provide employee_visible boolean')
    row.employee_visible=data['employee_visible'];audit(db,user,'DOCUMENT_VISIBILITY_CHANGED',row.id);db.commit();return {'ok':True}


def refresh_reminders(db,user):
    if user.role not in OPERATIONS:return
    db.query(User).filter(User.id==user.id).with_for_update().populate_existing().one()
    today=date.today();horizon=today+timedelta(days=90)
    def add(key,title,case_id=None,document_id=None):
        key=user.id+':'+key
        if not db.query(Notification).filter(Notification.event_key==key).first():
            db.add(Notification(user_id=user.id,event_key=key,title=title[:180],case_id=case_id,document_id=document_id));db.flush()
    if user.role in HR|{'employee'}:
        for document in document_query(db,user):
            version=db.query(DocumentVersion).filter(DocumentVersion.document_id==document.id).order_by(DocumentVersion.number.desc()).first()
            if version and version.expiry_date and version.expiry_date<=horizon:
                add('doc:'+version.id,'Document expiry review: '+document.title+' ('+str(version.expiry_date)+')',document_id=document.id)
    for case in case_query(db,user).filter(Case.status.notin_(['cancelled','rejected','closed','completed'])):
        if case.due_date and case.due_date<=today+timedelta(days=7):add('deadline:'+case.id,'Deadline review: '+case.reference,case_id=case.id)
        if case.kind=='leave' and case.status=='approved' and case.start_date<=today+timedelta(days=7):add('leave-start:'+case.id,'Approved leave start review: '+case.reference,case_id=case.id)
        if case.kind=='transfer' and case.status=='acknowledged' and case.start_date<=today:add('movement:'+case.id,'Approved movement ready for HR review: '+case.reference,case_id=case.id)
        if case.kind=='transfer' and case.status=='applied' and case.end_date and case.end_date<=today+timedelta(days=30):add('movement-end:'+case.id,'Temporary placement end review: '+case.reference,case_id=case.id)
    db.commit()
