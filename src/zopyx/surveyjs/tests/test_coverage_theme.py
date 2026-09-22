"""Statement-coverage tests for the theme/survey editor views and services.

Targets: ``browser/survey_editor.py``, ``browser/theme_editor.py``,
``browser/theme_manager.py``, ``browser/services/themes.py`` and
``browser/services/export.py``.
"""

from __future__ import annotations

import io
import json
import unittest
from datetime import datetime, timezone
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import MagicMock, patch
from urllib.parse import urlencode

import transaction
from BTrees.OOBTree import OOBTree
from docx import Document as DocxDocument
from openpyxl import load_workbook
from plone import api
from plone.app.testing import (
    TEST_USER_ID,
    TEST_USER_NAME,
    TEST_USER_PASSWORD,
    setRoles,
)
from plone.testing.zope import Browser
from zope.annotation.interfaces import IAnnotations

from zopyx.surveyjs.browser import survey_editor as survey_editor_module
from zopyx.surveyjs.browser import theme_editor as theme_editor_module
from zopyx.surveyjs.browser import theme_manager as theme_manager_module
from zopyx.surveyjs.browser.services import export as export_service
from zopyx.surveyjs.browser.services import themes as themes_service
from zopyx.surveyjs.browser.survey_editor import SurveyEditor
from zopyx.surveyjs.browser.theme_editor import ThemeEditorView
from zopyx.surveyjs.browser.theme_manager import ThemeManagerView
from zopyx.surveyjs.constants import DEFAULT_THEME_KEY, THEMES_KEY
from zopyx.surveyjs.converters.types import Attachment, Item
from zopyx.surveyjs.testing import (
    ZOPYX_SURVEYJS_FUNCTIONAL_TESTING,
    ZOPYX_SURVEYJS_INTEGRATION_TESTING,
)


def _theme_json(name: str, color: str = "#123456") -> dict:
    """Return a SurveyJS v2 preset-format theme definition."""
    return {
        "themeName": name,
        "colorPalette": "light",
        "isPanelless": False,
        "cssVariables": {"--sjs-primary-backcolor": color},
    }


# ---------------------------------------------------------------------------
# themes.py service layer
# ---------------------------------------------------------------------------


