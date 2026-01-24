from datetime import datetime, timezone
import uuid

from BTrees.OOBTree import OOBTree

from ...constants import FORM_VERSIONS_KEY
from ...utils import ensure_timezone_aware


def ensure_form_versions(annos):
    if FORM_VERSIONS_KEY not in annos:
        annos[FORM_VERSIONS_KEY] = OOBTree()
    return annos[FORM_VERSIONS_KEY]


def list_form_versions(annos):
    return list(annos.get(FORM_VERSIONS_KEY, {}).values())


def sorted_form_versions(annos, reverse=False):
    versions = list_form_versions(annos)
    return sorted(
        versions,
        key=lambda x: ensure_timezone_aware(x["created"]),
        reverse=reverse,
    )


def latest_form_json(annos):
    versions = sorted_form_versions(annos)
    return versions[-1]["form_json"] if versions else {}


def latest_form_version_id(annos):
    versions = sorted_form_versions(annos)
    return versions[-1]["id"] if versions else ""


def save_form_version(annos, form_json, user_id, locked=False, version_id=None):
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
