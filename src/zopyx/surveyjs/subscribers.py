# -*- coding: utf-8 -*-
"""Event subscribers for zopyx.surveyjs."""


def log_survey_submission(context, event):
    """Sample listener that logs form submissions to stdout."""
    context_info = getattr(context, "absolute_url", lambda: repr(context))()
    print(f"SurveyJSFormSubmitted: context={context_info} data={event.form_data}")
