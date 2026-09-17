"""Queue abstraction: Redis/RQ in prod, in-process fallback for local dev."""
from collections import deque

_local: deque = deque()

try:
    import redis  # noqa
    from app.core.config import settings  # noqa
    _redis_available = True
except Exception:
    _redis_available = False


def enqueue(kind: str, payload: dict) -> None:
    if _redis_available:
        try:
            import redis as _r
            from app.core.config import settings as _s
            r = _r.Redis.from_url(_s.redis_url)
            r.rpush(f"fty:{kind}", __import__("json").dumps(payload))
            return
        except Exception:
            pass
    _local.append((kind, payload))


def redis_reachable() -> bool:
    """True when a real Redis is up (i.e. an external worker will drain the queue)."""
    if not _redis_available:
        return False
    try:
        import redis as _r
        from app.core.config import settings as _s
        _r.Redis.from_url(_s.redis_url).ping()
        return True
    except Exception:
        return False


def process_sync() -> int:
    """Used in tests/dev: drain local queue through message worker."""
    from app.workers.tasks import handle_message_event
    n = 0
    while _local:
        kind, payload = _local.popleft()
        if kind == "message":
            handle_message_event(payload["channel"], payload["payload"])
            n += 1
    return n
