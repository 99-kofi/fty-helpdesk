from app.channels.base import BaseAdapter  # noqa
from app.channels.instagram import InstagramAdapter  # noqa
from app.channels.adapters import WhatsAppAdapter, FacebookAdapter, EmailAdapter  # noqa

ADAPTERS: dict[str, BaseAdapter] = {
    "instagram": InstagramAdapter(),
    "whatsapp": WhatsAppAdapter(),
    "facebook": FacebookAdapter(),
    "email": EmailAdapter(),
}
