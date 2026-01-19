from datetime import timezone


def ensure_timezone_aware(dt):
    """Convert naive datetime to UTC-aware datetime."""
    if dt.tzinfo is None or dt.tzinfo.utcoffset(dt) is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt
