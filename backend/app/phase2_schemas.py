from datetime import date
from pydantic import BaseModel,Field,ConfigDict,model_validator
from typing import Literal
class Strict(BaseModel):
    model_config=ConfigDict(extra='forbid',str_strip_whitespace=True)
class PolicyInput(Strict):
    name:str=Field(min_length=2,max_length=120)
    reference:str=Field(min_length=5,max_length=250)
    requires_balance:bool
    count_basis:Literal['calendar','working']
    working_days:list[int]=Field(default_factory=list,max_length=7)
    final_role:Literal['director','hr_admin']
    @model_validator(mode='after')
    def days(self):
        if self.count_basis=='working' and not self.working_days:raise ValueError('Select at least one working weekday')
        if len(set(self.working_days))!=len(self.working_days) or any(d<0 or d>6 for d in self.working_days):raise ValueError('Working days use unique weekday numbers from 0 (Monday) to 6 (Sunday)')
        return self
class BalanceInput(Strict):
    employee_id:str
    policy_id:str
    year:int=Field(ge=2000,le=2100)
    granted:int=Field(ge=0,le=366)
    note:str=Field(min_length=5,max_length=500)
class HolidayInput(Strict):
    day:date
    name:str=Field(min_length=2,max_length=120)
class WorkflowConfig(Strict):
    transfer_final_role:Literal['director','hr_admin']
    policy_reference:str=Field(min_length=5,max_length=250)
    letter_heading:str=Field(min_length=2,max_length=300)
    signatory_name:str=Field(min_length=2,max_length=120)
    signatory_title:str=Field(min_length=2,max_length=120)
class LeaveInput(Strict):
    employee_id:str
    policy_id:str
    start_date:date
    end_date:date
    reason:str=Field(min_length=5,max_length=1000)
    @model_validator(mode='after')
    def dates(self):
        if self.end_date<self.start_date or (self.end_date-self.start_date).days>366:raise ValueError('Choose a valid leave period up to 367 calendar days')
        if self.start_date<date.today():raise ValueError('New leave applications cannot be backdated')
        return self
class TransferInput(Strict):
    employee_id:str
    target_unit_id:str
    effective_date:date
    movement_type:Literal['Internal transfer','Reassignment','Temporary deployment','Secondment']
    end_date:date|None=None
    reason:str=Field(min_length=5,max_length=1000)
    @model_validator(mode='after')
    def dates(self):
        if self.end_date and self.end_date<self.effective_date:raise ValueError('End date cannot precede the effective date')
        if self.movement_type in {'Temporary deployment','Secondment'} and not self.end_date:raise ValueError('Specify the planned end date')
        return self
class AdminInput(Strict):
    title:str=Field(min_length=5,max_length=180)
    body:str=Field(min_length=5,max_length=3000)
    employee_id:str|None=None
    due_date:date|None=None
class CorrespondenceInput(Strict):
    title:str=Field(min_length=5,max_length=180)
    body:str=Field(min_length=5,max_length=10000)
    direction:Literal['Incoming','Outgoing','Internal memo']
    correspondent:str=Field(min_length=2,max_length=180)
    external_reference:str=Field(default='',max_length=120)
    due_date:date|None=None
class ActionInput(Strict):
    action:Literal['recommend','validate','approve','reject','cancel','request_cancellation','approve_cancellation','start_leave','report_return','confirm_return','acknowledge','apply','assign','respond','close']
    version:int=Field(ge=1)
    comment:str=Field(default='',max_length=2000)
    assigned_to:str|None=None
