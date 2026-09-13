"""GenericSetup import steps of the optional ``zopyx.surveyjs:demo`` profile.

The profile turns an existing site into a ready-to-explore demo:

* the SurveyJS theme presets that ``scripts/init_plone.py`` also seeds
  (``light``, ``dark``, ``light-no-panels``, ``dark-no-panels``) so that a
  stored survey theme always resolves, and
* a published ``demo-forms`` folder with three complex English example forms
  that each demonstrate a different scope (HR onboarding, customer
  satisfaction, event registration) and each use a different theme.

Both steps are idempotent: themes are seeded by name and forms by id, and a
form only receives a new version when its shipped definition changed. That
keeps ``profile re-install`` safe for a site that already contains demo
content.
"""

from datetime import datetime, timezone
from pathlib import Path
from typing import NamedTuple
import logging
import uuid

import orjson
from BTrees.OOBTree import OOBTree
from plone import api
from plone.api.exc import InvalidParameterError
from zope.annotation.interfaces import IAnnotations

from .browser.services import themes as themes_service
from .constants import FORM_VERSIONS_KEY, RESULTS_KEY
from .utils import ensure_timezone_aware

logger = logging.getLogger(__name__)

PROFILE_PATH = Path(__file__).resolve().parent / "profiles" / "demo"
THEMES_PATH = PROFILE_PATH / "themes"
FORMS_PATH = PROFILE_PATH / "forms"

DEMO_FOLDER_ID = "demo-forms"
DEMO_FOLDER_TITLE = "Demo Forms"
DEMO_LANGUAGE = "en"
DEMO_USER = "zopyx.surveyjs:demo"


class DemoTheme(NamedTuple):
    """A SurveyJS theme preset shipped with the demo profile."""

    name: str
    seed_file: str
    palette: str
    panelless: bool


class DemoForm(NamedTuple):
    """A demo form definition shipped with the demo profile."""

    id: str
    title: str
    description: str
    form_file: str
    theme: str


# Same presets (and the same seed files) that scripts/init_plone.py seeds via
# themes_service; the profile ships its own copies so the package is
# self-contained.
DEFAULT_THEMES = (
    DemoTheme("light", "light", "light", False),
    DemoTheme("dark", "dark", "dark", False),
    DemoTheme("light-no-panels", "light-no-panels", "light", True),
    DemoTheme("dark-no-panels", "dark-no-panels", "dark", True),
)

# (survey id, title, description, form definition, theme name)
DEMO_FORMS = (
    DemoForm(
        "employee-onboarding",
        "Employee Onboarding",
        "Human resources onboarding intake for a new hire.",
        "employee_onboarding.json",
        "light",
    ),
    DemoForm(
        "customer-satisfaction",
        "Customer Satisfaction Survey",
        "Product and support satisfaction for an existing customer account.",
        "customer_satisfaction.json",
        "dark",
    ),
    DemoForm(
        "conference-registration",
        "Conference Registration",
        "Registration and session booking for a two-day conference.",
        "conference_registration.json",
        "light-no-panels",
    ),
)


def _resolve_site(context):
    """Return the Plone site for a GenericSetup step context or content object."""
    get_site = getattr(context, "getSite", None)
    if callable(get_site):
        site = get_site()
        if site is not None:
            return site
    return api.portal.get()


def _load_json(path):
    return orjson.loads(Path(path).read_bytes())


def _publish(obj):
    """Publish ``obj`` unless it already is published."""
    try:
        state = api.content.get_state(obj)
    except InvalidParameterError:
        state = None
    if state == "published":
        return
    try:
        api.content.transition(obj=obj, transition="publish")
    except InvalidParameterError:
        logger.warning(
            "zopyx.surveyjs:demo - cannot publish %s (no 'publish' transition)",
            obj.absolute_url(),
        )


def _set_language(obj, language):
    try:
        obj.language = language
    except AttributeError:
        # Content types without a language field (e.g. a plain Dexterity type
        # that does not use the DublinCore behavior) are fine.
        pass