class ThemeServiceCoverageTests(unittest.TestCase):
    """Drive every service-layer branch of ``browser/services/themes.py``."""

    layer = ZOPYX_SURVEYJS_INTEGRATION_TESTING

    def setUp(self) -> None:
        self.portal = self.layer["portal"]
        setRoles(self.portal, TEST_USER_ID, ["Manager"])
        self.annotations = IAnnotations(self.portal)
        self._created: list[str] = []
        self._original_default = themes_service.get_default_theme_id(self.annotations)
        self.addCleanup(self._cleanup_annotations)

    def _cleanup_annotations(self) -> None:
        themes = self.annotations.get(THEMES_KEY)
        if themes is not None:
            for theme_id in self._created:
                themes.pop(theme_id, None)
        if self._original_default is None:
            self.annotations.pop(DEFAULT_THEME_KEY, None)
        else:
            self.annotations[DEFAULT_THEME_KEY] = self._original_default

    def _create(self, name: str = "Coverage Theme", theme_json: dict | None = None):
        theme = themes_service.create_theme(
            self.annotations,
            name,
            theme_json if theme_json is not None else _theme_json(name),
            user_id=TEST_USER_ID,
        )
        self._created.append(theme["id"])
        return theme

    def test_create_theme_stores_initial_version(self) -> None:
        payload = _theme_json("Create Me")
        theme = themes_service.create_theme(
            self.annotations, "  Create Me  ", payload, user_id="alice"
        )
        self._created.append(theme["id"])

        self.assertEqual(theme["name"], "Create Me")
        self.assertEqual(theme["theme_json"], payload)
        self.assertEqual(len(theme["versions"]), 1)
        self.assertIsInstance(theme["created"], datetime)
        self.assertIsNotNone(theme["created"].tzinfo)
        self.assertIsInstance(theme["modified"], datetime)

        version = next(iter(theme["versions"].values()))
        self.assertEqual(version["user"], "alice")
        self.assertEqual(version["theme_json"], payload)
        self.assertEqual(version["id"], next(iter(theme["versions"])))

        # Persisted in the annotations container, retrievable and sortable
        self.assertIs(self.annotations[THEMES_KEY][theme["id"]], theme)
        self.assertIs(themes_service.get_theme(self.annotations, theme["id"]), theme)
        self.assertIsNone(themes_service.get_theme(self.annotations, "does-not-exist"))

        other = self._create("aaa alphabetically first")
        names = [t["name"] for t in themes_service.list_themes(self.annotations)]
        self.assertLess(
            names.index("aaa alphabetically first"), names.index("Create Me")
        )
        self.assertIn(other["id"], self.annotations[THEMES_KEY])

    def test_save_theme_current_version_updates_newest_version(self) -> None:
        theme = self._create("Current Version")
        updated = _theme_json("Current Version", "#abcdef")

        result = themes_service.save_theme_current_version(
            self.annotations, theme["id"], updated, "bob"
        )

        self.assertIs(result, theme)
        self.assertEqual(result["theme_json"], updated)
        self.assertEqual(len(result["versions"]), 1)
        version = next(iter(result["versions"].values()))
        self.assertEqual(version["theme_json"], updated)
        self.assertEqual(version["user"], "bob")
        self.assertGreaterEqual(result["modified"], result["created"])
        self.assertIs(self.annotations[THEMES_KEY][theme["id"]], result)

    def test_save_theme_current_version_returns_none_without_theme_or_versions(
        self,
    ) -> None:
        self.assertIsNone(
            themes_service.save_theme_current_version(
                self.annotations, "missing-theme", _theme_json("X"), "bob"
            )
        )

        # Theme entry that carries no versions at all
        container = themes_service.ensure_themes(self.annotations)
        theme_id = "coverage-theme-without-versions"
        container[theme_id] = dict(
            id=theme_id,
            name="Without Versions",
            created=datetime.now(timezone.utc),
            modified=datetime.now(timezone.utc),
            theme_json=_theme_json("Without Versions"),
            versions=OOBTree(),
        )
        self._created.append(theme_id)

        self.assertIsNone(
            themes_service.save_theme_current_version(
                self.annotations, theme_id, _theme_json("Updated"), "bob"
            )
        )
        self.assertEqual(
            container[theme_id]["theme_json"], _theme_json("Without Versions")
        )
        self.assertEqual(len(container[theme_id]["versions"]), 0)

    def test_save_theme_version_appends_history_entry(self) -> None:
        self.assertIsNone(
            themes_service.save_theme_version(
                self.annotations, "missing-theme", _theme_json("X"), "bob"
            )
        )

        theme = self._create("History Theme")
        previous_modified = theme["modified"]
        updated = _theme_json("History Theme", "#00ff00")

        result = themes_service.save_theme_version(
            self.annotations, theme["id"], updated, "carol"
        )

        self.assertIs(result, theme)
        self.assertEqual(result["theme_json"], updated)
        self.assertEqual(len(result["versions"]), 2)
        self.assertGreaterEqual(result["modified"], previous_modified)
        newest = themes_service.sorted_theme_versions(result, reverse=True)[0]
        self.assertEqual(newest["user"], "carol")
        self.assertEqual(newest["theme_json"], updated)
        self.assertEqual(
            themes_service.sorted_theme_versions(result, reverse=True),
            list(reversed(themes_service.sorted_theme_versions(result))),
        )

    def test_restore_theme_version_handles_unknown_ids(self) -> None:
        self.assertIsNone(
            themes_service.restore_theme_version(
                self.annotations, "missing-theme", "missing-version"
            )
        )

        theme = self._create("Restore Me")
        version_id = next(iter(theme["versions"]))
        # Unknown version on an existing theme
        self.assertIsNone(
            themes_service.restore_theme_version(
                self.annotations, theme["id"], "missing-version"
            )
        )
        self.assertEqual(theme["theme_json"]["themeName"], "Restore Me")

        new_version = themes_service.save_theme_version(
            self.annotations, theme["id"], _theme_json("Restore Me", "#0000ff"), "carol"
        )
        versions_newest_first = themes_service.sorted_theme_versions(
            new_version, reverse=True
        )
        self.assertEqual(
            versions_newest_first[0]["theme_json"]["themeName"], "Restore Me"
        )

        restored = themes_service.restore_theme_version(
            self.annotations, theme["id"], version_id
        )
        self.assertIs(restored, theme)
        self.assertEqual(restored["theme_json"]["themeName"], "Restore Me")
        self.assertEqual(
            restored["theme_json"],
            themes_service.get_theme(self.annotations, theme["id"])["theme_json"],
        )

    def test_delete_theme_clears_default_and_reports_missing(self) -> None:
        theme = self._create("Default To Delete")

        self.assertTrue(themes_service.set_default_theme(self.annotations, theme["id"]))
        self.assertEqual(
            themes_service.get_default_theme_id(self.annotations), theme["id"]
        )

        self.assertTrue(themes_service.delete_theme(self.annotations, theme["id"]))
        self.assertNotIn(theme["id"], self.annotations.get(THEMES_KEY, {}))
        self.assertIsNone(themes_service.get_default_theme_id(self.annotations))

        # Deleting an unknown theme reports failure and keeps the default intact
        kept = self._create("Kept Theme")
        themes_service.set_default_theme(self.annotations, kept["id"])
        self.assertFalse(themes_service.delete_theme(self.annotations, "missing-theme"))
        self.assertEqual(
            themes_service.get_default_theme_id(self.annotations), kept["id"]
        )

    def test_set_default_theme_rejects_unknown_theme(self) -> None:
        self.assertFalse(themes_service.set_default_theme(self.annotations, "nope"))
        self.assertIsNone(themes_service.get_default_theme_id(self.annotations))


