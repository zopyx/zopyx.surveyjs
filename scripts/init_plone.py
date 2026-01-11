"""Initialize a demo Plone site with zopyx.surveyjs installed.

This script creates a demo Plone site with:
- Barceloneta enabled and a published logo image for the welcome page
- Addable types limited to Folder, Document, Survey
- Demo surveys seeded from JSON files under scripts/forms/
- Intro texts loaded from HTML snippets under scripts/forms/
- A welcome page set as default
- Demo user `forms` / `formsarecool` with Editor role

Run it in a Plone instance interpreter, e.g.:
  bin/instance run scripts/init_plone.py
"""

from AccessControl.SecurityManagement import newSecurityManager
from BTrees.OOBTree import OOBTree
from plone.app.textfield.value import RichTextValue
from plone.api.exc import InvalidParameterError
from plone.app.theming.browser.controlpanel import ThemingControlpanel
from Products.CMFPlone.factory import addPloneSite
from datetime import datetime, timezone
import os
from Testing.makerequest import makerequest
from pathlib import Path
import orjson
from plone import api
from plone.namedfile.file import NamedBlobImage
from zopyx.surveyjs.browser.views import FORM_VERSIONS_KEY, RESULTS_KEY
from zope.annotation.interfaces import IAnnotations
from zope.component.hooks import setSite
import transaction
import uuid


SITE_ID = "demo"
ADMIN = "admin2"


def _resolve_forms_path():
    """Return absolute path to scripts/forms based on this script's location."""
    here = Path(__file__).resolve()

    # 1) Direct sibling: scripts/forms relative to this file
    direct = here.parent / "forms"
    if direct.exists():
        return direct

    # 2) Walk up from the script location to find scripts/forms in project root
    for parent in here.parents:
        candidate = parent / "scripts" / "forms"
        if candidate.exists():
            return candidate

    # Fallback: the direct path even if missing (will raise later)
    return direct


FORMS_PATH = _resolve_forms_path()
ROOT_PATH = Path(__file__).resolve().parent.parent


def load_env_file():
    """Populate os.environ from a .env in the project root, ignoring existing keys."""
    env_path = ROOT_PATH / ".env"
    if not env_path.exists():
        return

    for line in env_path.read_text().splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if stripped.startswith("export "):
            stripped = stripped[len("export ") :].strip()
        if "=" not in stripped:
            continue
        key, value = stripped.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


def configure_ai_model_from_env():
    """Set the AI model and API key registry values from environment if provided."""
    ai_model = os.environ.get("AI_MODEL", "").strip()
    ai_key = os.environ.get("OPENAI_API_KEY", "").strip()

    if not ai_model and not ai_key:
        return

    try:
        if ai_model:
            api.portal.set_registry_record(
                "zopyx.surveyjs.interfaces.IFormsSettings.ai_model", ai_model
            )
            print(f"Configured AI model from environment: {ai_model}")
        if ai_key:
            api.portal.set_registry_record(
                "zopyx.surveyjs.interfaces.IFormsSettings.ai_api_key", ai_key
            )
            print("Configured AI API key from environment")
    except InvalidParameterError:
        print("AI registry records not found; skipping AI environment configuration")





def create_demo_survey(
    site,
    survey_id,
    title,
    description,
    form_json,
    intro_html=None,
    actions=None,
):
    survey = api.content.create(
        type="Survey",
        container=site,
        title=title,
        id=survey_id,
        description=description,
        text=RichTextValue(intro_html, "text/html", "text/html") if intro_html else None,
    )
    if actions:
        survey.actions = actions
    survey.reindexObject()
    api.content.transition(obj=survey, transition="publish")

    annos = IAnnotations(survey)
    annos.setdefault(FORM_VERSIONS_KEY, OOBTree())
    annos.setdefault(RESULTS_KEY, OOBTree())

    version_id = str(uuid.uuid4())
    annos[FORM_VERSIONS_KEY][version_id] = dict(
        id=version_id,
        created=datetime.now(timezone.utc),
        user=ADMIN,
        form_json=form_json,
    )
    return survey


def load_form_definition(name):
    form_path = FORMS_PATH / f"{name}.json"
    return orjson.loads(form_path.read_bytes())


def load_intro_text(name):
    intro_path = FORMS_PATH / f"{name}.html"
    return intro_path.read_text(encoding="utf-8").strip()


def set_form_intro_html(form_json, element_name, html):
    for page in form_json.get("pages", []):
        for element in page.get("elements", []):
            if element.get("type") == "html" and element.get("name") == element_name:
                element["html"] = html
                return


class MyThemingControlpanel(ThemingControlpanel):
    """
    A subclass of the standard ThemingControlpanel to override authorization.
    This allows the script to programmatically change theme settings without
    requiring the usual browser-based authentication and permissions.
    """

    def authorize(self):
        # Always return True to allow theme modifications.
        return True


acl = app.acl_users
admin_user = acl.getUser(ADMIN)
newSecurityManager(None, admin_user.__of__(acl))

load_env_file()

