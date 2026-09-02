"""Tests for the theme manager and editor views."""

import json
import unittest
from urllib.parse import urlencode

from plone.app.testing import TEST_USER_ID, TEST_USER_NAME, TEST_USER_PASSWORD, setRoles
from plone.testing.zope import Browser
from zope.annotation.interfaces import IAnnotations
from zope.component.hooks import getSite

import transaction

from zopyx.surveyjs.constants import THEMES_KEY
from zopyx.surveyjs.testing import ZOPYX_SURVEYJS_FUNCTIONAL_TESTING  # noqa: E501


class TestThemeManagerViews(unittest.TestCase):
    """Functional tests for @@theme-manager and @@theme-editor."""

    layer = ZOPYX_SURVEYJS_FUNCTIONAL_TESTING

    def setUp(self):
        self.app = self.layer["app"]
        self.portal = self.layer["portal"]
        setRoles(self.portal, TEST_USER_ID, ["Manager"])
        transaction.commit()
        self.browser = Browser(self.app)
        self.browser.raiseHttpErrors = False
        self.browser.addHeader(
            "Authorization",
            "Basic %s:%s" % (TEST_USER_NAME, TEST_USER_PASSWORD),
        )

    def _csrf_token(self):
        """Obtain a fresh CSRF token."""
        self.browser.open(self.portal.absolute_url() + "/@@authenticator/token")
        return self.browser.contents.strip()

    def _post(self, url, data):
        """POST form-encoded data with CSRF protection."""
        token = self._csrf_token()
        data["_authenticator"] = token
        self.browser.open(url, urlencode(data))
        return self.browser.contents

    def _get(self, url):
        """GET a URL and return contents."""
        self.browser.open(url)
        return self.browser.contents

    def test_theme_manager_anonymous_is_rejected(self):
        """Anonymous users are redirected to login."""
        browser = Browser(self.app)
        browser.raiseHttpErrors = False
        browser.open(self.portal.absolute_url() + "/@@theme-manager")
        self.assertIn("/login", browser.url)

    def test_theme_manager_renders_table(self):
        """Manager users see the theme manager page."""
        self.browser.open(self.portal.absolute_url() + "/@@theme-manager")
        self.assertIn("Theme Manager", self.browser.contents)
        self.assertIn("New Theme", self.browser.contents)

    def test_theme_create_and_verify_in_list(self):
        """Create a new theme via POST and verify it appears in the list."""
        self.browser.open(self.portal.absolute_url() + "/@@theme-manager")
        initial_count = self.browser.contents.count("delete-btn")

        resp = self._post(
            self.portal.absolute_url() + "/@@theme-manager",
            {"action": "create", "name": "My Test Theme"},
        )
        payload = json.loads(resp)
        self.assertTrue(payload["success"])
        self.assertIn("theme_id", payload)
        theme_id = payload["theme_id"]

        # Verify it appears in the list
        self.browser.open(self.portal.absolute_url() + "/@@theme-manager")
        self.assertIn("My Test Theme", self.browser.contents)
        new_count = self.browser.contents.count("delete-btn")
        self.assertEqual(new_count, initial_count + 1)

        # Verify in annotations
        annotations = IAnnotations(getSite())
        themes = annotations.get(THEMES_KEY, {})
        self.assertIn(theme_id, themes)
        self.assertEqual(themes[theme_id]["name"], "My Test Theme")

    def test_theme_create_empty_name_fails(self):
        """Creating a theme with empty name returns 400."""
        resp = self._post(
            self.portal.absolute_url() + "/@@theme-manager",
            {"action": "create", "name": ""},
        )
        payload = json.loads(resp)
        self.assertFalse(payload["success"])
        self.assertIn("Name is required", payload.get("error", ""))

    def test_theme_delete_removes_theme(self):
        """Create and then delete a theme."""
        resp = self._post(
            self.portal.absolute_url() + "/@@theme-manager",
            {"action": "create", "name": "Theme To Delete"},
        )
        theme_id = json.loads(resp)["theme_id"]

        resp = self._post(
            self.portal.absolute_url() + "/@@theme-manager",
            {"action": "delete", "theme_id": theme_id},
        )
        payload = json.loads(resp)
        self.assertTrue(payload["success"])

        annotations = IAnnotations(getSite())
        themes = annotations.get(THEMES_KEY, {})
        self.assertNotIn(theme_id, themes)

    def test_theme_upload_validates(self):
        """Upload with missing themeName is rejected."""
        invalid_json = json.dumps({"cssVariables": {"--color": "red"}})
        resp = self._post(
            self.portal.absolute_url() + "/@@theme-manager",
            {"action": "upload", "name": "Bad Theme", "theme_file": invalid_json},
        )
        payload = json.loads(resp)
        self.assertFalse(payload["success"])
        self.assertIn("themeName", payload.get("error", ""))

    def test_theme_upload_success(self):
        """Upload a valid theme JSON."""
        valid_theme = json.dumps({
            "themeName": "UploadedTheme",
            "colorPalette": "light",
            "cssVariables": {"--sjs-primary-backcolor": "#ff0000"},
        })
        resp = self._post(
            self.portal.absolute_url() + "/@@theme-manager",
            {
                "action": "upload",
                "name": "Uploaded Theme",
                "theme_file": valid_theme,
            },
        )
        payload = json.loads(resp)
        self.assertTrue(payload["success"])
        self.assertIn("theme_id", payload)

    def test_theme_download_returns_json(self):
        """Download a theme returns its JSON as attachment."""
        valid_theme = json.dumps({
            "themeName": "DownloadMe",
            "colorPalette": "dark",
            "cssVariables": {"--sjs-font-family": "Arial"},
        })
        resp = self._post(
            self.portal.absolute_url() + "/@@theme-manager",
            {
                "action": "upload",
                "name": "Download Me",
                "theme_file": valid_theme,
            },
        )
        theme_id = json.loads(resp)["theme_id"]

        self.browser.open(
            self.portal.absolute_url()
            + "/@@theme-manager?action=download&theme_id=" + theme_id
        )
        self.assertIn("application/json", self.browser.headers.get("Content-Type", ""))
        self.assertIn("attachment", self.browser.headers.get("Content-Disposition", ""))
        payload = json.loads(self.browser.contents)
        self.assertEqual(payload.get("themeName"), "DownloadMe")

    def test_theme_editor_requires_theme_id(self):
        """Theme editor without theme_id returns 400."""
        self.browser.open(self.portal.absolute_url() + "/@@theme-editor")
        self.assertIn("Missing theme_id parameter", self.browser.contents)

    def test_theme_editor_unknown_theme_returns_404(self):
        """Theme editor with nonexistent theme_id returns 404."""
        self.browser.open(
            self.portal.absolute_url()
            + "/@@theme-editor?theme_id=nonexistent"
        )
        self.assertIn("Theme not found", self.browser.contents)

    def test_theme_editor_save_version(self):
        """Save a new version of a theme."""
        resp = self._post(
            self.portal.absolute_url() + "/@@theme-manager",
            {"action": "create", "name": "Versioned Theme"},
        )
        theme_id = json.loads(resp)["theme_id"]

        theme_json = json.dumps({
            "themeName": "Versioned",
            "cssVariables": {"--sjs-primary-backcolor": "#00ff00"},
        })
        resp = self._post(
            self.portal.absolute_url() + "/@@theme-editor",
            {
                "action": "save_version",
                "theme_id": theme_id,
                "themeJson": theme_json,
            },
        )
        payload = json.loads(resp)
        self.assertTrue(payload["success"])
        self.assertIn("versions", payload)
        self.assertEqual(len(payload["versions"]), 2)

        annotations = IAnnotations(getSite())
        theme = annotations[THEMES_KEY][theme_id]
        self.assertEqual(theme["theme_json"]["themeName"], "Versioned")
        self.assertEqual(len(theme["versions"]), 2)

    def test_theme_editor_save_current_version(self):
        """Save changes without creating another version."""
        resp = self._post(
            self.portal.absolute_url() + "/@@theme-manager",
            {"action": "create", "name": "Current Version Theme"},
        )
        theme_id = json.loads(resp)["theme_id"]
        theme_json = json.dumps({
            "themeName": "Current Version",
            "cssVariables": {"--sjs-primary-backcolor": "#123456"},
        })

        resp = self._post(
            self.portal.absolute_url() + "/@@theme-editor",
            {
                "action": "save_current",
                "theme_id": theme_id,
                "themeJson": theme_json,
            },
        )
        payload = json.loads(resp)
        self.assertTrue(payload["success"])
        self.assertEqual(len(payload["versions"]), 1)

        theme = IAnnotations(getSite())[THEMES_KEY][theme_id]
        self.assertEqual(theme["theme_json"]["themeName"], "Current Version")
        self.assertEqual(len(theme["versions"]), 1)
        version = next(iter(theme["versions"].values()))
        self.assertEqual(version["theme_json"]["themeName"], "Current Version")

    def test_theme_editor_restore_version(self):
        """Restore a previous version of a theme."""
        initial_json = json.dumps({
            "themeName": "RestoreTest",
            "cssVariables": {"--sjs-primary-backcolor": "#0000ff"},
        })
        resp = self._post(
            self.portal.absolute_url() + "/@@theme-manager",
            {
                "action": "upload",
                "name": "Restore Test",
                "theme_file": initial_json,
            },
        )
        theme_id = json.loads(resp)["theme_id"]

        annotations = IAnnotations(getSite())
        theme = annotations[THEMES_KEY][theme_id]
        versions = list(theme["versions"].values())
        initial_version_id = versions[0]["id"]

        updated_json = json.dumps({
            "themeName": "RestoreTest",
            "cssVariables": {"--sjs-primary-backcolor": "#ff0000"},
        })
        self._post(
            self.portal.absolute_url() + "/@@theme-editor",
            {
                "action": "save_version",
                "theme_id": theme_id,
                "themeJson": updated_json,
            },
        )

        annotations = IAnnotations(getSite())
        self.assertEqual(
            annotations[THEMES_KEY][theme_id]["theme_json"]["cssVariables"][
                "--sjs-primary-backcolor"
            ],
            "#ff0000",
        )

        resp = self._post(
            self.portal.absolute_url() + "/@@theme-editor",
            {
                "action": "restore_version",
                "theme_id": theme_id,
                "version_id": initial_version_id,
            },
        )
        payload = json.loads(resp)
        self.assertTrue(payload["success"])
        self.assertEqual(
            payload["theme_json"]["cssVariables"]["--sjs-primary-backcolor"],
            "#0000ff",
        )

        annotations = IAnnotations(getSite())
        self.assertEqual(
            annotations[THEMES_KEY][theme_id]["theme_json"]["cssVariables"][
                "--sjs-primary-backcolor"
            ],
            "#0000ff",
        )

    def test_theme_editor_get_theme_data(self):
        """GET theme data returns the theme JSON."""
        valid_theme = json.dumps({
            "themeName": "GetDataTest",
            "cssVariables": {"--sjs-font-size": "16px"},
        })
        resp = self._post(
            self.portal.absolute_url() + "/@@theme-manager",
            {
                "action": "upload",
                "name": "Get Data",
                "theme_file": valid_theme,
            },
        )
        theme_id = json.loads(resp)["theme_id"]

        resp = self._post(
            self.portal.absolute_url() + "/@@theme-editor",
            {"action": "get_theme_data", "theme_id": theme_id},
        )
        payload = json.loads(resp)
        self.assertEqual(payload.get("themeName"), "GetDataTest")
        self.assertEqual(
            payload.get("cssVariables", {}).get("--sjs-font-size"), "16px"
        )