# ---------------------------------------------------------------------------
# export.py service layer
# ---------------------------------------------------------------------------


class ExportServiceCoverageTests(unittest.TestCase):
    """Exercise every ``write_export`` dispatcher with the real converters."""

    def setUp(self) -> None:
        self._tmp = TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.output_dir = Path(self._tmp.name)
        self.attachments = [
            Attachment(
                name="photo.png",
                content=b"\x89PNG\r\n\x1a\nbinary",
                content_type="image/png",
            )
        ]
        self.items = [
            Item(
                key="q1",
                label="Question 1",
                values=["answer-1"],
                attachments=[],
                field_type="text",
            ),
            Item(
                key="q2",
                label="Upload",
                values=["photo.png"],
                attachments=list(self.attachments),
                field_type="file",
            ),
            Item(
                key="q3",
                label="Matrix",
                values=["v1"],
                attachments=[],
                field_type="matrixdynamic",
                table=[["Col A", "Col B"], ["v1", "v2"]],
            ),
        ]

    def _export(self, format_key: str, poll_id: str = "poll-1"):
        return export_service.write_export(
            format_key,
            poll_id,
            self.items,
            self.attachments,
            "Alice Example",
            "2024-02-02T10:00:00+00:00",
            self.output_dir,
        )

    def test_write_export_text(self) -> None:
        path = self._export("text")
        self.assertEqual(path, self.output_dir / "poll-1.txt")
        text = path.read_text(encoding="utf-8")
        self.assertIn("Survey response", text)
        self.assertIn("Question 1:", text)
        self.assertIn("  - answer-1", text)
        self.assertIn("Alice Example", text)

    def test_write_export_markdown(self) -> None:
        path = self._export("md")
        self.assertEqual(path, self.output_dir / "poll-1.md")
        text = path.read_text(encoding="utf-8")
        self.assertIn("# Survey response (poll-1)", text)
        self.assertIn("Question 1", text)
        self.assertIn("answer-1", text)

    def test_write_export_html(self) -> None:
        path = self._export("html")
        self.assertEqual(path, self.output_dir / "poll-1.html")
        text = path.read_text(encoding="utf-8")
        self.assertIn("<html", text)
        self.assertIn("Question 1", text)
        self.assertIn("answer-1", text)
        # Attachments are inlined as data URLs by build_html
        self.assertIn("data:image/png;base64,", text)

    def test_write_export_pdf(self) -> None:
        path = self._export("pdf")
        self.assertEqual(path, self.output_dir / "poll-1.pdf")
        data = path.read_bytes()
        self.assertTrue(data.startswith(b"%PDF-"), data[:8])
        self.assertGreater(len(data), 1000)

    def test_write_export_csv(self) -> None:
        path = self._export("csv")
        self.assertEqual(path, self.output_dir / "poll-1.csv")
        rows = path.read_text(encoding="utf-8").splitlines()
        self.assertEqual(rows[0], "Key,Field,Value,Attachments")
        self.assertIn("q1,Question 1,answer-1,", rows[1])
        self.assertIn("photo.png (image/png)", rows[2])

    def test_write_export_xlsx(self) -> None:
        path = self._export("xlsx")
        self.assertEqual(path, self.output_dir / "poll-1.xlsx")
        self.assertTrue(path.read_bytes().startswith(b"PK"))

        workbook = load_workbook(filename=str(path))
        sheet = workbook.active
        self.assertEqual(sheet.title, "Survey")
        self.assertEqual(
            [cell.value for cell in sheet[1]], ["Key", "Field", "Value", "Attachments"]
        )
        self.assertEqual(
            [cell.value for cell in sheet[2]], ["q1", "Question 1", "answer-1", None]
        )
        self.assertEqual(sheet["B3"].value, "Upload")
        self.assertEqual(
            [cell.value for cell in sheet[4]], ["q3", "Matrix", "v1", None]
        )

    def test_write_export_xml(self) -> None:
        path = self._export("xml")
        self.assertEqual(path, self.output_dir / "poll-1.xml")
        text = path.read_text(encoding="utf-8")
        self.assertTrue(text.startswith("<?xml"), text[:20])
        self.assertIn("poll-1", text)
        self.assertIn("answer-1", text)

    def test_write_export_docx(self) -> None:
        path = self._export("docx")
        self.assertEqual(path, self.output_dir / "poll-1.docx")
        self.assertTrue(path.read_bytes().startswith(b"PK"))

        document = DocxDocument(str(path))
        paragraphs = [p.text for p in document.paragraphs]
        self.assertIn("Survey Response: poll-1", paragraphs)
        self.assertIn("Alice Example", " ".join(paragraphs))
        self.assertIn("- answer-1", paragraphs)
        self.assertIn("Attachment: photo.png (image/png)", paragraphs)

        table_text = [
            cell.text
            for table in document.tables
            for row in table.rows
            for cell in row.cells
        ]
        self.assertIn("Col A", table_text)
        self.assertIn("v2", table_text)

    def test_write_export_json(self) -> None:
        path = self._export("json")
        self.assertEqual(path, self.output_dir / "poll-1.json")
        payload = json.loads(path.read_text(encoding="utf-8"))
        self.assertEqual(payload["poll_id"], "poll-1")
        self.assertEqual(payload["creator"], "Alice Example")
        self.assertEqual(
            [field["key"] for field in payload["fields"]], ["q1", "q2", "q3"]
        )
        self.assertEqual(
            payload["fields"][2]["table"], [["Col A", "Col B"], ["v1", "v2"]]
        )

    def test_write_export_unknown_format_writes_nothing(self) -> None:
        path = self._export("bogus")
        self.assertIsNone(path)
        self.assertEqual(list(self.output_dir.iterdir()), [])


