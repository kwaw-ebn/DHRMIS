import csv, io, json, os, secrets, time
from datetime import datetime, timedelta, timezone, date
from pathlib import Path
import pyotp
from fastapi import FastAPI, Depends, HTTPException, Request, Response, UploadFile, File, Query
from fastapi.responses import StreamingResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from pydantic import ValidationError
from .db import get_db
from .models import Unit, Employee, Assignment, User, Session as LoginSession, Audit, Setting
from .schemas import Login, MfaCode, PasswordChange, UnitInput, EmployeeInput, UserInput, Vocabulary, ROLES, STATUSES
from .security import *

app=FastAPI(title='GHS StaffHub — DHRMIS',version='0.4.1',docs_url='/api/docs',openapi_url='/api/openapi.json')
SECURE=os.getenv('COOKIE_SECURE','true').lower()=='true'

@app.middleware('http')
async def headers(request,call_next):
    if request.method not in {'GET','HEAD','OPTIONS'}:
        origin=request.headers.get('origin')
        if origin and origin != f'{request.url.scheme}://{request.headers.get("host")}':
            return Response('Cross-origin request denied',403)
    response=await call_next(request)
    response.headers['X-Content-Type-Options']='nosniff'
    response.headers['X-Frame-Options']='DENY'
    response.headers['Referrer-Policy']='same-origin'
    response.headers['Permissions-Policy']='geolocation=(), camera=(), microphone=()'
    response.headers['Content-Security-Policy']="default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'; img-src 'self' data: blob:; connect-src 'self'; frame-ancestors 'none'; base-uri 'self'; form-action 'self'"
    if SECURE: response.headers['Strict-Transport-Security']='max-age=31536000; includeSubDomains'
    if request.url.path.startswith('/api'): response.headers['Cache-Control']='no-store'
    return response

@app.exception_handler(IntegrityError)
async def integrity_error(request,exc):
    return Response(json.dumps({'detail':'An identifier already exists or a referenced record is invalid.'}),409,media_type='application/json')

@app.get('/api/health')
def health(db: Session=Depends(get_db)):
    db.execute(select(1))
    return {'status':'ok','mode':'pilot','version':'0.4.1'}

@app.post('/api/auth/login')
def login(data:Login,response:Response,db:Session=Depends(get_db)):
    user=db.query(User).filter(User.email==str(data.email).lower()).first()
    if user and user.locked_until and utc(user.locked_until)>datetime.now(timezone.utc):
        raise HTTPException(429,'Account temporarily locked. Retry in 15 minutes.')
    valid=verify(data.password,user.password_hash if user else DUMMY_HASH)
    if not user or not valid or not user.active:
        if user:
            user.failed_attempts+=1
            if user.failed_attempts>=5: user.locked_until=datetime.now(timezone.utc)+timedelta(minutes=15)
            audit(db,user,'LOGIN_FAILED');db.commit()
        raise HTTPException(401,'Email or password is incorrect')
    user.failed_attempts=0;user.locked_until=None
    token=secrets.token_urlsafe(32);csrf=secrets.token_urlsafe(32)
    requires=user.role in PRIVILEGED or user.mfa_enabled
    db.add(LoginSession(id=digest(token),user_id=user.id,expires_at=datetime.now(timezone.utc)+timedelta(minutes=10 if requires else 480),authenticated=not requires,csrf_token=csrf))
    # Garbage collect expired sessions without affecting active users.
    db.query(LoginSession).filter(LoginSession.expires_at<datetime.now(timezone.utc)).delete()
    audit(db,user,'PASSWORD_VERIFIED');db.commit()
    response.set_cookie('staffhub_session',token,httponly=True,secure=SECURE,samesite='strict',max_age=480*60,path='/')
    return {'user':public_user(user),'csrf_token':csrf,'mfa_required':requires,'mfa_setup':requires and not user.mfa_enabled}

