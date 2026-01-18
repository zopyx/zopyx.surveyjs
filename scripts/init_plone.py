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
from zopyx.surveyjs.constants import FORM_VERSIONS_KEY, RESULTS_KEY
from zope.annotation.interfaces import IAnnotations
from zope.component import getMultiAdapter, getUtility
from zope.component.hooks import setSite
import transaction
import uuid
from plone.portlets.constants import CONTEXT_CATEGORY
from plone.portlets.interfaces import (
    ILocalPortletAssignmentManager,
    IPortletAssignmentMapping,
    IPortletManager,
)


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


def _env_bool(value, default=False):
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def configure_mail_from_env():
    """Configure Plone mail settings from environment variables if present."""

    # Support both generic and SURVEY_ prefixed env vars
    def _first(*keys):
        for key in keys:
            val = os.environ.get(key)
            if val:
                return val.strip()
        return ""

    smtp_host = _first("SMTP_HOST", "SURVEY_SMTP_HOST")
    smtp_port = _first("SMTP_PORT", "SURVEY_SMTP_PORT")
    smtp_user = _first("SMTP_USER", "SURVEY_SMTP_USERNAME")
    smtp_pass = _first("SMTP_PASSWORD", "SURVEY_SMTP_PASSWORD")
    smtp_tls = _env_bool(
        os.environ.get("SMTP_TLS", os.environ.get("SURVEY_SMTP_STARTTLS"))
    )
    smtp_ssl = _env_bool(os.environ.get("SMTP_SSL", os.environ.get("SURVEY_SMTP_SSL")))
    mail_from = _first("MAIL_FROM", "SURVEY_MAIL_FROM")
    mail_from_name = _first("MAIL_FROM_NAME", "SURVEY_MAIL_FROM_NAME")

    if not any([smtp_host, smtp_port, smtp_user, smtp_pass, mail_from, mail_from_name]):
        return

    try:
        if smtp_host:
            api.portal.set_registry_record("plone.smtp_host", smtp_host)
        if smtp_port:
            try:
                api.portal.set_registry_record("plone.smtp_port", int(smtp_port))
            except ValueError:
                print(f"Invalid SMTP_PORT '{smtp_port}', skipping port configuration")
        api.portal.set_registry_record("plone.smtp_userid", smtp_user or None)
        api.portal.set_registry_record("plone.smtp_pass", smtp_pass or None)
        api.portal.set_registry_record("plone.email_from_address", mail_from or None)
        api.portal.set_registry_record("plone.email_from_name", mail_from_name or None)
        print("Configured mail settings from environment")
    except InvalidParameterError:
        print(
            "Mail registry records not found; skipping mail environment configuration"
        )


def configure_site_languages():
    """Set site languages to English + German + Arabic + Japanese, with English as default."""
    try:
        api.portal.set_registry_record(
            "plone.available_languages", ["en", "de", "ar", "ja"]
        )
        api.portal.set_registry_record("plone.default_language", "en")
        optional_settings = {
            "plone.use_path_negotiation": True,
            "plone.use_content_negotiation": True,
            "plone.set_language_cookie": True,
            "plone.display_flags": True,
        }
        for key, value in optional_settings.items():
            try:
                api.portal.set_registry_record(key, value)
            except InvalidParameterError:
                continue
        print("Configured site languages: en (default), de, ar, ja")
    except InvalidParameterError:
        print("Language registry records not found; skipping language configuration")


def enable_language_selector():
    """Ensure the language selector is visible by default."""
    try:
        api.portal.set_registry_record("plone.disable_language_selector", False)
    except InvalidParameterError:
        pass

    try:
        props = api.portal.get_tool("portal_properties")
    except Exception:
        return

    site_props = getattr(props, "site_properties", None)
    if site_props and site_props.hasProperty("disable_language_selector"):
        if site_props.getProperty("disable_language_selector"):
            site_props._setProperty("disable_language_selector", False)
            print("Enabled language selector in site properties")


