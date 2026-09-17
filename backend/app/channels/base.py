"""Adapter interface (spec §3): normalize platform payloads → InternalMessage."""
from dataclasses import dataclass, field
from typing import Any


@dataclass
class InternalMessage:
    channel: str
    external_user_id: str
    content: str
    external_message_id: str | None = None
    attachments: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)


class BaseAdapter:
    channel = "base"

    def normalize(self, payload: dict) -> list[InternalMessage]:
        raise NotImplementedError