@app.get('/api/auth/mfa/setup')
def mfa_setup(request:Request,db:Session=Depends(get_db)):
    user,session=session_user(request,db,full=False)
    if user.mfa_enabled: raise HTTPException(409,'MFA already enabled')
    if not user.totp_secret:
        user.totp_secret=encrypt(pyotp.random_base32());db.commit()
    secret=decrypt(user.totp_secret)
    return {'secret':secret,'uri':pyotp.TOTP(secret).provisioning_uri(user.email,issuer_name='GHS StaffHub Pilot')}

@app.post('/api/auth/mfa/verify')
def mfa_verify(data:MfaCode,request:Request,db:Session=Depends(get_db)):
    user,session=session_user(request,db,full=False)
    # A row lock prevents concurrent reuse of the same time-based code.
    user=db.query(User).filter(User.id==user.id).with_for_update().one()
    if user.locked_until and utc(user.locked_until)>datetime.now(timezone.utc): raise HTTPException(429,'Account temporarily locked')
    step=int(time.time())//30
    secret=decrypt(user.totp_secret) if user.totp_secret else ''
    matching=next((n for n in [step-1,step,step+1] if secret and secrets.compare_digest(pyotp.TOTP(secret).at(n*30),data.code)),None)
    if matching is None or matching<=user.last_totp_step:
        user.failed_attempts+=1
        if user.failed_attempts>=5: user.locked_until=datetime.now(timezone.utc)+timedelta(minutes=15)
        audit(db,user,'MFA_FAILED');db.commit();raise HTTPException(401,'Invalid or already used authenticator code')
    user.last_totp_step=matching;user.failed_attempts=0;user.locked_until=None;user.mfa_enabled=True
    session.authenticated=True;session.expires_at=datetime.now(timezone.utc)+timedelta(hours=8)
    audit(db,user,'LOGIN_SUCCESS');db.commit()
    return {'user':public_user(user),'csrf_token':session.csrf_token}

@app.get('/api/auth/me')
def me(request:Request,db:Session=Depends(get_db),user:User=Depends(current_user)):
    _,session=session_user(request,db)
    return {'user':public_user(user),'csrf_token':session.csrf_token}

@app.post('/api/auth/logout')
def logout(request:Request,response:Response,db:Session=Depends(get_db)):
    user,session=session_user(request,db,full=False)
    db.delete(session);audit(db,user,'LOGOUT');db.commit()
    response.delete_cookie('staffhub_session',path='/');return {'ok':True}

@app.post('/api/auth/password')
def password(data:PasswordChange,request:Request,db:Session=Depends(get_db),user:User=Depends(current_user)):
    if not verify(data.current_password,user.password_hash): raise HTTPException(400,'Current password is incorrect')
    if data.new_password==data.current_password: raise HTTPException(400,'Choose a different password')
    user.password_hash=ph.hash(data.new_password);user.must_change_password=False
    _,session=session_user(request,db)
    db.query(LoginSession).filter(LoginSession.user_id==user.id,LoginSession.id!=session.id).delete()
    audit(db,user,'PASSWORD_CHANGED');db.commit();return {'ok':True}

@app.get('/api/units')
def units(db:Session=Depends(get_db),user:User=Depends(current_user)):
    if user.role=='auditor': raise HTTPException(403,'Audit records only')
    rows=db.query(Unit).filter(Unit.active==True).all()
    if user.role in SCOPED:
        visible=descendants(db,user.unit_id)
        # Include ancestors for readable breadcrumbs, not siblings.
        lookup={u.id:u for u in rows}; parent=user.unit_id
        while parent and parent in lookup:
            visible.add(parent);parent=lookup[parent].parent_id
        rows=[u for u in rows if u.id in visible]
    if user.role=='employee':
        employee=db.get(Employee,user.employee_id) if user.employee_id else None
        lookup={u.id:u for u in rows}; visible=set();parent=employee.unit_id if employee else None
        while parent and parent in lookup:
            visible.add(parent);parent=lookup[parent].parent_id
        rows=[u for u in rows if u.id in visible]
    return [{k:getattr(u,k) for k in ['id','name','kind','parent_id','category']} for u in rows]

