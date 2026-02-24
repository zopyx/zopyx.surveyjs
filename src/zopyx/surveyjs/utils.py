from datetime import timezone
import logging
from typing import Any

from plone.registry.interfaces import IRegistry
from zope.component import getUtility

from .interfaces import IFormsSettings

logger = logging.getLogger(__name__)


def ensure_timezone_aware(dt):
    """Convert naive datetime to UTC-aware datetime."""
    if dt.tzinfo is None or dt.tzinfo.utcoffset(dt) is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt


def resolve_mail_settings(context, field_names: list[str]) -> dict[str, Any]:
    """Resolve mail-related settings from survey-local or global registry settings.

    When ``context.use_global_mail_settings`` is truthy, values are read from the
    control panel (``IFormsSettings``). If a requested field is not present on the
    registry schema, this helper falls back to the local survey value for that field.

    If the toggle is absent (legacy objects), local values are used by default for
    backwards compatibility.
    """
    use_global = bool(getattr(context, "use_global_mail_settings", False))
    settings = None
    if use_global:
        try:
            registry = getUtility(IRegistry)
            settings = registry.forInterface(IFormsSettings, check=False)
        except Exception:
            logger.exception("Failed to load global mail settings; falling back to local")
            settings = None
            use_global = False

    resolved: dict[str, Any] = {
        "use_global_mail_settings": use_global,
    }
    for field_name in field_names:
        if use_global and settings is not None and hasattr(settings, field_name):
            resolved[field_name] = getattr(settings, field_name, None)
        else:
            resolved[field_name] = getattr(context, field_name, None)
    return resolved
