"""Identity Resolution (spec §5): (channel, external_user_id) → single Customer."""
from sqlalchemy.orm import Session
from app.models.customer import Customer, CustomerIdentity


def resolve_customer(db: Session, channel: str, external_user_id: str, name: str | None = None) -> Customer:
    ident = db.query(CustomerIdentity).filter_by(channel=channel, external_user_id=external_user_id).first()
    if ident:
        return db.get(Customer, ident.customer_id)
    customer = Customer(name=name)
    db.add(customer)
    db.flush()
    db.add(CustomerIdentity(customer_id=customer.id, channel=channel, external_user_id=external_user_id))
    db.commit()
    db.refresh(customer)
    return customer
