from plone import api
from plone.api.exc import InvalidParameterError
from Products.CMFPlone.interfaces import INonInstallable
from zope.interface import implementer
import logging
import platform
import uuid

logger = logging.getLogger(__name__)


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


def _prebuild_deno_binary():
    """Pre-build the Deno-based validate binary so it is ready at first use."""
    try:
        from .data_validation.deno_build import deno_build_targets
    except ImportError:
        logger.warning("Cannot import deno_build_targets, skipping pre-build.")
        return
    system = platform.system().lower()
    if system not in ("darwin", "linux"):
        logger.warning("Unsupported platform for Deno pre-build: %s", system)
        return
    logger.info("Pre-building Deno validate binary for %s ...", system)
    try:
        paths = deno_build_targets([system])
        logger.info("Deno validate binary built: %s", paths)
    except Exception as exc:
        logger.warning("Deno validate binary pre-build failed: %s", exc)


def post_install(context):
    """Post install script"""
    _ensure_authenticity_token_secret()
    _prebuild_deno_binary()


def uninstall(context):
    """Uninstall script"""
    # Do something at the end of the uninstallation of this package.