# Start clean: drop existing demo site if present
if SITE_ID in app.objectIds():
    app.manage_delObjects([SITE_ID])
    transaction.commit()

# Create fresh Plone site and install addon
addPloneSite(
    app,
    SITE_ID,
    distribution="classic",
    extension_ids=["plone.app.contenttypes:default"],
)
site = makerequest(app[SITE_ID])
setSite(site)
api.addon.install("zopyx.surveyjs")

# Apply Barceloneta theme
print("Enabling Barceloneta theme...")
site.REQUEST.form["form.button.Enable"] = "DONE"
site.REQUEST.form["themeName"] = "barceloneta"
view = MyThemingControlpanel(site, site.REQUEST)
view.update()
configure_ai_model_from_env()

# Create logo.jpg as Image content object
logo_path = Path(os.getcwd()) / "scripts" / "logo.jpg"
if logo_path.exists():
    logo_image = api.content.create(
        type="Image",
        container=site,
        id="logo",
        title="Privacy Forms Studio Logo",
        image=NamedBlobImage(
            data=logo_path.read_bytes(),
            filename="logo.jpg"
        )
    )
    logo_image.reindexObject()
    print("Created logo.jpg as Image content object")
else:
    print(f"logo.jpg not found at {logo_path}; skipping logo image creation")

transaction.commit()

site._p_jar.sync()

# Restrict addable types to essentials
allowed_types = {"Folder", "Document", "Survey", "Image"}
portal_types = api.portal.get_tool("portal_types")
for fti in portal_types.objectValues():
    fti.global_allow = fti.getId() in allowed_types

# Remove default folders
for obj_id in ("events", "news", "Members"):
    if obj_id in site.objectIds():
        site.manage_delObjects([obj_id])

# Seed event registration survey
event_form = load_form_definition("event_registration")

create_demo_survey(
    site,
    survey_id="event-registration",
    title="Event registration",
    description="Register for the event.",
    form_json=event_form,
)

welcome_html = load_intro_text("welcome")

# Add links to demo forms
welcome_html += """
<h3>Demo Forms</h3>
<ul>
  <li><a href="/Plone/demo/event-registration">Event registration</a></li>
  <li><a href="/Plone/demo/event-rsvp">Event registration / unregistration</a></li>
  <li><a href="/Plone/demo/mental-health-survey">Mental Health Survey</a></li>
  <li><a href="/Plone/demo/full-demo">Social Media Consumption Demo</a></li>
  <li><a href="/Plone/demo/food-feedback-demo">Food Ordering Service Feedback</a></li>
  <li><a href="/Plone/demo/order-form">Order form</a></li>
</ul>
"""

welcome = api.content.create(
    type="Document",
    container=site,
    title="Privacy Forms Studio",
    id="welcome",
    text=RichTextValue(
        welcome_html,
        "text/html",
        "text/html",
    ),
)
api.content.transition(obj=welcome, transition="publish")
welcome.reindexObject()
site.setDefaultPage("welcome")

# Mental Health survey (demo)
mental_intro = load_intro_text("mental_health_intro")
mental_form = load_form_definition("mental_health")
set_form_intro_html(mental_form, "introText", mental_intro)

create_demo_survey(
    site,
    survey_id="mental-health-survey",
    title="Mental Health Survey",
    description="A short, reflective check-in on wellbeing.",
    form_json=mental_form,
    intro_html=mental_intro,
    actions={"store"},
)

full_demo_intro = load_intro_text("full_demo_intro")
full_demo_form = load_form_definition("full_demo")
set_form_intro_html(full_demo_form, "demoIntro", full_demo_intro)

create_demo_survey(
    site,
    survey_id="full-demo",
    title="Social Media Consumption Demo",
    description="A comprehensive SurveyJS demo covering many field types.",
    form_json=full_demo_form,
    intro_html=full_demo_intro,
    actions={"store"},
)

feedback_form = load_form_definition("food_feedback")

create_demo_survey(
    site,
    survey_id="food-feedback-demo",
    title="Food Ordering Service Feedback",
    description="Rate a fictive food ordering service on three quick questions.",
    form_json=feedback_form,
    intro_html=load_intro_text("food_feedback_intro"),
    actions={"store"},
)

event_rsvp_form = load_form_definition("event_rsvp")

create_demo_survey(
    site,
    survey_id="event-rsvp",
    title="Event registration / unregistration",
    description="Register for the event or cancel an existing registration.",
    form_json=event_rsvp_form,
    actions={"store"},
)

order_form = load_form_definition("order_form")

create_demo_survey(
    site,
    survey_id="order-form",
    title="Order form",
    description="Collect simple cloth orders with customer info and order lines.",
    form_json=order_form,
    actions={"store"},
)

# Create a demo user with Editor role
if not api.user.get(username="forms"):
    api.user.create(username="forms", email="forms@example.com", password="formsarecool")
    api.user.grant_roles(username="forms", roles=["Editor"])
    print("Created demo user 'forms' with Editor role")
else:
    print("Demo user 'forms' already exists")

transaction.commit()
