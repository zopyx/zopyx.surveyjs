# -*- coding: utf-8 -*-
"""Setup tests for this package."""

from plone import api
from plone.app.testing import setRoles, TEST_USER_ID
from zopyx.surveyjs.testing import ZOPYX_SURVEYJS_INTEGRATION_TESTING  # noqa: E501

import unittest


try:
    from Products.CMFPlone.utils import get_installer
except ImportError:
    get_installer = None


class TestSetup(unittest.TestCase):
    """Test that zopyx.surveyjs is properly installed."""

    layer = ZOPYX_SURVEYJS_INTEGRATION_TESTING

    def setUp(self):
        """Custom shared utility setup for tests."""
        self.portal = self.layer["portal"]
        if get_installer:
            self.installer = get_installer(self.portal, self.layer["request"])
        else:
            self.installer = api.portal.get_tool("portal_quickinstaller")

    def test_product_installed(self):
        """Test if zopyx.surveyjs is installed."""
        if hasattr(self.installer, "is_product_installed"):
            installed = self.installer.is_product_installed("zopyx.surveyjs")
        else:
            installed = self.installer.isProductInstalled("zopyx.surveyjs")
        self.assertTrue(installed)

    def test_browserlayer(self):
        """Test that IZopyxSurveyjsLayer is registered."""
        from zopyx.surveyjs.interfaces import IZopyxSurveyjsLayer
        from plone.browserlayer import utils

        self.assertIn(IZopyxSurveyjsLayer, utils.registered_layers())


class TestUninstall(unittest.TestCase):
    layer = ZOPYX_SURVEYJS_INTEGRATION_TESTING

    def setUp(self):
        self.portal = self.layer["portal"]
        if get_installer:
            self.installer = get_installer(self.portal, self.layer["request"])
        else:
            self.installer = api.portal.get_tool("portal_quickinstaller")
        roles_before = api.user.get_roles(TEST_USER_ID)
        setRoles(self.portal, TEST_USER_ID, ["Manager"])
        if hasattr(self.installer, "uninstall_product"):
            self.installer.uninstall_product("zopyx.surveyjs")
        else:
            self.installer.uninstallProducts(["zopyx.surveyjs"])
        setRoles(self.portal, TEST_USER_ID, roles_before)

    def test_product_uninstalled(self):
        """Test if zopyx.surveyjs is cleanly uninstalled."""
        if hasattr(self.installer, "is_product_installed"):
            installed = self.installer.is_product_installed("zopyx.surveyjs")
        else:
            installed = self.installer.isProductInstalled("zopyx.surveyjs")
        self.assertFalse(installed)

    def test_browserlayer_removed(self):
        """Test that IZopyxSurveyjsLayer is removed."""
        from zopyx.surveyjs.interfaces import IZopyxSurveyjsLayer
        from plone.browserlayer import utils

        self.assertNotIn(IZopyxSurveyjsLayer, utils.registered_layers())