@app.post('/api/units',status_code=201)
def create_unit(data:UnitInput,db:Session=Depends(get_db),user:User=Depends(current_user)):
    allow(user,{'hr_admin'})
    expected={'district':{'organization'},'subdistrict':{'district'},'facility':{'district','subdistrict'},'department':{'district','facility'}}
    if data.kind=='organization':
        if data.parent_id or db.query(Unit).filter(Unit.kind=='organization').first(): raise HTTPException(400,'Only one root organization is supported in this pilot')
    else:
        parent=db.get(Unit,data.parent_id) if data.parent_id else None
        if not parent or not parent.active or parent.kind not in expected[data.kind]: raise HTTPException(400,'Invalid parent for this unit type')
    if data.kind=='facility' and not data.category: raise HTTPException(400,'Choose a facility category')
    if data.kind!='facility' and data.category: raise HTTPException(400,'Category is only applicable to facilities')
    unit=Unit(**data.model_dump());db.add(unit);db.flush();audit(db,user,'UNIT_CREATED',unit.id);db.commit();return {'id':unit.id}

@app.patch('/api/units/{unit_id}')
def rename_unit(unit_id:str,data:dict,db:Session=Depends(get_db),user:User=Depends(current_user)):
    allow(user,{'hr_admin'});unit=db.get(Unit,unit_id)
    if not unit: raise HTTPException(404,'Unit not found')
    name=data.get('name','').strip()
    if not 2<=len(name)<=180 or set(data)!={'name'}: raise HTTPException(400,'Provide a name between 2 and 180 characters')
    unit.name=name;audit(db,user,'UNIT_RENAMED',unit.id);db.commit();return {'ok':True}

@app.delete('/api/units/{unit_id}')
def archive_unit(unit_id:str,db:Session=Depends(get_db),user:User=Depends(current_user)):
    allow(user,{'hr_admin'});unit=db.get(Unit,unit_id)
    if not unit or not unit.active: raise HTTPException(404,'Unit not found')
    from .phase2_models import Case
    if db.query(Case).filter(or_(Case.target_unit_id==unit_id,Case.source_unit_id==unit_id),Case.status.notin_(['cancelled','rejected','closed','completed','applied'])).first(): raise HTTPException(409,'Resolve pending HR workflows before archiving this unit')
    if unit.kind in {'organization','district'}: raise HTTPException(400,'Root units cannot be archived')
    if db.query(Unit).filter(Unit.parent_id==unit_id,Unit.active==True).first() or db.query(Employee).filter(Employee.unit_id==unit_id,Employee.archived==False).first() or db.query(User).filter(User.unit_id==unit_id,User.active==True).first(): raise HTTPException(409,'Move staff and child units and remove user scopes before archiving')
    unit.active=False;audit(db,user,'UNIT_ARCHIVED',unit_id);db.commit();return {'ok':True}

@app.get('/api/settings')
def settings(db:Session=Depends(get_db),user:User=Depends(current_user)):
    return {s.key:json.loads(s.value) for s in db.query(Setting).all()} | {'roles':ROLES,'statuses':STATUSES,'pilot':True}

@app.put('/api/settings/vocabulary')
def vocabulary(data:Vocabulary,db:Session=Depends(get_db),user:User=Depends(current_user)):
    allow(user,{'hr_admin'})
    for key,values in data.model_dump().items():
        values=[v.strip() for v in values]
        if any(not v or len(v)>80 for v in values) or len(set(values))!=len(values): raise HTTPException(400,'Vocabulary entries must be unique, non-empty and at most 80 characters')
        used={x[0] for x in db.query(Employee.cadre if key=='cadres' else Employee.grade).all() if x[0]}
        if used-set(values): raise HTTPException(409,'Cannot remove vocabulary entries used by staff records')
        row=db.get(Setting,key)
        if row: row.value=json.dumps(values)
        else: db.add(Setting(key=key,value=json.dumps(values)))
    audit(db,user,'VOCABULARY_UPDATED');db.commit();return {'ok':True}

