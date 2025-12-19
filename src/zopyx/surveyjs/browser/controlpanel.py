# -*- coding: utf-8 -*-
"""Control panel for Forms settings."""

from plone.app.registry.browser.controlpanel import ControlPanelFormWrapper
from plone.app.registry.browser.controlpanel import RegistryEditForm
from plone.z3cform import layout
from zope.interface import Interface

from ..interfaces import IFormsSettings


class FormsSettingsEditForm(RegistryEditForm):
    """Forms Settings control panel form."""

    schema = IFormsSettings
    label = "Forms Settings"
    description = "Configure AI model settings for form generation"


FormsSettingsControlPanel = layout.wrap_form(
    FormsSettingsEditForm, ControlPanelFormWrapper
)
