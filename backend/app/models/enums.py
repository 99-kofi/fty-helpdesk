import enum


class Role(str, enum.Enum):
    admin = "admin"
    manager = "manager"
    agent = "agent"


class Channel(str, enum.Enum):
    instagram = "instagram"
    whatsapp = "whatsapp"
    facebook = "facebook"
    email = "email"
    web = "web"


class ConversationStatus(str, enum.Enum):
    new = "new"
    open = "open"
    assigned = "assigned"
    in_progress = "in_progress"
    waiting_for_customer = "waiting_for_customer"
    resolved = "resolved"
    closed = "closed"
    reopened = "reopened"


class TicketStatus(str, enum.Enum):
    open = "open"
    in_progress = "in_progress"
    waiting = "waiting"
    resolved = "resolved"
    closed = "closed"


class Priority(str, enum.Enum):
    low = "low"
    normal = "normal"
    high = "high"
    urgent = "urgent"