def validate_employee(data,db,employee_id=None):
    unit=db.get(Unit,data.unit_id)
    if not unit or not unit.active or unit.kind not in {'facility','department'}: raise HTTPException(400,'Staff must be assigned to an active facility or department')
    for key,value in [('cadres',data.cadre),('grades',data.grade)]:
        row=db.get(Setting,key)
        if value and (not row or value not in json.loads(row.value)): raise HTTPException(400,f'Choose a configured {key[:-1]}')
    if data.staff_id:
        duplicate=db.query(Employee).filter(func.lower(Employee.staff_id)==data.staff_id.lower())
        if employee_id:duplicate=duplicate.filter(Employee.id!=employee_id)
        if duplicate.first():raise HTTPException(409,'This staff ID / file number already exists')
    if data.supervisor_id:
        supervisor=db.get(Employee,data.supervisor_id)
        if not supervisor or supervisor.archived or data.supervisor_id==employee_id: raise HTTPException(400,'Invalid supervisor')
        seen={employee_id};cursor=supervisor
        while cursor:
            if cursor.id in seen: raise HTTPException(400,'Supervisor relationship would form a cycle')
            seen.add(cursor.id);cursor=db.get(Employee,cursor.supervisor_id) if cursor.supervisor_id else None

def employee_view(row,user):
    fields=['id','staff_id','full_name','preferred_name','job_title','cadre','grade','rank','status','unit_id','verified','version','licence_expiry','created_at','updated_at']
    if user.role in HR or (user.role=='employee' and user.employee_id==row.id):
        fields += ['ghs_number','payroll_number','date_of_birth','gender','email','phone','address','emergency_contact','appointment_type','employment_date','first_appointment_date','posting_date','supervisor_id','qualification','registration_body','registration_number','specialty']
    return {k:getattr(row,k) for k in fields}|{'file_number':row.staff_id}

def filter_staff(query,q,unit_id,cadre,status,db):
    if q: query=query.filter(or_(Employee.full_name.ilike(f'%{q}%'),Employee.staff_id.ilike(f'%{q}%'),Employee.job_title.ilike(f'%{q}%')))
    if unit_id: query=query.filter(Employee.unit_id.in_(descendants(db,unit_id)))
    if cadre: query=query.filter(Employee.cadre==cadre)
    if status: query=query.filter(Employee.status==status)
    return query

@app.get('/api/employees')
def employees(q:str='',unit_id:str='',cadre:str='',status:str='',page:int=Query(1,ge=1),page_size:int=Query(20,ge=1,le=100),db:Session=Depends(get_db),user:User=Depends(current_user)):
    query=filter_staff(staff_query(db,user),q,unit_id,cadre,status,db)
    return {'total':query.count(),'page':page,'items':[employee_view(e,user) for e in query.order_by(Employee.full_name).offset((page-1)*page_size).limit(page_size)]}

@app.get('/api/employees/export')
def export(q:str='',unit_id:str='',cadre:str='',status:str='',db:Session=Depends(get_db),user:User=Depends(current_user)):
    allow(user,HR|{'director','subdistrict_head','facility_head','department_head'})
    rows=filter_staff(staff_query(db,user),q,unit_id,cadre,status,db).order_by(Employee.full_name).all()
    output=io.StringIO();columns=['staff_id','full_name','job_title','cadre','grade','status','unit_id','verified']
    writer=csv.DictWriter(output,fieldnames=columns);writer.writeheader()
    for row in rows:
        values={key:getattr(row,key) for key in columns}
        values={k:("'"+str(v) if str(v).lstrip().startswith(('=','+','-','@','\t','\r')) else v) for k,v in values.items()}
        writer.writerow(values)
    audit(db,user,'STAFF_EXPORT',detail=f'{len(rows)} records');db.commit()
    return Response(output.getvalue(),media_type='text/csv',headers={'Content-Disposition':'attachment; filename="staff-directory.csv"'})

@app.get('/api/employees/import-template')
def import_template(user:User=Depends(current_user)):
    allow(user,HR)
    return Response('staff_id,full_name,ghs_number,payroll_number,email,phone,job_title,cadre,grade,status,unit_id,employment_date,licence_expiry\n',media_type='text/csv',headers={'Content-Disposition':'attachment; filename="staff-import-template.csv"'})

