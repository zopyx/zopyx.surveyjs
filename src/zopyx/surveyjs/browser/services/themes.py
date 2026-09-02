"""Helpers for storing and retrieving versioned SurveyJS theme definitions."""

from datetime import datetime, timezone
import uuid

from BTrees.OOBTree import OOBTree
from zope.annotation.interfaces import IAnnotations

from ...constants import THEMES_KEY, DEFAULT_THEME_KEY
from ...utils import ensure_timezone_aware


def ensure_themes(annotations):
    """Ensure the themes container exists in annotations."""
    if THEMES_KEY not in annotations:
        annotations[THEMES_KEY] = OOBTree()
    return annotations[THEMES_KEY]


def list_themes(annotations):
    """Return all stored themes as a list sorted by name."""
    themes = annotations.get(THEMES_KEY, {})
    return sorted(themes.values(), key=lambda t: str(t.get("name", "")).lower())


def get_theme(annotations, theme_id):
    """Return a single theme by id or None."""
    return annotations.get(THEMES_KEY, {}).get(theme_id)


def create_theme(annotations, name, theme_json=None, user_id=""):
    """Create a new theme with an initial version."""
    themes = ensure_themes(annotations)
    theme_id = str(uuid.uuid4())
    version_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc)
    theme_entry = dict(
        id=theme_id,
        name=name.strip(),
        created=now,
        modified=now,
        theme_json=theme_json or {},
        versions=OOBTree(),
    )
    theme_entry["versions"][version_id] = dict(
        id=version_id,
        created=now,
        user=user_id,
        theme_json=theme_json or {},
    )
    themes[theme_id] = theme_entry
    return theme_entry


def save_theme_current_version(annotations, theme_id, theme_json, user_id):
    """Overwrite the newest version of an existing theme."""
    themes = ensure_themes(annotations)
    theme = themes.get(theme_id)
    if theme is None:
        return None
    versions = theme.get("versions", {})
    if not versions:
        return None
    current_version = max(
        versions.values(),
        key=lambda version: ensure_timezone_aware(version["created"]),
    )
    current_version["theme_json"] = theme_json
    current_version["user"] = user_id
    theme["theme_json"] = theme_json
    theme["modified"] = datetime.now(timezone.utc)
    versions[current_version["id"]] = current_version
    themes[theme_id] = theme
    return theme


def save_theme_version(annotations, theme_id, theme_json, user_id):
    """Create a new version for an existing theme."""
    themes = ensure_themes(annotations)
    theme = themes.get(theme_id)
    if theme is None:
        return None
    version_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc)
    theme["theme_json"] = theme_json
    theme["modified"] = now
    theme["versions"][version_id] = dict(
        id=version_id,
        created=now,
        user=user_id,
        theme_json=theme_json,
    )
    themes[theme_id] = theme
    return theme


def restore_theme_version(annotations, theme_id, version_id):
    """Restore a theme to a previous version."""
    themes = ensure_themes(annotations)
    theme = themes.get(theme_id)
    if theme is None:
        return None
    version = theme.get("versions", {}).get(version_id)
    if version is None:
        return None
    theme["theme_json"] = version["theme_json"]
    theme["modified"] = datetime.now(timezone.utc)
    themes[theme_id] = theme
    return theme


def delete_theme(annotations, theme_id):
    """Remove a theme."""
    themes = ensure_themes(annotations)
    if theme_id in themes:
        del themes[theme_id]
        # Clear default if it was the default theme
        if get_default_theme_id(annotations) == theme_id:
            annotations.pop(DEFAULT_THEME_KEY, None)
        return True
    return False


def set_default_theme(annotations, theme_id):
    """Set a theme as the default. Returns False if theme_id doesn't exist."""
    themes = ensure_themes(annotations)
    if theme_id not in themes:
        return False
    annotations[DEFAULT_THEME_KEY] = theme_id
    return True


def get_default_theme_id(annotations):
    """Return the default theme ID, or None."""
    return annotations.get(DEFAULT_THEME_KEY, None)


def sorted_theme_versions(theme, reverse=False):
    """Return the theme's versions sorted by creation time."""
    versions = list(theme.get("versions", {}).values())
    return sorted(
        versions,
        key=lambda x: ensure_timezone_aware(x["created"]),
        reverse=reverse,
    )