import orjson
import plone.api
from Products.Five import BrowserView
from Products.Five.browser.pagetemplatefile import ViewPageTemplateFile
from zope.annotation.interfaces import IAnnotations
from zope.schema import getFieldsInOrder

from .. import _
from ..content.survey import ISurvey
from .services import forms as forms_service


class PFSView(BrowserView):
    """Permission-aware landing page with prominent call-to-action cards."""

    index = ViewPageTemplateFile("pfs.pt")

    def __call__(self):
        if self.request.get("REQUEST_METHOD", "GET").upper() == "POST":
            if (
                self.request.form.get("pfs_action") or ""
            ).strip() == "create_from_template":
                return self._handle_create_from_template()
        return self.index()

    @property
    def is_anonymous(self) -> bool:
        return plone.api.user.is_anonymous()

    @property
    def can_add_survey(self) -> bool:
        if self.is_anonymous:
            return False
        return plone.api.user.has_permission(
            "zopyx.surveyjs.AddSurvey", obj=self.context
        )

    @property
    def can_view_forms_overview(self) -> bool:
        if self.is_anonymous:
            return False
        return plone.api.user.has_permission("cmf.ManagePortal", obj=self.context)

    @property
    def can_create_from_template(self) -> bool:
        return self.can_add_survey and bool(self.template_options)

    @property
    def add_survey_url(self) -> str:
        return f"{self.context.absolute_url()}/@@survey-add"

    @property
    def forms_overview_url(self) -> str:
        return f"{self.context.absolute_url()}/@@survey-overview"

    @property
    def templates_overview_url(self) -> str:
        return f"{self.context.absolute_url()}/@@survey-templates-overview"

    @property
    def administration_url(self) -> str:
        portal = plone.api.portal.get()
        return f"{portal.absolute_url()}/@@form-settings"

    @property
    def cards(self) -> list[dict]:
        cards: list[dict] = []
        if self.can_add_survey:
            cards.append(
                {
                    "title": _("New form/survey"),
                    "description": _(
                        "Launch a brand-new form or survey and start collecting answers."
                    ),
                    "action_label": _("Create form"),
                    "url": self.add_survey_url,
                    "accent": "primary",
                    "icon": "add",
                }
            )
        if self.can_view_forms_overview:
            cards.append(
                {
                    "title": _("Forms overview"),
                    "description": _(
                        "See every form or survey at a glance, surface trends, and jump right in."
                    ),
                    "action_label": _("Open overview"),
                    "url": self.forms_overview_url,
                    "accent": "secondary",
                    "icon": "overview",
                }
            )
            if self.has_templates:
                cards.append(
                    {
                        "title": _("Templates overview"),
                        "description": _(
                            "Browse saved templates and reuse them for new forms or surveys."
                        ),
                        "action_label": _("Open templates"),
                        "url": self.templates_overview_url,
                        "accent": "secondary",
                        "icon": "template",
                    }
                )
            cards.append(
                {
                    "title": _("Administration"),
                    "description": _(
                        "Visit the control panel to adjust site-wide settings and integrations."
                    ),
                    "action_label": _("Open control panel"),
                    "url": self.administration_url,
                    "accent": "manager",
                    "icon": "admin",
                }
            )
        return cards

    @property
    def template_options(self) -> list[dict]:
        if self.is_anonymous:
            return []
        catalog = plone.api.portal.get_tool("portal_catalog")
        brains = catalog.searchResults(
            portal_type="SurveyTemplate",
            sort_on="sortable_title",
        )
        options: list[dict] = []
        for brain in brains:
            options.append(
                {
                    "uid": brain.UID,
                    "title": brain.Title or "",
                    "description": brain.Description or "",
                    "url": brain.getURL(),
                }
            )
        return options

    @property
    def has_templates(self) -> bool:
        if self.is_anonymous:
            return False
        catalog = plone.api.portal.get_tool("portal_catalog")
        context_path = "/".join(self.context.getPhysicalPath())
        brains = catalog.searchResults(
            portal_type="SurveyTemplate",
            path={"query": context_path, "depth": -1},
            sort_limit=1,
        )
        return bool(brains)

    def _handle_create_from_template(self):
        if not self.can_add_survey:
            self.request.response.setStatus(403)
            return _("You are not allowed to add surveys here.")

        template_uid = (self.request.form.get("template_uid") or "").strip()
        if not template_uid:
            plone.api.portal.show_message(_("Please select a template."), type="error")
            return self.request.response.redirect(
                self.context.absolute_url() + "/@@pfs"
            )

        template = plone.api.content.get(UID=template_uid)
        if template is None:
            plone.api.portal.show_message(_("Template not found."), type="error")
            return self.request.response.redirect(
                self.context.absolute_url() + "/@@pfs"
            )

        raw_json = getattr(template, "template_json", "") or ""
        if not raw_json:
            plone.api.portal.show_message(_("Template JSON is missing."), type="error")
            return self.request.response.redirect(
                self.context.absolute_url() + "/@@pfs"
            )

        try:
            form_json = orjson.loads(raw_json)
        except Exception as exc:
            plone.api.portal.show_message(
                _("Template JSON is invalid: ${error}", mapping={"error": str(exc)}),
                type="error",
            )
            return self.request.response.redirect(
                self.context.absolute_url() + "/@@pfs"
            )

        title = (
            (self.request.form.get("survey_title") or "").strip()
            or getattr(template, "Title", lambda: "")()
            or _("New Survey")
        )

        try:
            description = ""
            template_description = getattr(template, "Description", None)
            if callable(template_description):
                description = template_description() or ""
            else:
                description = getattr(template, "description", "") or ""

            survey = plone.api.content.create(
                container=self.context,
                type="Survey",
                title=title,
                description=description,
            )
            for name, field in getFieldsInOrder(ISurvey):
                if not hasattr(template, name):
                    continue
                try:
                    setattr(survey, name, getattr(template, name))
                except Exception:
                    continue
            annos = IAnnotations(survey)
            forms_service.save_form_version(
                annos,
                form_json,
                plone.api.user.get_current().getId(),
                locked=False,
            )
        except Exception as exc:
            plone.api.portal.show_message(
                _("Failed to create survey: ${error}", mapping={"error": str(exc)}),
                type="error",
            )
            return self.request.response.redirect(
                self.context.absolute_url() + "/@@pfs"
            )

        plone.api.portal.show_message(_("Survey created from template."), type="info")
        return self.request.response.redirect(survey.absolute_url())

    @property
    def login_url(self) -> str:
        portal = plone.api.portal.get()
        return f"{portal.absolute_url()}/login"