@app.post('/api/employees/import')
async def import_staff(file:UploadFile=File(...),db:Session=Depends(get_db),user:User=Depends(current_user)):
    allow(user,HR)
    content=await file.read(2*1024*1024+1)
    if len(content)>2*1024*1024: raise HTTPException(413,'CSV limit is 2 MB')
    try:
        reader=csv.DictReader(io.StringIO(content.decode('utf-8-sig')))
        if not reader.fieldnames or not {'full_name','job_title','cadre','unit_id'}<=set(reader.fieldnames): raise HTTPException(400,'Missing required CSV columns')
        rows=list(reader)
    except (UnicodeDecodeError,csv.Error): raise HTTPException(400,'Upload a valid UTF-8 CSV')
    if not rows or len(rows)>500: raise HTTPException(400,'Import 1–500 rows at a time')
    validated=[];errors=[];seen_ghs=set();seen_payroll=set();seen_staff_ids=set();seen_people=set()
    for n,row in enumerate(rows,2):
        try:
            if None in row: raise ValueError('Unexpected extra columns')
            clean={k:v.strip() for k,v in row.items() if v and v.strip()}
            unknown=set(clean)-set(EmployeeInput.model_fields)
            if unknown: raise ValueError('Unknown CSV columns: '+', '.join(sorted(unknown)))
            clean.pop('version',None);clean['verified']=False
            data=EmployeeInput(**clean);validate_employee(data,db)
            for field,seen in [('staff_id',seen_staff_ids),('ghs_number',seen_ghs),('payroll_number',seen_payroll)]:
                value=getattr(data,field)
                if value and (value in seen or db.query(Employee).filter(getattr(Employee,field)==value).first()): raise ValueError(f'Duplicate {field}')
                if value: seen.add(value)
            identity=(data.full_name.casefold(),str(data.date_of_birth or ''),data.unit_id)
            if identity in seen_people or db.query(Employee).filter(func.lower(Employee.full_name)==data.full_name.lower(),Employee.unit_id==data.unit_id).first(): raise ValueError('Possible duplicate person; review manually')
            seen_people.add(identity);validated.append(data)
        except (ValidationError,ValueError,HTTPException) as exc:
            errors.append({'row':n,'error':exc.detail if isinstance(exc,HTTPException) else str(exc)[:350]})
    if errors: raise HTTPException(400,{'message':'No rows were imported. Correct these errors and retry.','errors':errors})
    for data in validated: add_employee(data,db,user)
    audit(db,user,'STAFF_IMPORT',detail=f'{len(validated)} records');db.commit();return {'imported':len(validated)}

def add_employee(data,db,user):
    payload=data.model_dump(exclude={'version'});staff_id=payload.pop('staff_id',None)
    for field in ['ghs_number','payroll_number']:
        if payload[field]=='':payload[field]=None
    employee=Employee(**payload,staff_id=staff_id or 'SH-'+secrets.token_hex(5).upper())
    db.add(employee);db.flush()
    db.add(Assignment(employee_id=employee.id,unit_id=employee.unit_id,effective_date=employee.posting_date or date.today(),reason='Initial personnel registration'))
    audit(db,user,'EMPLOYEE_CREATED',employee.id)
    return employee

@app.post('/api/employees',status_code=201)
def create_employee(data:EmployeeInput,db:Session=Depends(get_db),user:User=Depends(current_user)):
    allow(user,HR);validate_employee(data,db)
    if db.query(Employee).filter(func.lower(Employee.full_name)==data.full_name.lower(),Employee.unit_id==data.unit_id,Employee.archived==False).first(): raise HTTPException(409,'Possible duplicate person at this unit. Review the existing record.')
    employee=add_employee(data,db,user);db.commit();return employee_view(employee,user)

@app.get('/api/employees/{employee_id}')
def employee(employee_id:str,db:Session=Depends(get_db),user:User=Depends(current_user)):
    row=staff_query(db,user).filter(Employee.id==employee_id).first()
    if not row: raise HTTPException(404,'Staff record not found')
    audit(db,user,'EMPLOYEE_VIEWED',row.id);db.commit()
    result=employee_view(row,user)
    result['assignments']=[{'unit_id':a.unit_id,'effective_date':a.effective_date,'end_date':a.end_date,'reason':a.reason} for a in db.query(Assignment).filter(Assignment.employee_id==row.id).order_by(Assignment.effective_date.desc())]
    return result

