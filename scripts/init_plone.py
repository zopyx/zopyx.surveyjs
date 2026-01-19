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
    """Set site languages to English + German + French + Italian + Spanish + Portuguese + Arabic + Japanese, with English as default."""
    try:
        api.portal.set_registry_record(
            "plone.available_languages",
            ["en", "de", "fr", "it", "es", "pt", "ar", "ja"],
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
        print("Configured site languages: en (default), de, fr, it, es, pt, ar, ja")
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
    print(form_path)
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


def remove_home_tab(context):
    """Hide the default 'Home' tab from the global navigation."""
    try:
        portal_actions = api.portal.get_tool("portal_actions")
        portal_tabs = portal_actions.get("portal_tabs")
        if portal_tabs and "index_html" in portal_tabs.objectIds():
            action = portal_tabs["index_html"]
            action.visible = False
            action._p_changed = True
    except Exception:
        # Failing quietly keeps the rest of the init script running
        pass


def redirect_demo_root_to_en(context):
    """Redirect the site root to the English language root without a default page."""
    try:
        context.setDefaultPage("")
    except Exception:
        try:
            context.setDefaultPage(None)
        except Exception:
            pass
    try:
        context.setLayout("root-redirect")
    except Exception:
        # Failing quietly keeps the rest of the init script running
        pass


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
remove_home_tab(site)

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
    "fr": {"root": "Français", "demos": "Démos (FR)"},
    "it": {"root": "Italiano", "demos": "Demo (IT)"},
    "es": {"root": "Español", "demos": "Demos (ES)"},
    "pt": {"root": "Português", "demos": "Demos (PT)"},
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

WELCOME_STYLE = """
<style>
  .demo-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(260px, 1fr)); gap: 16px; margin: 24px 0; padding: 0; list-style: none; }
  .demo-card { border: 1px solid #e1e4e8; border-radius: 10px; padding: 14px 16px; background: linear-gradient(180deg, #fafbfc 0%, #ffffff 100%); box-shadow: 0 2px 6px rgba(0,0,0,0.04); }
  .demo-card h4 { margin: 0 0 6px 0; font-size: 1.05rem; }
  .demo-card h4 a { color: #0b6fa4; }
  .demo-card h4 a:hover,
  .demo-card h4 a:focus { color: #084f74; text-decoration: underline; }
  .demo-card a { text-decoration: none; font-weight: 600; color: #0b6fa4; }
</style>
"""

WELCOME_BANNERS = {
    "en": "Demo system: This site is reset every six hours. Content may be wiped without notice.",
    "de": "Demonstrationssystem: Diese Seite wird alle sechs Stunden zur\u00fcckgesetzt. Inhalte k\u00f6nnen ohne Vorank\u00fcndigung gel\u00f6scht werden.",
    "fr": "Syst\u00e8me de d\u00e9monstration : ce site est r\u00e9initialis\u00e9 toutes les six heures. Le contenu peut \u00eatre supprim\u00e9 sans pr\u00e9avis.",
    "it": "Sistema dimostrativo: questo sito viene ripristinato ogni sei ore. I contenuti possono essere cancellati senza preavviso.",
    "es": "Sistema de demostraci\u00f3n: este sitio se restablece cada seis horas. El contenido puede borrarse sin previo aviso.",
    "pt": "Sistema de demonstra\u00e7\u00e3o: este site \u00e9 reiniciado a cada seis horas. O conte\u00fado pode ser apagado sem aviso pr\u00e9vio.",
    "ar": "\u0646\u0638\u0627\u0645 \u062a\u062c\u0631\u064a\u0628\u064a: \u062a\u062a\u0645 \u0625\u0639\u0627\u062f\u0629 \u0636\u0628\u0637 \u0647\u0630\u0627 \u0627\u0644\u0645\u0648\u0642\u0639 \u0643\u0644 \u0633\u062a \u0633\u0627\u0639\u0627\u062a. \u0642\u062f \u062a\u064f\u062d\u0630\u0641 \u0627\u0644\u0645\u062d\u062a\u0648\u064a\u0627\u062a \u062f\u0648\u0646 \u0625\u0634\u0639\u0627\u0631.",
    "ja": "\u30c7\u30e2\u74b0\u5883: \u3053\u306e\u30b5\u30a4\u30c8\u306f6\u6642\u9593\u3054\u3068\u306b\u30ea\u30bb\u30c3\u30c8\u3055\u308c\u307e\u3059\u3002\u5185\u5bb9\u306f\u4e88\u544a\u306a\u304f\u524a\u9664\u3055\u308c\u308b\u5834\u5408\u304c\u3042\u308a\u307e\u3059\u3002",
}

WELCOME_HEADINGS = {
    "en": "Demo Forms",
    "de": "Demo-Formulare",
    "fr": "Formulaires de d\u00e9monstration",
    "it": "Moduli demo",
    "es": "Formularios de demostraci\u00f3n",
    "pt": "Formul\u00e1rios de demonstra\u00e7\u00e3o",
    "ar": "\u0646\u0645\u0627\u0630\u062c \u062a\u062c\u0631\u064a\u0628\u064a\u0629",
    "ja": "\u30c7\u30e2\u30d5\u30a9\u30fc\u30e0",
}

WELCOME_DEMOS = {
    "en": [
        ("Event registration", "en/demos/event-registration"),
        ("Event registration / unregistration", "en/demos/event-rsvp"),
        ("Mental Health Survey", "en/demos/mental-health-survey"),
        ("Social Media Consumption Demo", "en/demos/full-demo"),
        ("Food Ordering Service Feedback", "en/demos/food-feedback-demo"),
        ("Order form", "en/demos/order-form"),
    ],
    "de": [
        ("Veranstaltungsanmeldung", "de/demos/event-registration-de"),
        ("Veranstaltung An-/Abmeldung", "de/demos/event-rsvp-de"),
        ("Umfrage zur psychischen Gesundheit", "de/demos/mental-health-survey-de"),
        ("Nutzung sozialer Medien", "de/demos/full-demo-de"),
        ("Feedback zum Essens-Bestellservice", "de/demos/food-feedback-demo-de"),
        ("Bestellformular f\u00fcr Kleidung", "de/demos/order-form-de"),
    ],
    "fr": [
        (
            "Inscription \u00e0 l\u2019\u00e9v\u00e9nement",
            "fr/demos/event-registration-fr",
        ),
        (
            "Inscription / d\u00e9sinscription \u00e0 l\u2019\u00e9v\u00e9nement",
            "fr/demos/event-rsvp-fr",
        ),
        ("Enqu\u00eate sur la sant\u00e9 mentale", "fr/demos/mental-health-survey-fr"),
        (
            "D\u00e9mo sur l\u2019usage des r\u00e9seaux sociaux",
            "fr/demos/full-demo-fr",
        ),
        ("Avis sur le service de commande de repas", "fr/demos/food-feedback-demo-fr"),
        ("Formulaire de commande", "fr/demos/order-form-fr"),
    ],
    "it": [
        ("Iscrizione all\u2019evento", "it/demos/event-registration-it"),
        ("Iscrizione / annullamento evento", "it/demos/event-rsvp-it"),
        ("Sondaggio sulla salute mentale", "it/demos/mental-health-survey-it"),
        ("Demo sull\u2019uso dei social media", "it/demos/full-demo-it"),
        ("Feedback sul servizio di ordinazione cibo", "it/demos/food-feedback-demo-it"),
        ("Modulo d\u2019ordine", "it/demos/order-form-it"),
    ],
    "es": [
        ("Registro del evento", "es/demos/event-registration-es"),
        ("Registro / cancelaci\u00f3n del evento", "es/demos/event-rsvp-es"),
        ("Encuesta de salud mental", "es/demos/mental-health-survey-es"),
        ("Demo de consumo de redes sociales", "es/demos/full-demo-es"),
        (
            "Comentarios sobre el servicio de pedido de comida",
            "es/demos/food-feedback-demo-es",
        ),
        ("Formulario de pedido", "es/demos/order-form-es"),
    ],
    "pt": [
        ("Inscri\u00e7\u00e3o no evento", "pt/demos/event-registration-pt"),
        ("Inscri\u00e7\u00e3o / cancelamento do evento", "pt/demos/event-rsvp-pt"),
        ("Pesquisa de sa\u00fade mental", "pt/demos/mental-health-survey-pt"),
        ("Demonstra\u00e7\u00e3o de uso de redes sociais", "pt/demos/full-demo-pt"),
        (
            "Feedback do servi\u00e7o de pedidos de comida",
            "pt/demos/food-feedback-demo-pt",
        ),
        ("Formul\u00e1rio de pedido", "pt/demos/order-form-pt"),
    ],
    "ar": [
        (
            "\u0627\u0644\u062a\u0633\u062c\u064a\u0644 \u0644\u0644\u0641\u0639\u0627\u0644\u064a\u0629",
            "ar/demos/event-registration-ar",
        ),
        (
            "\u0627\u0644\u062a\u0633\u062c\u064a\u0644 / \u0625\u0644\u063a\u0627\u0621 \u0627\u0644\u062a\u0633\u062c\u064a\u0644 \u0644\u0644\u0641\u0639\u0627\u0644\u064a\u0629",
            "ar/demos/event-rsvp-ar",
        ),
        (
            "\u0627\u0633\u062a\u0628\u064a\u0627\u0646 \u0627\u0644\u0635\u062d\u0629 \u0627\u0644\u0646\u0641\u0633\u064a\u0629",
            "ar/demos/mental-health-survey-ar",
        ),
        (
            "\u0639\u0631\u0636 \u0627\u0633\u062a\u0647\u0644\u0627\u0643 \u0648\u0633\u0627\u0626\u0644 \u0627\u0644\u062a\u0648\u0627\u0635\u0644 \u0627\u0644\u0627\u062c\u062a\u0645\u0627\u0639\u064a",
            "ar/demos/full-demo-ar",
        ),
        (
            "\u0645\u0644\u0627\u062d\u0638\u0627\u062a \u062e\u062f\u0645\u0629 \u0637\u0644\u0628 \u0627\u0644\u0637\u0639\u0627\u0645",
            "ar/demos/food-feedback-demo-ar",
        ),
        (
            "\u0646\u0645\u0648\u0630\u062c \u0627\u0644\u0637\u0644\u0628",
            "ar/demos/order-form-ar",
        ),
    ],
    "ja": [
        ("\u30a4\u30d9\u30f3\u30c8\u767b\u9332", "ja/demos/event-registration-ja"),
        (
            "\u30a4\u30d9\u30f3\u30c8\u767b\u9332 / \u53d6\u6d88",
            "ja/demos/event-rsvp-ja",
        ),
        (
            "\u30e1\u30f3\u30bf\u30eb\u30d8\u30eb\u30b9\u8abf\u67fb",
            "ja/demos/mental-health-survey-ja",
        ),
        (
            "\u30bd\u30fc\u30b7\u30e3\u30eb\u30e1\u30c7\u30a3\u30a2\u5229\u7528\u30c7\u30e2",
            "ja/demos/full-demo-ja",
        ),
        (
            "\u30d5\u30fc\u30c9\u6ce8\u6587\u30b5\u30fc\u30d3\u30b9\u306e\u30d5\u30a3\u30fc\u30c9\u30d0\u30c3\u30af",
            "ja/demos/food-feedback-demo-ja",
        ),
        ("\u8863\u985e\u6ce8\u6587\u30d5\u30a9\u30fc\u30e0", "ja/demos/order-form-ja"),
    ],
}

WELCOME_TITLES = {
    "en": "Privacy Forms Studio",
    "de": "Privacy Forms Studio",
    "fr": "Privacy Forms Studio",
    "it": "Privacy Forms Studio",
    "es": "Privacy Forms Studio",
    "pt": "Privacy Forms Studio",
    "ar": "\u0628\u0631\u0627\u064a\u0641\u0633\u064a \u0641\u0648\u0631\u0645\u0632 \u0633\u062a\u0648\u062f\u064a\u0648",
    "ja": "\u30d7\u30e9\u30a4\u30d0\u30b7\u30fc \u30d5\u30a9\u30fc\u30e0\u30ba \u30b9\u30bf\u30b8\u30aa",
}


def load_welcome_intro(language):
    suffix = "" if language == "en" else f"_{language}"
    return load_intro_text(f"welcome{suffix}")


def build_demo_section(language):
    items = WELCOME_DEMOS[language]
    heading = WELCOME_HEADINGS[language]
    dir_attr = ' dir="rtl"' if language == "ar" else ""

    # Ensure demo links resolve regardless of default-page vs direct URL.
    def _absolute_demo_href(href):
        if href.startswith(f"{language}/"):
            return href
        if href.startswith("/"):
            return href.lstrip("/")
        return f"{language}/" + href.lstrip("/")

    cards = "\n".join(
        f'    <li class="demo-card"><h4><a href="{_absolute_demo_href(href)}">{title}</a></h4></li>'
        for title, href in items
    )
    return f"""
<section{dir_attr}>
  <h3>{heading}</h3>
  <ul class="demo-grid">
{cards}
  </ul>
</section>
"""


def build_welcome_html(language):
    banner = WELCOME_BANNERS[language]
    intro = load_welcome_intro(language)
    demo_section = build_demo_section(language)
    return f"""{intro}
<div style="padding:12px 16px;margin:16px 0;border:2px solid #b45309;background:#fff7ed;border-radius:8px;color:#92400e;font-weight:700;">
  {banner}
</div>
{WELCOME_STYLE}
{demo_section}
"""


for language, root in language_roots.items():
    welcome_html = build_welcome_html(language)
    welcome = api.content.create(
        type="Document",
        container=root,
        title=WELCOME_TITLES[language],
        id="welcome",
        text=RichTextValue(
            welcome_html,
            "text/html",
            "text/html",
        ),
        language=language,
    )
    api.content.transition(obj=welcome, transition="publish")
    welcome.reindexObject()
    root.setDefaultPage("welcome")

redirect_demo_root_to_en(site)

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

# French demos
event_form_fr = load_form_definition("event_registration_fr")
set_form_language(event_form_fr, "fr")
set_form_locale(event_form_fr, "fr")

create_demo_survey(
    site,
    survey_id="event-registration-fr",
    title="Inscription à l’événement",
    description="Inscrivez-vous à l’événement.",
    form_json=event_form_fr,
    container=demos_by_language["fr"],
    language="fr",
)

mental_intro_fr = load_intro_text("mental_health_intro_fr")
mental_form_fr = load_form_definition("mental_health_fr")
set_form_language(mental_form_fr, "fr")
set_form_locale(mental_form_fr, "fr")
set_form_intro_html(mental_form_fr, "introText", mental_intro_fr)

create_demo_survey(
    site,
    survey_id="mental-health-survey-fr",
    title="Enquête sur la santé mentale",
    description="Un bref bilan anonyme de votre bien-être.",
    form_json=mental_form_fr,
    intro_html=mental_intro_fr,
    actions={"store"},
    container=demos_by_language["fr"],
    language="fr",
)

full_demo_intro_fr = load_intro_text("full_demo_intro_fr")
full_demo_form_fr = load_form_definition("full_demo_fr")
set_form_language(full_demo_form_fr, "fr")
set_form_locale(full_demo_form_fr, "fr")
set_form_intro_html(full_demo_form_fr, "demoIntro", full_demo_intro_fr)

create_demo_survey(
    site,
    survey_id="full-demo-fr",
    title="Démo sur l’usage des réseaux sociaux",
    description="Démonstration des fonctionnalités SurveyJS dans le contexte des réseaux sociaux.",
    form_json=full_demo_form_fr,
    intro_html=full_demo_intro_fr,
    actions={"store"},
    container=demos_by_language["fr"],
    language="fr",
)

feedback_form_fr = load_form_definition("food_feedback_fr")
set_form_language(feedback_form_fr, "fr")
set_form_locale(feedback_form_fr, "fr")

create_demo_survey(
    site,
    survey_id="food-feedback-demo-fr",
    title="Avis sur le service de commande de repas",
    description="Évaluez votre expérience récente de 1 à 5.",
    form_json=feedback_form_fr,
    intro_html=load_intro_text("food_feedback_intro_fr"),
    actions={"store"},
    container=demos_by_language["fr"],
    language="fr",
)

event_rsvp_form_fr = load_form_definition("event_rsvp_fr")
set_form_language(event_rsvp_form_fr, "fr")
set_form_locale(event_rsvp_form_fr, "fr")

create_demo_survey(
    site,
    survey_id="event-rsvp-fr",
    title="Inscription / désinscription à l’événement",
    description="Inscrivez-vous ou annulez une inscription existante.",
    form_json=event_rsvp_form_fr,
    actions={"store"},
    container=demos_by_language["fr"],
    language="fr",
)

order_form_fr = load_form_definition("order_form_fr")
set_form_language(order_form_fr, "fr")
set_form_locale(order_form_fr, "fr")

create_demo_survey(
    site,
    survey_id="order-form-fr",
    title="Formulaire de commande",
    description="Collecter les informations client et les lignes de commande.",
    form_json=order_form_fr,
    actions={"store"},
    container=demos_by_language["fr"],
    language="fr",
)

# Italian demos
event_form_it = load_form_definition("event_registration_it")
set_form_language(event_form_it, "it")
set_form_locale(event_form_it, "it")

create_demo_survey(
    site,
    survey_id="event-registration-it",
    title="Iscrizione all’evento",
    description="Iscriviti all’evento.",
    form_json=event_form_it,
    container=demos_by_language["it"],
    language="it",
)

mental_intro_it = load_intro_text("mental_health_intro_it")
mental_form_it = load_form_definition("mental_health_it")
set_form_language(mental_form_it, "it")
set_form_locale(mental_form_it, "it")
set_form_intro_html(mental_form_it, "introText", mental_intro_it)

create_demo_survey(
    site,
    survey_id="mental-health-survey-it",
    title="Sondaggio sulla salute mentale",
    description="Un breve check-in anonimo sul tuo benessere.",
    form_json=mental_form_it,
    intro_html=mental_intro_it,
    actions={"store"},
    container=demos_by_language["it"],
    language="it",
)

full_demo_intro_it = load_intro_text("full_demo_intro_it")
full_demo_form_it = load_form_definition("full_demo_it")
set_form_language(full_demo_form_it, "it")
set_form_locale(full_demo_form_it, "it")
set_form_intro_html(full_demo_form_it, "demoIntro", full_demo_intro_it)

create_demo_survey(
    site,
    survey_id="full-demo-it",
    title="Demo sull’uso dei social media",
    description="Dimostrazione delle funzionalità SurveyJS nel contesto dei social media.",
    form_json=full_demo_form_it,
    intro_html=full_demo_intro_it,
    actions={"store"},
    container=demos_by_language["it"],
    language="it",
)

feedback_form_it = load_form_definition("food_feedback_it")
set_form_language(feedback_form_it, "it")
set_form_locale(feedback_form_it, "it")

create_demo_survey(
    site,
    survey_id="food-feedback-demo-it",
    title="Feedback sul servizio di ordinazione cibo",
    description="Valuta la tua esperienza recente da 1 a 5.",
    form_json=feedback_form_it,
    intro_html=load_intro_text("food_feedback_intro_it"),
    actions={"store"},
    container=demos_by_language["it"],
    language="it",
)

event_rsvp_form_it = load_form_definition("event_rsvp_it")
set_form_language(event_rsvp_form_it, "it")
set_form_locale(event_rsvp_form_it, "it")

create_demo_survey(
    site,
    survey_id="event-rsvp-it",
    title="Iscrizione / annullamento evento",
    description="Iscriviti o annulla un’iscrizione esistente.",
    form_json=event_rsvp_form_it,
    actions={"store"},
    container=demos_by_language["it"],
    language="it",
)

order_form_it = load_form_definition("order_form_it")
set_form_language(order_form_it, "it")
set_form_locale(order_form_it, "it")

create_demo_survey(
    site,
    survey_id="order-form-it",
    title="Modulo d’ordine",
    description="Raccogli i dati del cliente e le righe d’ordine.",
    form_json=order_form_it,
    actions={"store"},
    container=demos_by_language["it"],
    language="it",
)

# Spanish demos
event_form_es = load_form_definition("event_registration_es")
set_form_language(event_form_es, "es")
set_form_locale(event_form_es, "es")

create_demo_survey(
    site,
    survey_id="event-registration-es",
    title="Registro del evento",
    description="Regístrate en el evento.",
    form_json=event_form_es,
    container=demos_by_language["es"],
    language="es",
)

mental_intro_es = load_intro_text("mental_health_intro_es")
mental_form_es = load_form_definition("mental_health_es")
set_form_language(mental_form_es, "es")
set_form_locale(mental_form_es, "es")
set_form_intro_html(mental_form_es, "introText", mental_intro_es)

create_demo_survey(
    site,
    survey_id="mental-health-survey-es",
    title="Encuesta de salud mental",
    description="Un breve chequeo anónimo de tu bienestar.",
    form_json=mental_form_es,
    intro_html=mental_intro_es,
    actions={"store"},
    container=demos_by_language["es"],
    language="es",
)

full_demo_intro_es = load_intro_text("full_demo_intro_es")
full_demo_form_es = load_form_definition("full_demo_es")
set_form_language(full_demo_form_es, "es")
set_form_locale(full_demo_form_es, "es")
set_form_intro_html(full_demo_form_es, "demoIntro", full_demo_intro_es)

create_demo_survey(
    site,
    survey_id="full-demo-es",
    title="Demo de consumo de redes sociales",
    description="Demostración de funciones de SurveyJS en el contexto de redes sociales.",
    form_json=full_demo_form_es,
    intro_html=full_demo_intro_es,
    actions={"store"},
    container=demos_by_language["es"],
    language="es",
)

feedback_form_es = load_form_definition("food_feedback_es")
set_form_language(feedback_form_es, "es")
set_form_locale(feedback_form_es, "es")

create_demo_survey(
    site,
    survey_id="food-feedback-demo-es",
    title="Comentarios sobre el servicio de pedido de comida",
    description="Valora tu experiencia reciente de 1 a 5.",
    form_json=feedback_form_es,
    intro_html=load_intro_text("food_feedback_intro_es"),
    actions={"store"},
    container=demos_by_language["es"],
    language="es",
)

event_rsvp_form_es = load_form_definition("event_rsvp_es")
set_form_language(event_rsvp_form_es, "es")
set_form_locale(event_rsvp_form_es, "es")

create_demo_survey(
    site,
    survey_id="event-rsvp-es",
    title="Registro / cancelación del evento",
    description="Regístrate o cancela una inscripción existente.",
    form_json=event_rsvp_form_es,
    actions={"store"},
    container=demos_by_language["es"],
    language="es",
)

order_form_es = load_form_definition("order_form_es")
set_form_language(order_form_es, "es")
set_form_locale(order_form_es, "es")

create_demo_survey(
    site,
    survey_id="order-form-es",
    title="Formulario de pedido",
    description="Recoge datos del cliente y líneas de pedido.",
    form_json=order_form_es,
    actions={"store"},
    container=demos_by_language["es"],
    language="es",
)

# Portuguese demos
event_form_pt = load_form_definition("event_registration_pt")
set_form_language(event_form_pt, "pt")
set_form_locale(event_form_pt, "pt")

create_demo_survey(
    site,
    survey_id="event-registration-pt",
    title="Inscrição no evento",
    description="Inscreva-se no evento.",
    form_json=event_form_pt,
    container=demos_by_language["pt"],
    language="pt",
)

mental_intro_pt = load_intro_text("mental_health_intro_pt")
mental_form_pt = load_form_definition("mental_health_pt")
set_form_language(mental_form_pt, "pt")
set_form_locale(mental_form_pt, "pt")
set_form_intro_html(mental_form_pt, "introText", mental_intro_pt)

create_demo_survey(
    site,
    survey_id="mental-health-survey-pt",
    title="Pesquisa de saúde mental",
    description="Um breve check-in anônimo sobre seu bem-estar.",
    form_json=mental_form_pt,
    intro_html=mental_intro_pt,
    actions={"store"},
    container=demos_by_language["pt"],
    language="pt",
)

full_demo_intro_pt = load_intro_text("full_demo_intro_pt")
full_demo_form_pt = load_form_definition("full_demo_pt")
set_form_language(full_demo_form_pt, "pt")
set_form_locale(full_demo_form_pt, "pt")
set_form_intro_html(full_demo_form_pt, "demoIntro", full_demo_intro_pt)

create_demo_survey(
    site,
    survey_id="full-demo-pt",
    title="Demonstração de uso de redes sociais",
    description="Demonstração das funcionalidades do SurveyJS no contexto de redes sociais.",
    form_json=full_demo_form_pt,
    intro_html=full_demo_intro_pt,
    actions={"store"},
    container=demos_by_language["pt"],
    language="pt",
)

feedback_form_pt = load_form_definition("food_feedback_pt")
set_form_language(feedback_form_pt, "pt")
set_form_locale(feedback_form_pt, "pt")

create_demo_survey(
    site,
    survey_id="food-feedback-demo-pt",
    title="Feedback do serviço de pedidos de comida",
    description="Avalie sua experiência recente de 1 a 5.",
    form_json=feedback_form_pt,
    intro_html=load_intro_text("food_feedback_intro_pt"),
    actions={"store"},
    container=demos_by_language["pt"],
    language="pt",
)

event_rsvp_form_pt = load_form_definition("event_rsvp_pt")
set_form_language(event_rsvp_form_pt, "pt")
set_form_locale(event_rsvp_form_pt, "pt")

create_demo_survey(
    site,
    survey_id="event-rsvp-pt",
    title="Inscrição / cancelamento do evento",
    description="Inscreva-se ou cancele uma inscrição existente.",
    form_json=event_rsvp_form_pt,
    actions={"store"},
    container=demos_by_language["pt"],
    language="pt",
)

order_form_pt = load_form_definition("order_form_pt")
set_form_language(order_form_pt, "pt")
set_form_locale(order_form_pt, "pt")

create_demo_survey(
    site,
    survey_id="order-form-pt",
    title="Formulário de pedido",
    description="Colete dados do cliente e itens do pedido.",
    form_json=order_form_pt,
    actions={"store"},
    container=demos_by_language["pt"],
    language="pt",
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
