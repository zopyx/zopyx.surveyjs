"""Tests for the optional ``zopyx.surveyjs:demo`` GenericSetup profile."""

import unittest
from pathlib import Path

from plone import api
from plone.app.testing import TEST_USER_ID, applyProfile, setRoles
from zope.annotation.interfaces import IAnnotations

from zopyx.surveyjs.constants import FORM_VERSIONS_KEY, RESULTS_KEY, THEMES_KEY
from zopyx.surveyjs.demo_profile import (
    DEFAULT_THEMES,
    DEMO_FOLDER_ID,
    DEMO_FOLDER_TITLE,
    DEMO_FORMS,
    FORMS_PATH,
    THEMES_PATH,
    _load_json,
)
from zopyx.surveyjs.testing import ZOPYX_SURVEYJS_DEMO_INTEGRATION_TESTING

# scripts/themes/ is not part of the package (it feeds scripts/init_plone.py);
# this path only exists in a source checkout.
SCRIPT_THEMES_PATH = Path(__file__).resolve().parents[4] / "scripts" / "themes"

QUESTION_TYPES = {
    "boolean",
    "checkbox",
    "comment",
    "dropdown",
    "expression",
    "file",
    "imagepicker",
    "matrix",
    "matrixdropdown",
    "matrixdynamic",
    "paneldynamic",
    "radiogroup",
    "ranking",
    "rating",
    "signaturepad",
    "tagbox",
    "text",
}


def count_questions(elements):
    """Recursively count question elements (panels and HTML are not counted)."""
    total = 0
    for element in elements or []:
        element_type = element.get("type")
        if element_type in QUESTION_TYPES:
            total += 1
        if element_type == "panel":
            total += count_questions(element.get("elements"))
    return total


