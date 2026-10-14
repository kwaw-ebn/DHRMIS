import os, hashlib, secrets
from datetime import datetime, timezone
from argon2 import PasswordHasher
from argon2.exceptions import VerificationError, InvalidHashError
from cryptography.fernet import Fernet
from fastapi import Depends, HTTPException, Request
from sqlalchemy.orm import Session
from .db import get_db
from .models import User, Session as LoginSession, Audit, Unit, Employee
ph = PasswordHasher()
HR = {'hr_admin','hr_officer'}
READ_STAFF = HR | {'director','subdistrict_head','facility_head','department_head','employee'}
SCOPED = {'subdistrict_head','facility_head','department_head'}
PRIVILEGED = {'hr_admin','hr_officer','director','subdistrict_head','facility_head','department_head','platform_admin','auditor'}

def cipher():
    key = os.environ.get('MFA_ENCRYPTION_KEY')
    if not key: raise RuntimeError('MFA_ENCRYPTION_KEY is required')
    return Fernet(key.encode())
def encrypt(value): return cipher().encrypt(value.encode()).decode()
def decrypt(value): return cipher().decrypt(value.encode()).decode()
def digest(value): return hashlib.sha256(value.encode()).hexdigest()
def verify(password, hashed):
    try: return ph.verify(hashed, password)
    except (VerificationError, InvalidHashError): return False
DUMMY_HASH = ph.hash(secrets.token_urlsafe(32))
def utc(value): return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value

def session_user(request: Request, db: Session, full=True):
    token = request.cookies.get('staffhub_session','')
    session = db.get(LoginSession,digest(token)) if token else None
    if not session or utc(session.expires_at) <= datetime.now(timezone.utc):
        raise HTTPException(401,'Please sign in')
    user = db.get(User,session.user_id)
    if not user or not user.active: raise HTTPException(401,'Account disabled')
    if request.method not in {'GET','HEAD','OPTIONS'}:
        if not secrets.compare_digest(request.headers.get('x-csrf-token',''),session.csrf_token):
            raise HTTPException(403,'Invalid request token')
    if full and not session.authenticated: raise HTTPException(403,'Complete MFA verification')
    return user,session

def current_user(request: Request, db: Session = Depends(get_db)):
    user,_ = session_user(request,db)
    if user.must_change_password and request.url.path not in {'/api/auth/me','/api/auth/password','/api/auth/logout'}:
        raise HTTPException(403,'Change your temporary password first')
    return user

def allow(user, roles):
    if user.role not in roles: raise HTTPException(403,'Your role does not permit this action')
def audit(db,user,action,entity=None,detail=''):
    db.add(Audit(actor_id=user.id if user else None,actor_name=user.name if user else 'Unknown',action=action,entity_id=entity,detail=detail))
def descendants(db,unit_id):
    units = db.query(Unit).all()
    result = {unit_id} if unit_id else set()
    while True:
        new = {u.id for u in units if u.parent_id in result} - result
        if not new: break
        result.update(new)
    return result

def staff_query(db,user):
    allow(user,READ_STAFF)
    query=db.query(Employee).filter(Employee.archived == False)
    if user.role == 'employee': return query.filter(Employee.id==user.employee_id)
    if user.role in SCOPED: return query.filter(Employee.unit_id.in_(descendants(db,user.unit_id)))
    return query

def public_user(user):
    return {k:getattr(user,k) for k in ['id','email','name','role','unit_id','employee_id','must_change_password','mfa_enabled','active']}