# ---------------------------------------------------------------------------
# HTTP level coverage of the three browser views
# ---------------------------------------------------------------------------


class _ThemeHttpTestCase(unittest.TestCase):
    """Shared browser/CSRF plumbing for the theme view HTTP tests."""

    layer = ZOPYX_SURVEYJS_FUNCTIONAL_TESTING

    def setUp(self) -> None:
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
        self._created: list[str] = []
        self._original_default = IAnnotations(self.portal).get(DEFAULT_THEME_KEY, None)
        self.addCleanup(self._cleanup_themes)

    def _cleanup_themes(self) -> None:
        annotations = IAnnotations(self.portal)
        themes = annotations.get(THEMES_KEY)
        if themes is not None:
            for theme_id in self._created:
                themes.pop(theme_id, None)
        if self._original_default is None:
            annotations.pop(DEFAULT_THEME_KEY, None)
        else:
            annotations[DEFAULT_THEME_KEY] = self._original_default
        transaction.commit()

    def _csrf_token(self) -> str:
        self.browser.open(self.portal.absolute_url() + "/@@authenticator/token")
        return self.browser.contents.strip()

    def _post(self, url: str, data: dict) -> str:
        payload = dict(data)
        payload["_authenticator"] = self._csrf_token()
        self.browser.open(url, urlencode(payload))
        return self.browser.contents

    def _get(self, url: str) -> str:
        self.browser.open(url)
        return self.browser.contents

    def _manager_url(self) -> str:
        return self.portal.absolute_url() + "/@@theme-manager"

    def _editor_url(self) -> str:
        return self.portal.absolute_url() + "/@@theme-editor"

    def _create_theme(self, name: str = "Coverage Theme") -> str:
        response = self._post(self._manager_url(), {"action": "create", "name": name})
        payload = json.loads(response)
        self.assertTrue(payload["success"], response)
        self._created.append(payload["theme_id"])
        return payload["theme_id"]

    def _upload_theme(
        self, name: str | None = "Coverage Upload", theme: dict | None = None
    ) -> str:
        data = {
            "action": "upload",
            "theme_file": json.dumps(theme or _theme_json("Coverage Upload")),
        }
        if name is not None:
            data["name"] = name
        response = self._post(self._manager_url(), data)
        payload = json.loads(response)
        self.assertTrue(payload["success"], response)
        self._created.append(payload["theme_id"])
        return payload["theme_id"]


