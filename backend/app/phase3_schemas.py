from datetime import date, datetime
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, model_validator

class Input(BaseModel):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True)
class Training(Input):
    provider: str = Field(min_length=2, max_length=180)
    hours: float = Field(ge=0, le=2000)
    credits: float = Field(ge=0, le=1000)
    certificate_reference: str = Field(default='', max_length=250)
class Promotion(Input):
    final_role: Literal['director','hr_admin']
    target_grade: str = Field(min_length=1, max_length=80)
    policy_reference: str = Field(min_length=3, max_length=250)
    evidence: str = Field(min_length=3, max_length=4000)
class Retirement(Input):
    final_role: Literal['director','hr_admin']
    policy_reference: str = Field(min_length=3, max_length=250)
    reason: str = Field(min_length=3, max_length=1000)
    checklist: list[str] = Field(min_length=1, max_length=30)
    @model_validator(mode='after')
    def check_items(self):
        if any(not x.strip() or len(x)>180 for x in self.checklist) or len(set(self.checklist))!=len(self.checklist):raise ValueError('Use distinct checklist items of 1–180 characters')
        return self
class Appraisal(Input):
    objectives: str = Field(min_length=3, max_length=4000)
    assessment: str = Field(default='', max_length=6000)
class RecordInput(Input):
    kind: Literal['training','promotion','retirement','appraisal']
    employee_id: str
    title: str = Field(min_length=3, max_length=180)
    start_date: date
    end_date: date
    reviewer_id: str | None = None
    data: dict
    @model_validator(mode='after')
    def validate_data(self):
        if self.end_date<self.start_date:raise ValueError('End date must follow start date')
        schema={'training':Training,'promotion':Promotion,'retirement':Retirement,'appraisal':Appraisal}[self.kind]
        self.data=schema.model_validate(self.data).model_dump()
        return self
class RecordEdit(Input):
    version: int = Field(ge=1)
    title: str = Field(min_length=3, max_length=180)
    start_date: date
    end_date: date
    data: dict
class Action(Input):
    version: int = Field(ge=1)
    action: str = Field(min_length=1, max_length=40)
    comment: str = Field(min_length=3, max_length=2000)
    completed_items: list[str] | None = None
class ShiftInput(Input):
    employee_id: str
    starts_at: datetime
    ends_at: datetime
    duty: str = Field(min_length=2, max_length=120)
    @model_validator(mode='after')
    def dates(self):
        if not self.starts_at.tzinfo or not self.ends_at.tzinfo:raise ValueError('Include a timezone offset')
        hours=(self.ends_at-self.starts_at).total_seconds()/3600
        if hours<=0 or hours>24:raise ValueError('A shift must last more than zero and at most 24 hours')
        return self
class AttendanceInput(Input):
    employee_id: str
    day: date
    outcome: Literal['present','absent','late','excused','off_duty']
    note: str = Field(min_length=3, max_length=1000)
    version: int = Field(default=0, ge=0)
class EstablishmentInput(Input):
    final_role: Literal['director','hr_admin']
    unit_id: str
    cadre: str = Field(min_length=1, max_length=100)
    positions: int = Field(ge=0, le=10000)
    reference: str = Field(min_length=3, max_length=250)
    effective_date: date

class RetirementPolicy(Input):
    version: int = Field(ge=0)
    reference: str = Field(min_length=3,max_length=250)
    age_years: int = Field(ge=18,le=100)
    notice_days: int = Field(ge=0,le=3650)