def seed_demo_themes(site, user_id=DEMO_USER):
    """Seed the SurveyJS theme presets; return the names of created themes."""
    annotations = IAnnotations(site)
    existing = {theme.get("name") for theme in themes_service.list_themes(annotations)}
    created = []
    for theme in DEFAULT_THEMES:
        if theme.name in existing:
            logger.info("zopyx.surveyjs:demo - theme '%s' exists, skipping", theme.name)
            continue
        seed_path = THEMES_PATH / f"{theme.seed_file}.json"
        if not seed_path.exists():
            logger.warning("zopyx.surveyjs:demo - missing theme seed %s", seed_path)
            continue
        themes_service.create_theme(
            annotations, theme.name, _load_json(seed_path), user_id=user_id
        )
        created.append(theme.name)
    return created


def _theme_ids_by_name(site):
    annotations = IAnnotations(site)
    return {
        theme.get("name"): theme.get("id")
        for theme in themes_service.list_themes(annotations)
        if theme.get("id")
    }


def _newest_form_json(versions):
    """Return the form JSON of the newest stored version, or None."""
    if not versions:
        return None
    newest = max(
        versions.values(),
        key=lambda version: ensure_timezone_aware(version["created"]),
    )
    return newest.get("form_json")


def _ensure_demo_folder(site):
    folder = site.get(DEMO_FOLDER_ID)
    if folder is None:
        folder = api.content.create(
            type="Folder",
            container=site,
            id=DEMO_FOLDER_ID,
            title=DEMO_FOLDER_TITLE,
        )
    else:
        folder.title = DEMO_FOLDER_TITLE
    _set_language(folder, DEMO_LANGUAGE)
    folder.reindexObject()
    _publish(folder)
    return folder


def _ensure_form_version(survey, form_json, user_id):
    """Store the shipped form definition as a new version when it changed."""
    annotations = IAnnotations(survey)
    versions = annotations.setdefault(FORM_VERSIONS_KEY, OOBTree())
    annotations.setdefault(RESULTS_KEY, OOBTree())
    if _newest_form_json(versions) == form_json:
        return False
    version_id = str(uuid.uuid4())
    versions[version_id] = dict(
        id=version_id,
        created=datetime.now(timezone.utc),
        user=user_id,
        form_json=form_json,
    )
    return True


def create_demo_forms(site, user_id=DEMO_USER):
    """Create/refresh the demo-forms folder; return the survey ids."""
    container = _ensure_demo_folder(site)
    theme_ids = _theme_ids_by_name(site)
    created = []
    for spec in DEMO_FORMS:
        form_json = _load_json(FORMS_PATH / spec.form_file)
        survey = container.get(spec.id)
        if survey is not None and survey.portal_type != "Survey":
            logger.warning(
                "zopyx.surveyjs:demo - '%s' already exists and is not a Survey; "
                "skipping it",
                spec.id,
            )
            continue
        if survey is None:
            survey = api.content.create(
                type="Survey",
                container=container,
                id=spec.id,
                title=spec.title,
                description=spec.description,
            )
        else:
            survey.title = spec.title
            survey.description = spec.description
        _set_language(survey, DEMO_LANGUAGE)
        survey.actions = {"store"}
        theme_id = theme_ids.get(spec.theme)
        if theme_id:
            survey.theme = theme_id
        else:
            logger.warning(
                "zopyx.surveyjs:demo - theme '%s' is missing for form '%s'",
                spec.theme,
                spec.id,
            )
        _ensure_form_version(survey, form_json, user_id)
        survey.reindexObject()
        _publish(survey)
        created.append(spec.id)
    return created


def import_demo_themes(context):
    """GenericSetup step: seed the demo SurveyJS themes."""
    site = _resolve_site(context)
    created = seed_demo_themes(site)
    if created:
        logger.info("zopyx.surveyjs:demo - seeded themes: %s", ", ".join(created))
    return "SurveyJS demo themes imported."


def import_demo_forms(context):
    """GenericSetup step: create the demo-forms folder and its forms."""
    site = _resolve_site(context)
    created = create_demo_forms(site)
    logger.info("zopyx.surveyjs:demo - demo forms available: %s", ", ".join(created))
    return "SurveyJS demo forms imported."
