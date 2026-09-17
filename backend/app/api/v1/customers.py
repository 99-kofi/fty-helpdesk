from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from app.core.database import get_db
from app.core.deps import get_current_user, require_role
from app.models.conversation import Conversation
from app.models.customer import Customer
from app.models.user import User
from app.schemas import CustomerIn, CustomerOut

router = APIRouter(prefix="/customers", tags=["customers"], dependencies=[Depends(get_current_user)])


@router.get("", response_model=list[CustomerOut])
def list_customers(db: Session = Depends(get_db), me: User = Depends(get_current_user)):
    q = db.query(Customer)
    if me.role != "admin":
        # Workers see only customers in their own queue.
        q = (q.join(Conversation, Conversation.customer_id == Customer.id)
             .filter(Conversation.assigned_agent_id == me.id).distinct())
    return q.order_by(Customer.id.desc()).limit(100).all()


@router.post("", response_model=CustomerOut, dependencies=[Depends(require_role("admin"))])
def create_customer(data: CustomerIn, db: Session = Depends(get_db)):
    c = Customer(**data.model_dump())
    db.add(c)
    db.commit()
    db.refresh(c)
    return c