@app.put('/api/employees/{employee_id}')
def update_employee(employee_id:str,data:EmployeeInput,db:Session=Depends(get_db),user:User=Depends(current_user)):
    allow(user,HR)
    row=db.query(Employee).filter(Employee.id==employee_id,Employee.archived==False).with_for_update().first()
    if not row: raise HTTPException(404,'Staff record not found')
    if data.version!=row.version: raise HTTPException(409,'The record has changed. Reload it before editing.')
    validate_employee(data,db,row.id)
    if data.unit_id!=row.unit_id: raise HTTPException(400,'Use Postings & transfers to change assignments through the approval workflow.')
    if data.staff_id is not None and data.staff_id!=row.staff_id:raise HTTPException(400,'Staff ID / file number is permanent and cannot be changed through profile editing')
    changes=[]
    for key,value in data.model_dump(exclude={'version','staff_id'}).items():
        if key in {'ghs_number','payroll_number'} and value=='':value=None
        if getattr(row,key)!=value: changes.append(key)
        setattr(row,key,value)
    row.version+=1;audit(db,user,'EMPLOYEE_UPDATED',row.id,detail='Fields: '+', '.join(changes));db.commit();return employee_view(row,user)

@app.delete('/api/employees/{employee_id}')
def archive_employee(employee_id:str,db:Session=Depends(get_db),user:User=Depends(current_user)):
    allow(user,{'hr_admin'});row=db.query(Employee).filter(Employee.id==employee_id).with_for_update().populate_existing().first()
    from .phase2_models import Case
    if db.query(Case).filter(Case.employee_id==employee_id,Case.status.notin_(['cancelled','rejected','closed','completed','applied'])).first():raise HTTPException(409,'Resolve active HR workflows before archiving this staff record')
    if not row or row.archived: raise HTTPException(404,'Staff record not found')
    row.archived=True;row.version+=1
    for account in db.query(User).filter(User.employee_id==row.id):
        account.active=False;db.query(LoginSession).filter(LoginSession.user_id==account.id).delete()
    audit(db,user,'EMPLOYEE_ARCHIVED',row.id);db.commit();return {'ok':True}

@app.get('/api/dashboard')
def dashboard(unit_id:str='',db:Session=Depends(get_db),user:User=Depends(current_user)):
    query=staff_query(db,user)
    if unit_id: query=query.filter(Employee.unit_id.in_(descendants(db,unit_id)))
    staff=query.all();today=date.today();expiry=today+timedelta(days=90)
    def counts(key):
        result={}
        for e in staff: result[getattr(e,key)]=result.get(getattr(e,key),0)+1
        return [{'name':k,'count':v} for k,v in sorted(result.items(),key=lambda x:-x[1])]
    lookup={u.id:u.name for u in db.query(Unit).all()}
    distribution=[{'name':lookup.get(x['name'],'Unknown'),'count':x['count']} for x in counts('unit_id')]
    return {'total':len(staff),'active':sum(e.status=='Active' for e in staff),'on_leave':sum(e.status in {'On approved leave','On study leave'} for e in staff),'unverified':sum(not e.verified for e in staff),'licences_due':sum(e.licence_expiry is not None and e.licence_expiry<=expiry for e in staff),'by_cadre':counts('cadre'),'by_status':counts('status'),'by_unit':distribution,'alerts':[{'id':e.id,'full_name':e.full_name,'expiry':e.licence_expiry,'expired':e.licence_expiry<today} for e in staff if e.licence_expiry and e.licence_expiry<=expiry]}

@app.get('/api/audit')
def audit_logs(page:int=Query(1,ge=1),db:Session=Depends(get_db),user:User=Depends(current_user)):
    allow(user,{'hr_admin','auditor'})
    query=db.query(Audit)
    return {'total':query.count(),'items':[{k:getattr(a,k) for k in ['id','actor_name','action','entity_id','detail','created_at']} for a in query.order_by(Audit.created_at.desc()).offset((page-1)*50).limit(50)]}