def create_demo_survey(
    site,
    survey_id,
    title,
    description,
    form_json,
    intro_html=None,
    actions=None,
    container=None,
    language="en",
):
    container = container or site
    survey = api.content.create(
        type="Survey",
        container=container,
        title=title,
        id=survey_id,
        description=description,
        text=RichTextValue(intro_html, "text/html", "text/html")
        if intro_html
        else None,
        language=language,
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


def set_form_language(form_json, language):
    form_json["language"] = language


def set_form_locale(form_json, locale):
    form_json["locale"] = locale


def remove_navigation_portlets(context):
    """Remove navigation portlets and block them from being re-acquired."""
    for manager_name in ("plone.leftcolumn", "plone.rightcolumn"):
        try:
            manager = getUtility(IPortletManager, name=manager_name, context=context)
            assignments = getMultiAdapter((context, manager), IPortletAssignmentMapping)
            if "navigation" in assignments:
                del assignments["navigation"]

            local_manager = getMultiAdapter(
                (context, manager), ILocalPortletAssignmentManager
            )
            local_manager.setBlacklistStatus(CONTEXT_CATEGORY, True)
        except Exception:
            # Failing quietly keeps the rest of the init script running
            continue


def ensure_folder(container, folder_id, title):
    """Ensure a published folder exists and return it."""
    folder = container.get(folder_id)
    if not folder:
        folder = api.content.create(
            type="Folder",
            container=container,
            id=folder_id,
            title=title,
        )
    try:
        state = api.content.get_state(folder)
    except InvalidParameterError:
        state = None
    if state != "published":
        try:
            api.content.transition(obj=folder, transition="publish")
        except InvalidParameterError:
            pass
    return folder


def ensure_language_tree(site, language, root_title, demos_title):
    """Create a language root and its demos folder."""
    root = ensure_folder(site, language, root_title)
    try:
        root.language = language
        root.reindexObject()
    except Exception:
        pass

    demos = ensure_folder(root, "demos", demos_title)
    try:
        demos.language = language
        demos.reindexObject()
    except Exception:
        pass

    return root, demos


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
api.addon.install("privacyforms.theme")

# Apply privacyforms.theme
print("Enabling privacyforms.theme...")
site.REQUEST.form["form.button.Enable"] = "DONE"
site.REQUEST.form["themeName"] = "privacyforms.theme"
view = MyThemingControlpanel(site, site.REQUEST)
view.update()
configure_ai_model_from_env()
configure_mail_from_env()
configure_site_languages()
enable_language_selector()
remove_navigation_portlets(site)

# Create logo.jpg as Image content object
logo_path = Path(os.getcwd()) / "scripts" / "logo.jpg"
if logo_path.exists():
    logo_image = api.content.create(
        type="Image",
        container=site,
        id="logo",
        title="Privacy Forms Studio Logo",
        image=NamedBlobImage(data=logo_path.read_bytes(), filename="logo.jpg"),
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

language_trees = {
    "en": {"root": "English", "demos": "Demos (EN)"},
    "de": {"root": "Deutsch", "demos": "Demos (DE)"},
    "ar": {"root": "العربية", "demos": "نماذج تجريبية (AR)"},
    "ja": {"root": "日本語", "demos": "デモフォーム (JP)"},
}

language_roots = {}
demos_by_language = {}
for language, titles in language_trees.items():
    root, demos_folder = ensure_language_tree(
        site, language, titles["root"], titles["demos"]
    )
    language_roots[language] = root
    demos_by_language[language] = demos_folder

# Seed event registration survey
event_form = load_form_definition("event_registration")

create_demo_survey(
    site,
    survey_id="event-registration",
    title="Event registration",
    description="Register for the event.",
    form_json=event_form,
    container=demos_by_language["en"],
)

welcome_html = load_intro_text("welcome")

# Add styled links to demo forms
welcome_html += """
<div style="padding:12px 16px;margin:16px 0;border:2px solid #b45309;background:#fff7ed;border-radius:8px;color:#92400e;font-weight:700;">
  Demo system: This site is reset every six hours. Content may be wiped without notice.
</div>
<style>
  .demo-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(260px, 1fr)); gap: 16px; margin: 24px 0; padding: 0; list-style: none; }
  .demo-card { border: 1px solid #e1e4e8; border-radius: 10px; padding: 14px 16px; background: linear-gradient(180deg, #fafbfc 0%, #ffffff 100%); box-shadow: 0 2px 6px rgba(0,0,0,0.04); }
  .demo-card h4 { margin: 0 0 6px 0; font-size: 1.05rem; }
  .demo-card h4 a { color: #0b6fa4; }
  .demo-card h4 a:hover,
  .demo-card h4 a:focus { color: #084f74; text-decoration: underline; }
  .demo-card a { text-decoration: none; font-weight: 600; color: #0b6fa4; }
</style>
<section>
  <h3>Demo Forms (EN)</h3>
  <ul class="demo-grid">
    <li class="demo-card">
      <h4><a href="demo/en/demos/event-registration">Event registration</a></h4>
    </li>
    <li class="demo-card">
      <h4><a href="demo/en/demos/event-rsvp">Event registration / unregistration</a></h4>
    </li>
    <li class="demo-card">
      <h4><a href="demo/en/demos/mental-health-survey">Mental Health Survey</a></h4>
    </li>
    <li class="demo-card">
      <h4><a href="demo/en/demos/full-demo">Social Media Consumption Demo</a></h4>
    </li>
    <li class="demo-card">
      <h4><a href="demo/en/demos/food-feedback-demo">Food Ordering Service Feedback</a></h4>
    </li>
    <li class="demo-card">
      <h4><a href="demo/en/demos/order-form">Order form</a></h4>
    </li>
  </ul>
</section>
<section>
  <h3>Demo Forms (DE)</h3>
  <ul class="demo-grid">
    <li class="demo-card">
      <h4><a href="demo/de/demos/event-registration-de">Veranstaltungsanmeldung</a></h4>
    </li>
    <li class="demo-card">
      <h4><a href="demo/de/demos/event-rsvp-de">Veranstaltung An-/Abmeldung</a></h4>
    </li>
    <li class="demo-card">
      <h4><a href="demo/de/demos/mental-health-survey-de">Umfrage zur psychischen Gesundheit</a></h4>
    </li>
    <li class="demo-card">
      <h4><a href="demo/de/demos/full-demo-de">Nutzung sozialer Medien</a></h4>
    </li>
    <li class="demo-card">
      <h4><a href="demo/de/demos/food-feedback-demo-de">Feedback zum Essens-Bestellservice</a></h4>
    </li>
    <li class="demo-card">
      <h4><a href="demo/de/demos/order-form-de">Bestellformular für Kleidung</a></h4>
    </li>
  </ul>
</section>
<section dir="rtl">
  <h3>نماذج تجريبية (AR)</h3>
  <ul class="demo-grid">
    <li class="demo-card">
      <h4><a href="demo/ar/demos/event-registration-ar">التسجيل للفعالية</a></h4>
    </li>
    <li class="demo-card">
      <h4><a href="demo/ar/demos/event-rsvp-ar">التسجيل / إلغاء التسجيل للفعالية</a></h4>
    </li>
    <li class="demo-card">
      <h4><a href="demo/ar/demos/mental-health-survey-ar">استبيان الصحة النفسية</a></h4>
    </li>
    <li class="demo-card">
      <h4><a href="demo/ar/demos/full-demo-ar">عرض استهلاك وسائل التواصل الاجتماعي</a></h4>
    </li>
    <li class="demo-card">
      <h4><a href="demo/ar/demos/food-feedback-demo-ar">ملاحظات خدمة طلب الطعام</a></h4>
    </li>
    <li class="demo-card">
      <h4><a href="demo/ar/demos/order-form-ar">نموذج الطلب</a></h4>
    </li>
  </ul>
</section>
<section>
  <h3>デモフォーム (JP)</h3>
  <ul class="demo-grid">
    <li class="demo-card">
      <h4><a href="demo/ja/demos/event-registration-ja">イベント登録</a></h4>
    </li>
    <li class="demo-card">
      <h4><a href="demo/ja/demos/event-rsvp-ja">イベント登録 / 取消</a></h4>
    </li>
    <li class="demo-card">
      <h4><a href="demo/ja/demos/mental-health-survey-ja">メンタルヘルス調査</a></h4>
    </li>
    <li class="demo-card">
      <h4><a href="demo/ja/demos/full-demo-ja">ソーシャルメディア利用デモ</a></h4>
    </li>
    <li class="demo-card">
      <h4><a href="demo/ja/demos/food-feedback-demo-ja">フード注文サービスのフィードバック</a></h4>
    </li>
    <li class="demo-card">
      <h4><a href="demo/ja/demos/order-form-ja">衣類注文フォーム</a></h4>
    </li>
  </ul>
</section>
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
    container=demos_by_language["en"],
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
    container=demos_by_language["en"],
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
    container=demos_by_language["en"],
)

event_rsvp_form = load_form_definition("event_rsvp")

create_demo_survey(
    site,
    survey_id="event-rsvp",
    title="Event registration / unregistration",
    description="Register for the event or cancel an existing registration.",
    form_json=event_rsvp_form,
    actions={"store"},
    container=demos_by_language["en"],
)

order_form = load_form_definition("order_form")

create_demo_survey(
    site,
    survey_id="order-form",
    title="Order form",
    description="Collect simple cloth orders with customer info and order lines.",
    form_json=order_form,
    actions={"store"},
    container=demos_by_language["en"],
)

# German demos
event_form_de = load_form_definition("event_registration_de")
set_form_language(event_form_de, "de")

create_demo_survey(
    site,
    survey_id="event-registration-de",
    title="Veranstaltungsanmeldung",
    description="Melden Sie sich zur Veranstaltung an.",
    form_json=event_form_de,
    container=demos_by_language["de"],
    language="de",
)

mental_intro_de = load_intro_text("mental_health_intro_de")
mental_form_de = load_form_definition("mental_health_de")
set_form_language(mental_form_de, "de")
set_form_intro_html(mental_form_de, "introText", mental_intro_de)

create_demo_survey(
    site,
    survey_id="mental-health-survey-de",
    title="Umfrage zur psychischen Gesundheit",
    description="Ein kurzer, vertraulicher Check-in zu Ihrem Wohlbefinden in dieser Woche.",
    form_json=mental_form_de,
    intro_html=mental_intro_de,
    actions={"store"},
    container=demos_by_language["de"],
    language="de",
)

full_demo_intro_de = load_intro_text("full_demo_intro_de")
full_demo_form_de = load_form_definition("full_demo_de")
set_form_language(full_demo_form_de, "de")
set_form_intro_html(full_demo_form_de, "demoIntro", full_demo_intro_de)

create_demo_survey(
    site,
    survey_id="full-demo-de",
    title="Nutzung sozialer Medien",
    description="Demonstration von SurveyJS-Funktionen im Kontext sozialer Medien.",
    form_json=full_demo_form_de,
    intro_html=full_demo_intro_de,
    actions={"store"},
    container=demos_by_language["de"],
    language="de",
)

feedback_form_de = load_form_definition("food_feedback_de")
set_form_language(feedback_form_de, "de")

create_demo_survey(
    site,
    survey_id="food-feedback-demo-de",
    title="Feedback zum Essens-Bestellservice",
    description="Kurze 1-5 Bewertungen zu Ihrer letzten Erfahrung.",
    form_json=feedback_form_de,
    intro_html=load_intro_text("food_feedback_intro_de"),
    actions={"store"},
    container=demos_by_language["de"],
    language="de",
)

event_rsvp_form_de = load_form_definition("event_rsvp_de")
set_form_language(event_rsvp_form_de, "de")

create_demo_survey(
    site,
    survey_id="event-rsvp-de",
    title="Veranstaltung An-/Abmeldung",
    description="Für eine Veranstaltung an- oder abmelden.",
    form_json=event_rsvp_form_de,
    actions={"store"},
    container=demos_by_language["de"],
    language="de",
)

order_form_de = load_form_definition("order_form_de")
set_form_language(order_form_de, "de")

create_demo_survey(
    site,
    survey_id="order-form-de",
    title="Bestellformular für Kleidung",
    description="Kundendaten und Bestellpositionen für Textilien erfassen.",
    form_json=order_form_de,
    actions={"store"},
    container=demos_by_language["de"],
    language="de",
)

# Arabic demos (duplicates of EN forms)
event_form_ar = load_form_definition("event_registration_ar")
set_form_language(event_form_ar, "ar")
set_form_locale(event_form_ar, "ar")

create_demo_survey(
    site,
    survey_id="event-registration-ar",
    title="التسجيل للفعالية",
    description="سجّل في الفعالية.",
    form_json=event_form_ar,
    container=demos_by_language["ar"],
    language="ar",
)

mental_intro_ar = load_intro_text("mental_health_intro_ar")
mental_form_ar = load_form_definition("mental_health_ar")
set_form_language(mental_form_ar, "ar")
set_form_locale(mental_form_ar, "ar")
set_form_intro_html(mental_form_ar, "introText", mental_intro_ar)

create_demo_survey(
    site,
    survey_id="mental-health-survey-ar",
    title="استبيان الصحة النفسية",
    description="تقييم قصير ومراجعة ذاتية للحالة النفسية.",
    form_json=mental_form_ar,
    intro_html=mental_intro_ar,
    actions={"store"},
    container=demos_by_language["ar"],
    language="ar",
)

full_demo_intro_ar = load_intro_text("full_demo_intro_ar")
full_demo_form_ar = load_form_definition("full_demo_ar")
set_form_language(full_demo_form_ar, "ar")
set_form_locale(full_demo_form_ar, "ar")
set_form_intro_html(full_demo_form_ar, "demoIntro", full_demo_intro_ar)

create_demo_survey(
    site,
    survey_id="full-demo-ar",
    title="عرض استهلاك وسائل التواصل الاجتماعي",
    description="عرض شامل لميزات SurveyJS باستخدام سياق وسائل التواصل.",
    form_json=full_demo_form_ar,
    intro_html=full_demo_intro_ar,
    actions={"store"},
    container=demos_by_language["ar"],
    language="ar",
)

feedback_form_ar = load_form_definition("food_feedback_ar")
set_form_language(feedback_form_ar, "ar")
set_form_locale(feedback_form_ar, "ar")

create_demo_survey(
    site,
    survey_id="food-feedback-demo-ar",
    title="ملاحظات خدمة طلب الطعام",
    description="قيّم تجربة الطلب بخمس نقاط سريعة.",
    form_json=feedback_form_ar,
    intro_html=load_intro_text("food_feedback_intro_ar"),
    actions={"store"},
    container=demos_by_language["ar"],
    language="ar",
)

event_rsvp_form_ar = load_form_definition("event_rsvp_ar")
set_form_language(event_rsvp_form_ar, "ar")
set_form_locale(event_rsvp_form_ar, "ar")

create_demo_survey(
    site,
    survey_id="event-rsvp-ar",
    title="التسجيل / إلغاء التسجيل للفعالية",
    description="سجّل أو ألغِ التسجيل في الفعالية.",
    form_json=event_rsvp_form_ar,
    actions={"store"},
    container=demos_by_language["ar"],
    language="ar",
)

order_form_ar = load_form_definition("order_form_ar")
set_form_language(order_form_ar, "ar")
set_form_locale(order_form_ar, "ar")

create_demo_survey(
    site,
    survey_id="order-form-ar",
    title="نموذج الطلب",
    description="جمع بيانات العميل وبنود الطلب.",
    form_json=order_form_ar,
    actions={"store"},
    container=demos_by_language["ar"],
    language="ar",
)

# Japanese demos
event_form_ja = load_form_definition("event_registration_ja")
set_form_language(event_form_ja, "ja")
set_form_locale(event_form_ja, "ja")

create_demo_survey(
    site,
    survey_id="event-registration-ja",
    title="イベント登録",
    description="イベントに登録してください。",
    form_json=event_form_ja,
    container=demos_by_language["ja"],
    language="ja",
)

mental_intro_ja = load_intro_text("mental_health_intro_ja")
mental_form_ja = load_form_definition("mental_health_ja")
set_form_language(mental_form_ja, "ja")
set_form_locale(mental_form_ja, "ja")
set_form_intro_html(mental_form_ja, "introText", mental_intro_ja)

create_demo_survey(
    site,
    survey_id="mental-health-survey-ja",
    title="メンタルヘルス調査",
    description="今週の気分を手短に、かつ匿名で振り返るための調査です。",
    form_json=mental_form_ja,
    intro_html=mental_intro_ja,
    actions={"store"},
    container=demos_by_language["ja"],
    language="ja",
)

full_demo_intro_ja = load_intro_text("full_demo_intro_ja")
full_demo_form_ja = load_form_definition("full_demo_ja")
set_form_language(full_demo_form_ja, "ja")
set_form_locale(full_demo_form_ja, "ja")
set_form_intro_html(full_demo_form_ja, "demoIntro", full_demo_intro_ja)

create_demo_survey(
    site,
    survey_id="full-demo-ja",
    title="ソーシャルメディア利用デモ",
    description="ソーシャルメディアの文脈でSurveyJSの機能を紹介するデモです。",
    form_json=full_demo_form_ja,
    intro_html=full_demo_intro_ja,
    actions={"store"},
    container=demos_by_language["ja"],
    language="ja",
)

feedback_form_ja = load_form_definition("food_feedback_ja")
set_form_language(feedback_form_ja, "ja")
set_form_locale(feedback_form_ja, "ja")

create_demo_survey(
    site,
    survey_id="food-feedback-demo-ja",
    title="フード注文サービスのフィードバック",
    description="最近の体験について1〜5で簡単に評価してください。",
    form_json=feedback_form_ja,
    intro_html=load_intro_text("food_feedback_intro_ja"),
    actions={"store"},
    container=demos_by_language["ja"],
    language="ja",
)

event_rsvp_form_ja = load_form_definition("event_rsvp_ja")
set_form_language(event_rsvp_form_ja, "ja")
set_form_locale(event_rsvp_form_ja, "ja")

create_demo_survey(
    site,
    survey_id="event-rsvp-ja",
    title="イベント登録 / 取消",
    description="イベントに登録するか、参加できない場合は取消をお知らせください。",
    form_json=event_rsvp_form_ja,
    actions={"store"},
    container=demos_by_language["ja"],
    language="ja",
)

order_form_ja = load_form_definition("order_form_ja")
set_form_language(order_form_ja, "ja")
set_form_locale(order_form_ja, "ja")

create_demo_survey(
    site,
    survey_id="order-form-ja",
    title="衣類注文フォーム",
    description="顧客情報と明細行を収集するためのシンプルな衣類注文フォームです。",
    form_json=order_form_ja,
    actions={"store"},
    container=demos_by_language["ja"],
    language="ja",
)

# Create a demo user with Editor role
if not api.user.get(username="forms"):
    api.user.create(
        username="forms", email="forms@example.com", password="formsarecool"
    )
    api.user.grant_roles(username="forms", roles=["Editor"])
    print("Created demo user 'forms' with Editor role")
else:
    print("Demo user 'forms' already exists")

transaction.commit()
