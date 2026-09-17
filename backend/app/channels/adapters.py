from app.channels.base import BaseAdapter, InternalMessage


class WhatsAppAdapter(BaseAdapter):
    channel = "whatsapp"

    def normalize(self, payload: dict) -> list[InternalMessage]:
        out: list[InternalMessage] = []
        for entry in payload.get("entry", []):
            for change in entry.get("changes", []):
                for msg in change.get("value", {}).get("messages", []):
                    if msg.get("type") == "text":
                        out.append(InternalMessage(
                            channel="whatsapp",
                            external_user_id=msg.get("from", "unknown"),
                            content=msg.get("text", {}).get("body", ""),
                            external_message_id=msg.get("id"),
                            metadata=msg,
                        ))
        return out


class FacebookAdapter(BaseAdapter):
    channel = "facebook"

    def normalize(self, payload: dict) -> list[InternalMessage]:
        from app.channels.instagram import InstagramAdapter
        msgs = InstagramAdapter().normalize(payload)
        for m in msgs:
            m.channel = "facebook"
        return msgs


class EmailAdapter(BaseAdapter):
    channel = "email"

    def normalize(self, payload: dict) -> list[InternalMessage]:
        if "from" not in payload:
            return []
        return [InternalMessage(
            channel="email",
            external_user_id=str(payload.get("from")),
            content=str(payload.get("body", "")),
            metadata=payload,
        )]