@app.get('/api/users')
def users(db:Session=Depends(get_db),user:User=Depends(current_user)):
    allow(user,{'hr_admin','platform_admin'})
    return [public_user(u) for u in db.query(User).order_by(User.name)]

@app.post('/api/users',status_code=201)
def create_user(data:UserInput,db:Session=Depends(get_db),user:User=Depends(current_user)):
    allow(user,{'hr_admin','platform_admin'})
    permitted=set(ROLES)-{'platform_admin'} if user.role=='hr_admin' else {'platform_admin'}
    if data.role not in permitted: raise HTTPException(403,'Cannot assign this role')
    if data.role in SCOPED:
        unit=db.get(Unit,data.unit_id) if data.unit_id else None
        required={'subdistrict_head':'subdistrict','facility_head':'facility','department_head':'department'}[data.role]
        if not unit or not unit.active or unit.kind!=required: raise HTTPException(400,'Choose a matching scope for this role')
    elif data.unit_id: raise HTTPException(400,'Scope is only applicable to unit head roles')
    if data.role=='employee':
        employee=db.get(Employee,data.employee_id) if data.employee_id else None
        if not employee or employee.archived: raise HTTPException(400,'Link an active staff record')
    elif data.employee_id: raise HTTPException(400,'Staff linkage is currently reserved for employee accounts')
    account=User(email=str(data.email).lower(),name=data.name,password_hash=ph.hash(data.password),role=data.role,unit_id=data.unit_id,employee_id=data.employee_id)
    db.add(account);db.flush();audit(db,user,'USER_CREATED',account.id,detail=data.role);db.commit();return public_user(account)

@app.patch('/api/users/{user_id}')
def disable_user(user_id:str,data:dict,db:Session=Depends(get_db),user:User=Depends(current_user)):
    allow(user,{'hr_admin','platform_admin'})
    account=db.get(User,user_id)
    if not account: raise HTTPException(404,'Account not found')
    if account.id==user.id: raise HTTPException(400,'You cannot disable your own account')
    if user.role=='platform_admin' and account.role!='platform_admin' or user.role=='hr_admin' and account.role=='platform_admin': raise HTTPException(403,'Cannot manage this account')
    if set(data)!={'active'} or not isinstance(data['active'],bool): raise HTTPException(400,'Provide an active boolean')
    account.active=data['active'];db.query(LoginSession).filter(LoginSession.user_id==account.id).delete();audit(db,user,'USER_ENABLED' if account.active else 'USER_DISABLED',account.id);db.commit();return {'ok':True}

@app.post('/api/users/{user_id}/reset-password')
def reset_password(user_id:str,db:Session=Depends(get_db),user:User=Depends(current_user)):
    allow(user,{'hr_admin','platform_admin'});account=db.get(User,user_id)
    if not account: raise HTTPException(404,'Account not found')
    if account.id==user.id or (user.role=='hr_admin' and account.role=='platform_admin') or (user.role=='platform_admin' and account.role!='platform_admin'): raise HTTPException(403,'Cannot reset this account')
    temporary=secrets.token_urlsafe(18);account.password_hash=ph.hash(temporary);account.must_change_password=True;account.failed_attempts=0;account.locked_until=None
    db.query(LoginSession).filter(LoginSession.user_id==account.id).delete();audit(db,user,'PASSWORD_RESET',account.id);db.commit()
    return {'temporary_password':temporary,'note':'Share through an approved private channel. MFA remains required.'}

from .phase2 import router as phase2_router
app.include_router(phase2_router)

from .phase3 import router as phase3_router
app.include_router(phase3_router)

from .photos import router as photos_router
app.include_router(photos_router)

from .staff_files import router as staff_files_router
app.include_router(staff_files_router)

from .hr_tasks import router as hr_tasks_router
app.include_router(hr_tasks_router)

static=Path(__file__).parent.parent/'static'
if static.exists(): app.mount('/',StaticFiles(directory=static,html=True),name='frontend')
