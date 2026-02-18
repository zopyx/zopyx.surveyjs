from Products.Five import BrowserView
from Products.Five.browser.pagetemplatefile import ViewPageTemplateFile
import json

from .. import _
from .services.http import json_error, json_response


class SurveyTemplateViewer(BrowserView):
    index = ViewPageTemplateFile("survey_template_viewer.pt")

    def __call__(self):
        return self.index()

    def get_template_json(self):
        raw_json = getattr(self.context, "template_json", "") or ""
        if not raw_json:
            json_error(
                self.request.response,
                404,
                "template_json_missing",
                message=_("No template JSON configured."),
            )
            return
        try:
            payload = json.loads(raw_json)
        except Exception as exc:
            json_error(
                self.request.response,
                400,
                "template_json_invalid",
                message=str(exc),
            )
            return
        if not isinstance(payload, dict):
            json_error(
                self.request.response,
                400,
                "template_json_invalid",
                message=_("Template JSON must be a JSON object."),
            )
            return
        json_response(self.request.response, payload)