class ThemeManagerHttpCoverageTests(_ThemeHttpTestCase):
    """Cover the error/set-default/download branches of the theme manager."""

    def test_set_default_theme_via_post(self) -> None:
        first = self._create_theme("Coverage Theme A")
        second = self._create_theme("Coverage Theme B")

        response = self._post(
            self._manager_url(), {"action": "set_default", "theme_id": second}
        )
        self.assertEqual(json.loads(response), {"success": True})
        self.assertEqual(IAnnotations(self.portal).get(DEFAULT_THEME_KEY, None), second)

        contents = self._get(self._manager_url())
        row_start = contents.index("Coverage Theme B")
        row_start = contents.rindex("<tr", 0, row_start)
        row_end = contents.index("</tr>", row_start)
        default_row = contents[row_start:row_end]
        self.assertIn("theme-default-badge", default_row)
        self.assertNotIn("make-default-btn", default_row)

        other_start = contents.rindex("<tr", 0, contents.index("Coverage Theme A"))
        other_row = contents[other_start : contents.index("</tr>", other_start)]
        self.assertNotIn("theme-default-badge", other_row)
        self.assertIn("make-default-btn", other_row)

        self.assertIn(first, contents)
        self.assertIn(second, contents)

    def test_set_default_theme_requires_and_validates_theme_id(self) -> None:
        response = self._post(self._manager_url(), {"action": "set_default"})
        payload = json.loads(response)
        self.assertFalse(payload["success"])
        self.assertEqual(payload["error"], "theme_id is required")
        self.assertEqual(
            IAnnotations(self.portal).get(DEFAULT_THEME_KEY, None),
            self._original_default,
        )

        response = self._post(
            self._manager_url(), {"action": "set_default", "theme_id": "unknown-theme"}
        )
        self.assertEqual(json.loads(response), {"success": False})
        self.assertEqual(
            IAnnotations(self.portal).get(DEFAULT_THEME_KEY, None),
            self._original_default,
        )

    def test_delete_theme_requires_theme_id(self) -> None:
        response = self._post(self._manager_url(), {"action": "delete"})
        payload = json.loads(response)
        self.assertFalse(payload["success"])
        self.assertEqual(payload["error"], "theme_id is required")

    def test_upload_rejects_missing_and_invalid_payloads(self) -> None:
        response = self._post(self._manager_url(), {"action": "upload"})
        payload = json.loads(response)
        self.assertFalse(payload["success"])
        self.assertEqual(payload["error"], "No file uploaded")

        response = self._post(
            self._manager_url(), {"action": "upload", "theme_file": "{not json"}
        )
        payload = json.loads(response)
        self.assertFalse(payload["success"])
        self.assertIn("Invalid JSON:", payload["error"])

    def test_upload_without_name_uses_theme_name(self) -> None:
        theme_id = self._upload_theme(
            name=None, theme=_theme_json("Name From File", "#ff0000")
        )
        stored = IAnnotations(self.portal)[THEMES_KEY][theme_id]
        self.assertEqual(stored["name"], "Name From File")
        self.assertEqual(stored["theme_json"]["themeName"], "Name From File")

    def test_download_unknown_theme_returns_error(self) -> None:
        contents = self._get(self._manager_url() + "?action=download&theme_id=missing")
        payload = json.loads(contents)
        self.assertFalse(payload["success"])
        self.assertEqual(payload["error"], "Theme not found")


class ThemeEditorHttpCoverageTests(_ThemeHttpTestCase):
    """Cover the render, export and validation branches of the theme editor."""

    def test_get_renders_editor_page_with_versions(self) -> None:
        theme_id = self._upload_theme(name="Editor Render")

        contents = self._get(f"{self._editor_url()}?theme_id={theme_id}")

        self.assertIn("survey-editor-config", contents)
        self.assertIn(f'data-theme-id="{theme_id}"', contents)
        self.assertIn('data-theme-name="Editor Render"', contents)

        marker = contents.index('id="theme-versions-data"')
        json_start = contents.index(">", marker) + 1
        json_end = contents.index("</script>", json_start)
        versions = json.loads(contents[json_start:json_end])
        self.assertEqual(len(versions), 1)
        self.assertEqual(versions[0]["number"], 1)
        self.assertEqual(versions[0]["user"], TEST_USER_ID)
        self.assertIsNotNone(datetime.fromisoformat(versions[0]["created"]).tzinfo)
        stored_version = next(
            iter(IAnnotations(self.portal)[THEMES_KEY][theme_id]["versions"])
        )
        self.assertEqual(versions[0]["id"], stored_version)

    def test_editor_get_theme_data_action(self) -> None:
        theme_id = self._upload_theme(
            name="Editor Data", theme=_theme_json("Editor Data", "#00ff00")
        )
        contents = self._post(
            self._editor_url(),
            {"action": "get_theme_data", "theme_id": theme_id},
        )
        self.assertEqual(json.loads(contents)["themeName"], "Editor Data")

    def test_export_theme_action_returns_download(self) -> None:
        theme_id = self._create_theme("Coverage Export Theme")
        exported = _theme_json("Coverage Export Theme", "#abcdef")

        contents = self._post(
            self._editor_url(),
            {
                "action": "export_theme",
                "theme_id": theme_id,
                "themeJson": json.dumps(exported),
            },
        )

        self.assertEqual(json.loads(contents), exported)
        self.assertEqual(
            self.browser.headers.get("Content-Type"),
            "application/json; charset=utf-8",
        )
        self.assertEqual(
            self.browser.headers.get("Content-Disposition"),
            'attachment; filename="Coverage_Export_Theme.json"',
        )
        self.assertEqual(
            self.browser.headers.get("Content-Length"),
            str(len(json.dumps(exported, indent=2).encode("utf-8"))),
        )
        # The stored theme is untouched by the export
        stored = IAnnotations(self.portal)[THEMES_KEY][theme_id]
        self.assertEqual(stored["theme_json"], {})

    def test_export_theme_without_payload_uses_stored_json(self) -> None:
        theme_id = self._upload_theme(
            name="Stored Export", theme=_theme_json("Stored Export", "#111111")
        )
        contents = self._post(
            self._editor_url(), {"action": "export_theme", "theme_id": theme_id}
        )
        self.assertEqual(json.loads(contents)["themeName"], "Stored Export")

    def test_save_actions_require_theme_json_payload(self) -> None:
        theme_id = self._create_theme("Coverage Missing Payload")
        for action in ("save_version", "save_current"):
            response = self._post(
                self._editor_url(), {"action": action, "theme_id": theme_id}
            )
            payload = json.loads(response)
            self.assertFalse(payload["success"], action)
            self.assertEqual(payload["error"], "No theme JSON provided")

        stored = IAnnotations(self.portal)[THEMES_KEY][theme_id]
        self.assertEqual(len(stored["versions"]), 1)

    def test_restore_version_requires_and_validates_version_id(self) -> None:
        theme_id = self._create_theme("Coverage Restore Validation")

        response = self._post(
            self._editor_url(), {"action": "restore_version", "theme_id": theme_id}
        )
        payload = json.loads(response)
        self.assertFalse(payload["success"])
        self.assertEqual(payload["error"], "version_id is required")

        response = self._post(
            self._editor_url(),
            {
                "action": "restore_version",
                "theme_id": theme_id,
                "version_id": "unknown-version",
            },
        )
        payload = json.loads(response)
        self.assertFalse(payload["success"])
        self.assertEqual(payload["error"], "Version not found")


