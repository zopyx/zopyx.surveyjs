"""Helpers for storing and retrieving versioned SurveyJS form definitions."""

from datetime import datetime, timezone
import uuid

from BTrees.OOBTree import OOBTree

from ...constants import FORM_VERSIONS_KEY
from ...utils import ensure_timezone_aware


def ensure_form_versions(annos):
    """Ensure the form version container exists in annotations."""
    if FORM_VERSIONS_KEY not in annos:
        annos[FORM_VERSIONS_KEY] = OOBTree()
    return annos[FORM_VERSIONS_KEY]


def list_form_versions(annos):
    """Return all stored form versions as a list."""
    return list(annos.get(FORM_VERSIONS_KEY, {}).values())


def sorted_form_versions(annos, reverse=False):
    """Return form versions sorted by creation time."""
    versions = list_form_versions(annos)
    return sorted(
        versions,
        key=lambda x: ensure_timezone_aware(x["created"]),
        reverse=reverse,
    )


def latest_form_json(annos):
    """Return the latest stored form JSON or an empty object."""
    versions = sorted_form_versions(annos)
    return versions[-1]["form_json"] if versions else {}


def latest_form_version_id(annos):
    """Return the identifier of the latest stored form version."""
    versions = sorted_form_versions(annos)
    return versions[-1]["id"] if versions else ""


def save_form_version(annos, form_json, user_id, locked=False, version_id=None):
    """Create and persist a new form version entry in annotations."""
    ensure_form_versions(annos)
    data = dict(
        id=version_id or str(uuid.uuid4()),
        created=datetime.now(timezone.utc),
        user=user_id,
        form_json=form_json,
        locked=locked,
    )
    annos[FORM_VERSIONS_KEY][data["id"]] = data
    return data
