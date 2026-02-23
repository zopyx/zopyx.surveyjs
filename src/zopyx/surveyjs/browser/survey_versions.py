import orjson
import plone.api
from plone.dexterity.utils import iterSchemata
from zope.annotation.interfaces import IAnnotations
from zope.schema import getFieldsInOrder

from .. import _
from ..constants import FORM_VERSIONS_KEY
from .services import forms as forms_service
from .services.http import json_response
from .views import Views


class SurveyVersions(Views):
    @property
    def versions(self):
        """Get all form versions sorted by date (newest first)."""
        annos = IAnnotations(self.context)
        forms_service.ensure_form_versions(annos)
        return forms_service.sorted_form_versions(annos, reverse=True)

    @property
    def has_versions(self):
        """Check if any versions exist."""
        return len(self.versions) > 0

    def download_version(self):
        """Download a specific version as JSON file."""
        version_id = self.request.form.get("version_id")

        if not version_id:
            plone.api.portal.show_message(_("No version ID provided"), type="error")
            return self.request.response.redirect(
                self.context.absolute_url() + "/@@form-versions"
            )

        annos = IAnnotations(self.context)
        form_versions = annos.get(FORM_VERSIONS_KEY, {})

        version_data = form_versions.get(version_id)
        if not version_data:
            plone.api.portal.show_message(_("Version not found"), type="error")
            return self.request.response.redirect(
                self.context.absolute_url() + "/@@form-versions"
            )

        filename = f"survey-form-{version_id[:8]}.json"
        json_content = orjson.dumps(
            version_data["form_json"], option=orjson.OPT_INDENT_2
        )

        self.request.response.setHeader("Content-Type", "application/json")
        self.request.response.setHeader(
            "Content-Disposition", f'attachment; filename="{filename}"'
        )
        self.request.response.write(json_content)

    def restore_version(self):
        """Restore an old version by creating a new version with old content."""
        version_id = self.request.form.get("version_id")

        if not version_id:
            plone.api.portal.show_message(_("No version ID provided"), type="error")
            return self.request.response.redirect(
                self.context.absolute_url() + "/@@form-versions"
            )

        annos = IAnnotations(self.context)
        form_versions = annos.get(FORM_VERSIONS_KEY, {})

        old_version = form_versions.get(version_id)
        if not old_version:
            plone.api.portal.show_message(_("Version not found"), type="error")
            return self.request.response.redirect(
                self.context.absolute_url() + "/@@form-versions"
            )

        forms_service.save_form_version(
            annos,
            old_version["form_json"],
            plone.api.user.get_current().getId(),
            locked=False,
        )

        plone.api.portal.show_message(
            _("Version restored successfully. A new version has been created."),
            type="info",
        )
        return self.request.response.redirect(
            self.context.absolute_url() + "/@@form-versions"
        )

    def toggle_version_lock(self):
        """Toggle lock state for a form version."""
        version_id = self.request.form.get("version_id")
        if not version_id:
            plone.api.portal.show_message(_("No version ID provided"), type="error")
            return self.request.response.redirect(
                self.context.absolute_url() + "/@@form-versions"
            )

        annos = IAnnotations(self.context)
        form_versions = annos.get(FORM_VERSIONS_KEY, {})
        version_data = form_versions.get(version_id)
        if not version_data:
            plone.api.portal.show_message(_("Version not found"), type="error")
            return self.request.response.redirect(
                self.context.absolute_url() + "/@@form-versions"
            )

        locked = bool(version_data.get("locked"))
        version_data["locked"] = not locked
        form_versions[version_id] = version_data

        message = (
            _("Version locked") if version_data["locked"] else _("Version unlocked")
        )
        plone.api.portal.show_message(message, type="info")
        return self.request.response.redirect(
            self.context.absolute_url() + "/@@form-versions"
        )

    def delete_version(self):
        """Delete a form version unless locked."""
        version_id = self.request.form.get("version_id")
        if not version_id:
            plone.api.portal.show_message(_("No version ID provided"), type="error")
            return self.request.response.redirect(
                self.context.absolute_url() + "/@@form-versions"
            )

        annos = IAnnotations(self.context)
        form_versions = annos.get(FORM_VERSIONS_KEY, {})
        version_data = form_versions.get(version_id)
        if not version_data:
            plone.api.portal.show_message(_("Version not found"), type="error")
            return self.request.response.redirect(
                self.context.absolute_url() + "/@@form-versions"
            )

        if version_data.get("locked"):
            plone.api.portal.show_message(
                _("Version is locked and cannot be deleted"), type="error"
            )
            return self.request.response.redirect(
                self.context.absolute_url() + "/@@form-versions"
            )

        del form_versions[version_id]
        plone.api.portal.show_message(_("Version deleted"), type="info")
        return self.request.response.redirect(
            self.context.absolute_url() + "/@@form-versions"
        )

    def upload_version(self):
        """Upload a JSON file and save as new version."""
        uploaded_file = self.request.form.get("json_file")

        if not uploaded_file:
            plone.api.portal.show_message(_("No file uploaded"), type="error")
            return self.request.response.redirect(
                self.context.absolute_url() + "/@@form-versions"
            )

        try:
            file_content = uploaded_file.read()
            if isinstance(file_content, bytes):
                file_content = file_content.decode("utf-8")

            json_data = orjson.loads(file_content)
            if not isinstance(json_data, dict):
                raise ValueError("JSON must be an object")

        except (orjson.JSONDecodeError, ValueError) as e:
            plone.api.portal.show_message(
                _("Invalid JSON file: ${error}", mapping={"error": str(e)}),
                type="error",
            )
            return self.request.response.redirect(
                self.context.absolute_url() + "/@@form-versions"
            )

        annos = IAnnotations(self.context)
        forms_service.save_form_version(
            annos,
            json_data,
            plone.api.user.get_current().getId(),
            locked=False,
        )

        plone.api.portal.show_message(
            _("JSON uploaded successfully as new version"), type="info"
        )
        return self.request.response.redirect(
            self.context.absolute_url() + "/@@form-versions"
        )

    def view_version_json(self):
        """Return JSON for a specific version for viewing."""
        version_id = self.request.form.get("version_id")

        annos = IAnnotations(self.context)
        form_versions = annos.get(FORM_VERSIONS_KEY, {})

        version_data = form_versions.get(version_id)
        if not version_data:
            result = {"error": "Version not found"}
        else:
            result = version_data["form_json"]

        json_response(
            self.request.response,
            result,
            dumps_options=orjson.OPT_INDENT_2,
        )

    def create_template_from_version(self):
        """Create a SurveyTemplate from a selected form version."""
        version_id = (self.request.form.get("version_id") or "").strip()
        title = (self.request.form.get("template_title") or "").strip()
        if not version_id or not title:
            plone.api.portal.show_message(
                _("Template name and version are required."), type="error"
            )
            return self.request.response.redirect(
                self.context.absolute_url() + "/@@form-versions"
            )

        annos = IAnnotations(self.context)
        form_versions = annos.get(FORM_VERSIONS_KEY, {})
        version_data = form_versions.get(version_id)
        if not version_data:
            plone.api.portal.show_message(_("Version not found"), type="error")
            return self.request.response.redirect(
                self.context.absolute_url() + "/@@form-versions"
            )

        parent = self.context.aq_parent
        if not plone.api.user.has_permission(
            "zopyx.surveyjs.AddSurveyTemplate", obj=parent
        ):
            plone.api.portal.show_message(
                _("You do not have permission to add templates here."), type="error"
            )
            return self.request.response.redirect(
                self.context.absolute_url() + "/@@form-versions"
            )

        try:
            description = self.context.Description()
            template_json = orjson.dumps(
                version_data["form_json"], option=orjson.OPT_INDENT_2
            ).decode("utf-8")

            template = plone.api.content.create(
                container=parent,
                type="SurveyTemplate",
                title=title,
                description=description,
            )
            template.template_json = template_json
            for schema in iterSchemata(self.context):
                for name, field in getFieldsInOrder(schema):
                    if name in ["id", "title", "description"]:
                        continue
                    v = self.context.__dict__.get(name, object)
                    if v is not object:
                        setattr(template, name, v)

            template.reindexObject()
        except Exception as exc:
            plone.api.portal.show_message(
                _("Failed to create template: ${error}", mapping={"error": str(exc)}),
                type="error",
            )
            return self.request.response.redirect(
                self.context.absolute_url() + "/@@form-versions"
            )
        plone.api.portal.show_message(_("Template created successfully."), type="info")
        return self.request.response.redirect(template.absolute_url())
