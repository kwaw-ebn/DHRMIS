"""One logical personnel file per employee, referenced by their immutable staff ID."""
from fastapi import APIRouter,Depends
from sqlalchemy.orm import Session
from .db import get_db
from .models import User
from .security import current_user,HR,audit
from .phase2 import require_employee,case_query,document_query,doc_view,CATEGORIES,EMPLOYEE_CATEGORIES
from .phase2_models import Case,Document
from .phase3 import query_records
from .phase3_models import WorkforceRecord
router=APIRouter(prefix='/api/employees',tags=['Staff personnel files'])

@router.get('/{employee_id}/file')
def staff_file(employee_id:str,db:Session=Depends(get_db),user:User=Depends(current_user)):
    employee=require_employee(db,user,employee_id)
    can_documents=user.role in HR|{'employee'}
    docs=document_query(db,user).filter(Document.employee_id==employee.id) if can_documents else None
    cases=case_query(db,user).filter(Case.employee_id==employee.id)
    workflows=cases.order_by(Case.created_at.desc()).limit(100).all()
    workforce={};totals={}
    for kind in ['training','promotion','retirement','appraisal']:
        q=query_records(db,user,kind).filter(WorkforceRecord.employee_id==employee.id);totals[kind]=q.count()
        workforce[kind]=[{k:getattr(r,k) for k in ['id','title','start_date','end_date','status']} for r in q.order_by(WorkforceRecord.created_at.desc()).limit(100)]
    result={'file_number':employee.staff_id,'staff_id':employee.staff_id,'employee_id':employee.id,'employee_name':employee.full_name,'documents_allowed':can_documents,'document_categories':CATEGORIES if user.role in HR else sorted(EMPLOYEE_CATEGORIES) if can_documents else [],'documents':[doc_view(db,r)|{'can_add_version':user.role in HR or r.created_by==user.id} for r in docs.order_by(Document.title).limit(100)] if can_documents else [],'document_total':docs.count() if can_documents else None,'requests':[{'id':r.id,'reference':r.reference,'kind':r.kind,'title':r.title,'status':r.status,'created_at':r.created_at} for r in workflows],'request_total':cases.count(),'workforce':workforce,'workforce_totals':totals}
    audit(db,user,'STAFF_FILE_VIEWED',employee.id,detail='Scoped personnel file index');db.commit();return result