class SurveyEditorHttpCoverageTests(_ThemeHttpTestCase):
    """Cover the ``@@editor`` GET/POST paths against a real survey object."""

    def setUp(self) -> None:
        super().setUp()
        self.survey = api.content.create(
            container=self.portal,
            type="Survey",
            id="coverage-editor-survey",
            title="Coverage Editor Survey",
        )
        transaction.commit()
        self.survey_url = f"{self.portal.absolute_url()}/coverage-editor-survey"

    def test_get_editor_renders_config_with_theme_choices(self) -> None:
        theme_id = self._upload_theme(
            name="Editor Choices", theme=_theme_json("Editor Choices", "#00ff00")
        )

        contents = self._get(self.survey_url + "/@@editor")

        self.assertIn("survey-editor-config", contents)
        # survey_languages is unset on the object -> empty JSON list
        self.assertIn('data-survey-languages="[]"', contents)
        self.assertIn('data-survey-current-theme=""', contents)
        self.assertIn("Editor Choices", contents)
        self.assertIn(theme_id, contents)

    def test_post_save_theme_sets_survey_theme(self) -> None:
        theme_id = self._upload_theme(
            name="Assigned Theme", theme=_theme_json("Assigned")
        )

        response = self._post(
            self.survey_url + "/@@editor",
            {"action": "save_theme", "theme_id": theme_id},
        )
        payload = json.loads(response)
        self.assertTrue(payload["success"])
        self.assertEqual(payload["theme_id"], theme_id)
        self.assertEqual(self.browser.headers.get("Content-Type"), "application/json")

        stored_survey = self.portal["coverage-editor-survey"]
        self.assertEqual(stored_survey.theme, theme_id)

        # A second POST without theme_id clears the assignment again
        response = self._post(self.survey_url + "/@@editor", {"action": "save_theme"})
        payload = json.loads(response)
        self.assertTrue(payload["success"])
        self.assertEqual(payload["theme_id"], "")
        self.assertIsNone(self.portal["coverage-editor-survey"].theme)

    def test_get_editor_theme_json_action(self) -> None:
        theme_id = self._upload_theme(
            name="Editor JSON", theme=_theme_json("Editor JSON", "#222222")
        )

        contents = self._get(
            self.survey_url + f"/@@editor?action=get_theme_json&theme_id={theme_id}"
        )
        self.assertEqual(json.loads(contents)["themeName"], "Editor JSON")

        # Missing and unknown theme ids both yield an empty JSON object
        self.assertEqual(
            json.loads(self._get(self.survey_url + "/@@editor?action=get_theme_json")),
            {},
        )
        self.assertEqual(
            json.loads(
                self._get(
                    self.survey_url
                    + "/@@editor?action=get_theme_json&theme_id=unknown-theme"
                )
            ),
            {},
        )


# ---------------------------------------------------------------------------
# Unit level coverage of branches that HTTP requests cannot reach
# ---------------------------------------------------------------------------


class _MockViewTestCase(unittest.TestCase):
    """Base for branch tests that drive view methods with a mock request."""

    layer = ZOPYX_SURVEYJS_FUNCTIONAL_TESTING

    def setUp(self) -> None:
        self.portal = self.layer["portal"]
        setRoles(self.portal, TEST_USER_ID, ["Manager"])
        transaction.commit()

    def _view(self, cls):
        view = cls.__new__(cls)
        view.context = MagicMock()
        view.context.absolute_url.return_value = "http://nohost/plone/survey"
        view.request = MagicMock()
        view.request.form = {}
        view.request.response = MagicMock()
        view.request.get.return_value = "GET"
        return view


