from app.channels.base import BaseAdapter, InternalMessage


class InstagramAdapter(BaseAdapter):
    channel = "instagram"

    def normalize(self, payload: dict) -> list[InternalMessage]:
        out: list[InternalMessage] = []
        for entry in payload.get("entry", []):
            for item in entry.get("messaging", []):
                out.append(InternalMessage(
                    channel="instagram",
                    external_user_id=str(item.get("sender", {}).get("id", "unknown")),
                    content=item.get("message", {}).get("text", ""),
                    external_message_id=item.get("message", {}).get("mid"),
                    metadata=item,
                ))
        return out
