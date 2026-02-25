import json

from .views import Views


class SurveyEditor(Views):
    """Dedicated browser view for @@editor."""

    @property
    def survey_languages(self):
        values = getattr(self.context, "survey_languages", None) or []
        if isinstance(values, (list, tuple, set)):
            return [str(v).strip() for v in values if str(v).strip()]
        return []

    @property
    def survey_languages_json(self):
        return json.dumps(self.survey_languages)
