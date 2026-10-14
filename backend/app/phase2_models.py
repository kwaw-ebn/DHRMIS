from datetime import date,datetime
from sqlalchemy import String,Date,DateTime,Boolean,Integer,ForeignKey,Text,UniqueConstraint,LargeBinary
from sqlalchemy.orm import Mapped,mapped_column
from .db import Base
from .models import uid,now
class LeavePolicy(Base):
    __tablename__='leave_policies'
    id:Mapped[str]=mapped_column(String(36),primary_key=True,default=uid)
    name:Mapped[str]=mapped_column(String(120),unique=True)
    reference:Mapped[str]=mapped_column(String(250))
    requires_balance:Mapped[bool]=mapped_column(Boolean)
    count_basis:Mapped[str]=mapped_column(String(20))
    working_days:Mapped[str]=mapped_column(Text)
    final_role:Mapped[str]=mapped_column(String(40))
    active:Mapped[bool]=mapped_column(Boolean,default=True)
    created_at:Mapped[datetime]=mapped_column(DateTime(timezone=True),default=now)
class LeaveBalance(Base):
    __tablename__='leave_balances'
    __table_args__=(UniqueConstraint('employee_id','policy_id','year',name='uq_leave_balance'),)
    id:Mapped[str]=mapped_column(String(36),primary_key=True,default=uid)
    employee_id:Mapped[str]=mapped_column(ForeignKey('employees.id'),index=True)
    policy_id:Mapped[str]=mapped_column(ForeignKey('leave_policies.id'))
    year:Mapped[int]=mapped_column(Integer)
    granted:Mapped[int]=mapped_column(Integer)
    note:Mapped[str]=mapped_column(String(500))
class Holiday(Base):
    __tablename__='public_holidays'
    id:Mapped[str]=mapped_column(String(36),primary_key=True,default=uid)
    day:Mapped[date]=mapped_column(Date,unique=True)
    name:Mapped[str]=mapped_column(String(120))
class Case(Base):
    __tablename__='administrative_cases'
    id:Mapped[str]=mapped_column(String(36),primary_key=True,default=uid)
    reference:Mapped[str]=mapped_column(String(60),unique=True,index=True)
    kind:Mapped[str]=mapped_column(String(30),index=True)
    title:Mapped[str]=mapped_column(String(180))
    body:Mapped[str]=mapped_column(Text)
    employee_id:Mapped[str|None]=mapped_column(ForeignKey('employees.id'),index=True)
    created_by:Mapped[str]=mapped_column(ForeignKey('users.id'))
    assigned_to:Mapped[str|None]=mapped_column(ForeignKey('users.id'))
    policy_id:Mapped[str|None]=mapped_column(ForeignKey('leave_policies.id'))
    source_unit_id:Mapped[str|None]=mapped_column(ForeignKey('organization_units.id'))
    target_unit_id:Mapped[str|None]=mapped_column(ForeignKey('organization_units.id'))
    start_date:Mapped[date|None]=mapped_column(Date)
    end_date:Mapped[date|None]=mapped_column(Date)
    due_date:Mapped[date|None]=mapped_column(Date)
    days:Mapped[int|None]=mapped_column(Integer)
    data:Mapped[str]=mapped_column(Text,default='{}')
    status:Mapped[str]=mapped_column(String(40),default='submitted',index=True)
    final_role:Mapped[str|None]=mapped_column(String(40))
    version:Mapped[int]=mapped_column(Integer,default=1)
    created_at:Mapped[datetime]=mapped_column(DateTime(timezone=True),default=now)
    updated_at:Mapped[datetime]=mapped_column(DateTime(timezone=True),default=now,onupdate=now)
class Approval(Base):
    __tablename__='workflow_approvals'
    id:Mapped[str]=mapped_column(String(36),primary_key=True,default=uid)
    case_id:Mapped[str]=mapped_column(ForeignKey('administrative_cases.id'),index=True)
    actor_id:Mapped[str]=mapped_column(ForeignKey('users.id'))
    action:Mapped[str]=mapped_column(String(50))
    comment:Mapped[str]=mapped_column(Text)
    created_at:Mapped[datetime]=mapped_column(DateTime(timezone=True),default=now)
class Notification(Base):
    __tablename__='notifications'
    id:Mapped[str]=mapped_column(String(36),primary_key=True,default=uid)
    user_id:Mapped[str]=mapped_column(ForeignKey('users.id'),index=True)
    case_id:Mapped[str|None]=mapped_column(ForeignKey('administrative_cases.id'))
    title:Mapped[str]=mapped_column(String(180))
    document_id:Mapped[str|None]=mapped_column(ForeignKey('employee_documents.id'))
    event_key:Mapped[str|None]=mapped_column(String(300),unique=True)
    read:Mapped[bool]=mapped_column(Boolean,default=False)
    created_at:Mapped[datetime]=mapped_column(DateTime(timezone=True),default=now)
class Document(Base):
    __tablename__='employee_documents'
    id:Mapped[str]=mapped_column(String(36),primary_key=True,default=uid)
    employee_id:Mapped[str]=mapped_column(ForeignKey('employees.id'),index=True)
    title:Mapped[str]=mapped_column(String(180))
    category:Mapped[str]=mapped_column(String(60))
    employee_visible:Mapped[bool]=mapped_column(Boolean,default=False)
    created_by:Mapped[str]=mapped_column(ForeignKey('users.id'))
    archived:Mapped[bool]=mapped_column(Boolean,default=False)
class DocumentVersion(Base):
    __tablename__='document_versions'
    __table_args__=(UniqueConstraint('document_id','number',name='uq_document_version'),)
    id:Mapped[str]=mapped_column(String(36),primary_key=True,default=uid)
    document_id:Mapped[str]=mapped_column(ForeignKey('employee_documents.id'),index=True)
    number:Mapped[int]=mapped_column(Integer)
    object_key:Mapped[str]=mapped_column(String(500),unique=True)
    filename:Mapped[str]=mapped_column(String(180))
    content_type:Mapped[str]=mapped_column(String(80))
    size:Mapped[int]=mapped_column(Integer)
    checksum:Mapped[str]=mapped_column(String(64))
    uploaded_by:Mapped[str]=mapped_column(ForeignKey('users.id'))
    verified:Mapped[bool]=mapped_column(Boolean,default=False)
    expiry_date:Mapped[date|None]=mapped_column(Date)
    created_at:Mapped[datetime]=mapped_column(DateTime(timezone=True),default=now)
