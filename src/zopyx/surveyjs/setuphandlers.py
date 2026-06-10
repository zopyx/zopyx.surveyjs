from plone import api
from plone.api.exc import InvalidParameterError
from Products.CMFPlone.interfaces import INonInstallable
from zope.interface import implementer
import uuid


@implementer(INonInstallable)
class HiddenProfiles(object):
    def getNonInstallableProfiles(self):
        """Hide uninstall profile from site-creation and quickinstaller."""
        return [
            "zopyx.surveyjs:uninstall",
        ]


def _ensure_authenticity_token_secret():
    """Set a uuid4 authenticity_token_secret if none is set."""
    secret_key = (
        "zopyx.surveyjs.interfaces.IFormsSettings.authenticity_token_secret"
    )
    enabled_key = (
        "zopyx.surveyjs.interfaces.IFormsSettings.authenticity_token_enabled"
    )
    try:
        current = api.portal.get_registry_record(secret_key)
        if current:
            return
        api.portal.set_registry_record(secret_key, str(uuid.uuid4()))
        api.portal.set_registry_record(enabled_key, True)
    except InvalidParameterError:
        pass


def post_install(context):
    """Post install script"""
    _ensure_authenticity_token_secret()


def uninstall(context):
    """Uninstall script"""
    # Do something at the end of the uninstallation of this package.
