import json


def parse_sse_event(event: str) -> dict | None:
    if not event.startswith("data: "):
        return None
    try:
        return json.loads(event[6:].strip())
    except json.JSONDecodeError:
        return None