class ThemeEditorBranchTests(_MockViewTestCase):
    """Failure branches of ``browser/theme_editor.py``."""

    def _editor(self):
        view = self._view(ThemeEditorView)
        view._theme = dict(
            id="coverage-theme-id",
            name="Coverage Editor Theme",
            theme_json=_theme_json("Coverage Editor Theme"),
            versions=OOBTree(),
        )
        return view

    def test_save_current_version_without_current_version_returns_404(self) -> None:
        view = self._editor()
        view.request.form = {"themeJson": json.dumps(_theme_json("Updated"))}

        with (
            patch.object(theme_editor_module, "getSite", return_value=self.portal),
            patch.object(
                theme_editor_module.themes_service,
                "save_theme_current_version",
                return_value=None,
            ) as save,
        ):
            result = view._save_current_version()

        save.assert_called_once()
        self.assertEqual(save.call_args.args[0:2][1], "coverage-theme-id")
        self.assertEqual(
            json.loads(result),
            {"success": False, "error": "Theme has no current version"},
        )
        view.request.response.setStatus.assert_called_once_with(404)
        view.request.response.setHeader.assert_not_called()

    def test_save_current_version_failure_returns_500(self) -> None:
        view = self._editor()
        view.request.form = {"themeJson": json.dumps(_theme_json("Updated"))}

        with patch.object(
            theme_editor_module.themes_service,
            "save_theme_current_version",
            side_effect=RuntimeError("storage exploded"),
        ):
            result = view._save_current_version()

        payload = json.loads(result)
        self.assertFalse(payload["success"])
        self.assertIn("storage exploded", payload["error"])
        view.request.response.setStatus.assert_called_once_with(500)
        view.request.response.setHeader.assert_called_once_with(
            "Content-Type", "application/json"
        )

    def test_save_version_failure_returns_500(self) -> None:
        view = self._editor()
        view.request.form = {"themeJson": json.dumps(_theme_json("Updated"))}

        with patch.object(
            theme_editor_module.themes_service,
            "save_theme_version",
            side_effect=ValueError("bad version"),
        ):
            result = view._save_version()

        payload = json.loads(result)
        self.assertFalse(payload["success"])
        self.assertIn("bad version", payload["error"])
        view.request.response.setStatus.assert_called_once_with(500)

    def test_export_theme_failure_returns_500(self) -> None:
        view = self._editor()
        view._theme = MagicMock()
        view._theme.get.side_effect = RuntimeError("theme metadata broken")
        view.request.form = {}

        result = view._export_theme_json()

        payload = json.loads(result)
        self.assertFalse(payload["success"])
        self.assertIn("theme metadata broken", payload["error"])
        view.request.response.setStatus.assert_called_once_with(500)
        view.request.response.setHeader.assert_called_once_with(
            "Content-Type", "application/json"
        )

    def test_versions_json_reports_newest_first(self) -> None:
        view = self._editor()
        older = datetime(2024, 1, 1, 12, 0, tzinfo=timezone.utc)
        newer = datetime(2024, 2, 2, 12, 0, tzinfo=timezone.utc)
        view._theme = {
            "id": "coverage-theme-id",
            "name": "Versions",
            "versions": {
                "old": {"id": "old", "created": older, "user": "alice"},
                "new": {"id": "new", "created": newer, "user": "bob"},
            },
        }

        versions = json.loads(view.versions_json)

        self.assertEqual([v["id"] for v in versions], ["new", "old"])
        self.assertEqual([v["number"] for v in versions], [2, 3])
        self.assertEqual(versions[0]["created"], newer.isoformat())
        self.assertEqual(versions[0]["user"], "bob")
        self.assertEqual(versions[1]["created"], older.isoformat())

    def test_current_user_falls_back_to_admin(self) -> None:
        view = self._editor()
        with patch(
            "plone.api.user.get_current", side_effect=RuntimeError("no request")
        ):
            self.assertEqual(view._current_user(), "admin")

        with patch("plone.api.user.get_current") as get_current:
            get_current.return_value.getId.return_value = "coverage-user"
            self.assertEqual(view._current_user(), "coverage-user")