class TestDemoProfile(unittest.TestCase):
    """The demo profile seeds themes plus a demo-forms folder."""

    layer = ZOPYX_SURVEYJS_DEMO_INTEGRATION_TESTING

    def setUp(self):
        self.portal = self.layer["portal"]
        setRoles(self.portal, TEST_USER_ID, ["Manager"])

    # -- helpers ---------------------------------------------------------

    def themes(self):
        return IAnnotations(self.portal).get(THEMES_KEY, {})

    def themes_by_name(self):
        return {theme["name"]: theme for theme in self.themes().values()}

    def folder(self):
        return self.portal.get(DEMO_FOLDER_ID)

    def survey(self, survey_id):
        return self.folder().get(survey_id)

    def versions(self, survey):
        return IAnnotations(survey).get(FORM_VERSIONS_KEY)

    def newest_form_json(self, survey):
        versions = self.versions(survey)
        self.assertTrue(versions, "survey has no stored form version")
        newest = max(versions.values(), key=lambda version: version["created"])
        return newest["form_json"]

    def demo_surveys(self):
        folder = self.folder()
        return {
            obj.id: obj for obj in folder.objectValues() if obj.portal_type == "Survey"
        }

    # -- tests -----------------------------------------------------------

    def test_profile_is_registered(self):
        self.assertTrue(self.portal.portal_setup.profileExists("zopyx.surveyjs:demo"))

    def test_demo_themes_seeded(self):
        by_name = self.themes_by_name()
        self.assertEqual(set(by_name), {theme.name for theme in DEFAULT_THEMES})
        self.assertEqual(by_name["light"]["theme_json"]["colorPalette"], "light")
        self.assertEqual(by_name["dark"]["theme_json"]["colorPalette"], "dark")
        self.assertFalse(by_name["light"]["theme_json"].get("isPanelless", False))
        self.assertTrue(by_name["light-no-panels"]["theme_json"]["isPanelless"])
        self.assertTrue(by_name["dark-no-panels"]["theme_json"]["isPanelless"])
        for theme in self.themes().values():
            self.assertTrue(theme["versions"], "theme has no stored version")

    def test_demo_folder_is_published(self):
        folder = self.folder()
        self.assertIsNotNone(folder)
        self.assertEqual(folder.title, DEMO_FOLDER_TITLE)
        self.assertEqual(api.content.get_state(folder), "published")

    def test_three_demo_forms_created(self):
        surveys = self.demo_surveys()
        self.assertEqual(set(surveys), {spec.id for spec in DEMO_FORMS})
        for spec in DEMO_FORMS:
            survey = surveys[spec.id]
            self.assertEqual(api.content.get_state(survey), "published")
            self.assertEqual(survey.title, spec.title)
            self.assertEqual(survey.language, "en")
            self.assertEqual(set(survey.actions), {"store"})
            self.assertIsNotNone(IAnnotations(survey).get(RESULTS_KEY))
            form_json = self.newest_form_json(survey)
            self.assertTrue(form_json["pages"])

    def test_each_form_uses_a_different_theme(self):
        themes_by_id = {theme["id"]: theme["name"] for theme in self.themes().values()}
        assigned = {}
        for spec in DEMO_FORMS:
            theme_id = self.survey(spec.id).theme
            self.assertTrue(theme_id, f"survey {spec.id} has no theme")
            self.assertIn(theme_id, themes_by_id)
            assigned[spec.id] = themes_by_id[theme_id]
        self.assertEqual(len(set(assigned.values())), len(DEMO_FORMS))
        for spec in DEMO_FORMS:
            self.assertEqual(assigned[spec.id], spec.theme)

    def test_shipped_form_definitions_are_complex_and_english(self):
        for spec in DEMO_FORMS:
            form_json = _load_json(FORMS_PATH / spec.form_file)
            self.assertEqual(form_json.get("locale"), "en")
            self.assertGreaterEqual(
                len(form_json["pages"]), 5, f"{spec.id}: too few pages"
            )
            questions = 0
            for page in form_json["pages"]:
                questions += count_questions(page.get("elements"))
            self.assertGreaterEqual(questions, 20, f"{spec.id}: too few questions")

    def test_shipped_form_definitions_are_the_stored_versions(self):
        for spec in DEMO_FORMS:
            stored = self.newest_form_json(self.survey(spec.id))
            self.assertEqual(stored, _load_json(FORMS_PATH / spec.form_file))

    def test_each_form_renders_with_its_theme(self):
        by_name = self.themes_by_name()
        for spec in DEMO_FORMS:
            view = self.survey(spec.id).restrictedTraverse("@@viewer")
            self.assertEqual(
                view.survey_theme_json,
                by_name[spec.theme]["theme_json"],
                f"{spec.id}: viewer does not use the '{spec.theme}' theme",
            )
            self.assertIn("surveyViewerContainer", view())

    def test_theme_seeds_match_the_init_script_copies(self):
        """scripts/themes (init_plone.py) must not drift from the profile."""
        if not SCRIPT_THEMES_PATH.exists():
            self.skipTest("scripts/themes is not part of the package")
        for theme in DEFAULT_THEMES:
            name = f"{theme.seed_file}.json"
            self.assertEqual(
                _load_json(THEMES_PATH / name),
                _load_json(SCRIPT_THEMES_PATH / name),
                f"{name}: profile seed differs from the init_plone.py seed",
            )

    def test_reapplying_the_profile_is_idempotent(self):
        theme_count = len(self.themes())
        version_counts = {
            spec.id: len(self.versions(self.survey(spec.id))) for spec in DEMO_FORMS
        }

        applyProfile(self.portal, "zopyx.surveyjs:demo")

        self.assertEqual(len(self.themes()), theme_count)
        self.assertEqual(len(self.demo_surveys()), len(DEMO_FORMS))
        for spec in DEMO_FORMS:
            self.assertEqual(
                len(self.versions(self.survey(spec.id))),
                version_counts[spec.id],
                f"{spec.id}: re-import added a duplicate form version",
            )

    def test_reimport_updates_an_outdated_form_version(self):
        """A changed definition is stored as a new version - and only once."""
        survey = self.survey("employee-onboarding")
        versions = self.versions(survey)
        newest = max(versions.values(), key=lambda version: version["created"])
        newest["form_json"] = {"title": "Outdated", "pages": []}
        before = len(versions)

        applyProfile(self.portal, "zopyx.surveyjs:demo")

        survey = self.survey("employee-onboarding")
        self.assertEqual(len(self.versions(survey)), before + 1)
        self.assertTrue(self.newest_form_json(survey)["pages"])
