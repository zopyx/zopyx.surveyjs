# -*- coding: utf-8 -*-
"""GenericSetup upgrade steps for zopyx.surveyjs."""

from plone import api


def to_1002(context):
    """Register the new IFormsSettings fields in the Plone registry.

    Re-runs the plone.app.registry import step so the records for the
    new AI provider settings (ai_provider, ollama_model, custom_llm_name,
    custom_api_url, custom_api_key) exist on installations upgrading from
    a previous profile version.
    """
    setup_tool = api.portal.get_tool("portal_setup")
    setup_tool.runImportStepFromProfile(
        "profile-zopyx.surveyjs:default",
        "plone.app.registry",
    )
