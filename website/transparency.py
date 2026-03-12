import uuid
from datetime import datetime, timezone

from django.core.cache import cache

GLOBAL_SCOPE = "global"
MAX_EVENTS_PER_SCOPE = 25


def page_scope(name):
    return f"page:{name}"


def match_scope(match_id):
    return f"match:{match_id}"


def _cache_key(scope):
    return f"transparency:events:{scope}"


def _serialize_event(event):
    serialized = dict(event)
    occurred_at = serialized.get("occurred_at")
    if isinstance(occurred_at, datetime):
        serialized["occurred_at"] = occurred_at.astimezone(timezone.utc).isoformat()
    return serialized


def record_event(
    *,
    scope,
    category,
    source,
    action,
    summary,
    detail="",
    status="info",
    route="",
    entity_ref="",
    scopes=None,
):
    event = _serialize_event(
        {
            "id": str(uuid.uuid4()),
            "occurred_at": datetime.now(timezone.utc),
            "category": category,
            "source": source,
            "action": action,
            "summary": summary,
            "detail": detail,
            "status": status,
            "route": route,
            "entity_ref": str(entity_ref) if entity_ref else "",
        }
    )

    target_scopes = [scope]
    for extra_scope in scopes or []:
        if extra_scope not in target_scopes:
            target_scopes.append(extra_scope)

    for target_scope in target_scopes:
        cache_key = _cache_key(target_scope)
        events = cache.get(cache_key, [])
        events.insert(0, event)
        cache.set(cache_key, events[:MAX_EVENTS_PER_SCOPE], None)

    return event


def get_events(scope, limit=10):
    return list(cache.get(_cache_key(scope), []))[:limit]


def clear_events(*scopes):
    for scope in scopes:
        cache.delete(_cache_key(scope))
