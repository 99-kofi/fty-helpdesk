from pydantic import BaseModel, EmailStr


class UserOut(BaseModel):
    id: int
    name: str
    email: str  # plain str: seed/dev domains like .local fail strict EmailStr
    role: str
    team: str | None = None
    availability: str = "available"
    max_active: int = 10
    class Config:
        from_attributes = True


class LoginIn(BaseModel):
    email: EmailStr
    password: str


class TokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"


class CustomerIn(BaseModel):
    name: str | None = None
    email: str | None = None
    phone: str | None = None


class CustomerOut(CustomerIn):
    id: int
    class Config:
        from_attributes = True


class ConversationIn(BaseModel):
    customer_id: int
    channel: str = "web"
    priority: str = "normal"


class ConversationOut(ConversationIn):
    id: int
    status: str
    assigned_agent_id: int | None = None
    assigned_team: str | None = None
    class Config:
        from_attributes = True


class MessageIn(BaseModel):
    sender_type: str = "agent"
    sender_id: str | None = None
    content: str
    message_type: str = "text"


class MessageOut(MessageIn):
    id: int
    conversation_id: int
    class Config:
        from_attributes = True


class TicketIn(BaseModel):
    conversation_id: int
    category: str | None = None
    priority: str = "normal"


class TicketOut(TicketIn):
    id: int
    status: str
    assigned_to: int | None = None
    class Config:
        from_attributes = True