class ThemeManagerBranchTests(_MockViewTestCase):
    """Failure branches of ``browser/theme_manager.py``."""

    def test_upload_accepts_file_objects_and_bytes(self) -> None:
        view = self._view(ThemeManagerView)
        theme = _theme_json("BytesIO Theme", "#334455")
        view.request.form = {
            "theme_file": io.BytesIO(json.dumps(theme).encode("utf-8")),
            "name": "BytesIO Upload",
        }
        view.request.get.return_value = None

        with patch.object(theme_manager_module, "getSite", return_value=self.portal):
            result = view._upload_theme()

        payload = json.loads(result)
        self.assertTrue(payload["success"], result)
        theme_id = payload["theme_id"]
        self.addCleanup(self._drop_theme, theme_id)

        stored = IAnnotations(self.portal)[THEMES_KEY][theme_id]
        self.assertEqual(stored["name"], "BytesIO Upload")
        self.assertEqual(stored["theme_json"], theme)

    def test_upload_rejects_non_utf8_bytes(self) -> None:
        view = self._view(ThemeManagerView)
        view.request.form = {
            "theme_file": io.BytesIO(b"\xff\xfe\x00not utf8"),
            "name": "Broken Upload",
        }
        view.request.get.return_value = None

        with patch.object(theme_manager_module, "getSite", return_value=self.portal):
            result = view._upload_theme()

        payload = json.loads(result)
        self.assertFalse(payload["success"])
        self.assertTrue(payload["error"].startswith("Invalid JSON:"))

    def test_current_user_falls_back_to_admin(self) -> None:
        view = self._view(ThemeManagerView)
        with patch(
            "plone.api.user.get_current", side_effect=RuntimeError("no request")
        ):
            self.assertEqual(view._current_user(), "admin")

    def _drop_theme(self, theme_id: str) -> None:
        themes = IAnnotations(self.portal).get(THEMES_KEY)
        if themes is not None:
            themes.pop(theme_id, None)
        transaction.commit()


class SurveyEditorBranchTests(_MockViewTestCase):
    """Branches of ``browser/survey_editor.py`` not reachable over HTTP."""

    def test_survey_languages_normalizes_and_rejects_other_types(self) -> None:
        view = self._view(SurveyEditor)
        view.context.survey_languages = ["de", " ", "en", ""]
        self.assertEqual(view.survey_languages, ["de", "en"])
        self.assertEqual(json.loads(view.survey_languages_json), ["de", "en"])

        view.context.survey_languages = ("fr",)
        self.assertEqual(view.survey_languages, ["fr"])

        view.context.survey_languages = {"de"}
        self.assertEqual(view.survey_languages, ["de"])

        view.context.survey_languages = "de"
        self.assertEqual(view.survey_languages, [])
        self.assertEqual(json.loads(view.survey_languages_json), [])

        view.context.survey_languages = None
        self.assertEqual(view.survey_languages, [])

    def test_current_theme_id_defaults_to_empty_string(self) -> None:
        view = self._view(SurveyEditor)
        view.context.theme = None
        self.assertEqual(view.current_theme_id, "")
        view.context.theme = "theme-1"
        self.assertEqual(view.current_theme_id, "theme-1")

    def test_themes_choices_without_site_or_with_broken_service(self) -> None:
        view = self._view(SurveyEditor)

        with patch.object(survey_editor_module, "getSite", return_value=None):
            self.assertEqual(view.themes_choices, [{"value": "", "text": "No theme"}])

        with (
            patch.object(survey_editor_module, "getSite", return_value=self.portal),
            patch.object(
                survey_editor_module.themes_service,
                "list_themes",
                side_effect=RuntimeError("boom"),
            ),
        ):
            self.assertEqual(view.themes_choices, [{"value": "", "text": "No theme"}])

    def test_themes_choices_skips_theme_without_id(self) -> None:
        view = self._view(SurveyEditor)
        with (
            patch.object(survey_editor_module, "getSite", return_value=self.portal),
            patch.object(
                survey_editor_module.themes_service,
                "list_themes",
                return_value=[
                    {"id": "theme-a", "name": "Theme A"},
                    {"id": "", "name": "Ignored"},
                    {"name": "Unnamed"},
                ],
            ),
        ):
            choices = view.themes_choices
            self.assertEqual(json.loads(view.themes_choices_json), choices)

        self.assertEqual(
            choices,
            [
                {"value": "", "text": "No theme"},
                {"value": "theme-a", "text": "Theme A"},
            ],
        )

    def test_save_theme_denies_without_permission(self) -> None:
        view = self._view(SurveyEditor)
        view.request.form = {"theme_id": "theme-a"}

        with patch(
            "plone.api.user.has_permission", return_value=False
        ) as has_permission:
            result = view._save_theme()

        has_permission.assert_called_once()
        self.assertEqual(
            json.loads(result), {"success": False, "error": "Permission denied"}
        )
        view.request.response.setStatus.assert_called_once_with(403)
        view.request.response.setHeader.assert_not_called()
        view.context.reindexObject.assert_not_called()

    def test_get_theme_json_without_site_or_with_broken_service(self) -> None:
        view = self._view(SurveyEditor)
        view.request.get.return_value = "theme-a"

        with patch.object(survey_editor_module, "getSite", return_value=None):
            self.assertEqual(json.loads(view._get_theme_json()), {})

        with (
            patch.object(survey_editor_module, "getSite", return_value=self.portal),
            patch.object(
                survey_editor_module.themes_service,
                "get_theme",
                side_effect=RuntimeError("boom"),
            ),
        ):
            self.assertEqual(json.loads(view._get_theme_json()), {})
