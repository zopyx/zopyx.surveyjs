"""Tests for the Plone site distribution shipped with this add-on.

The layer creates two sites from the same distribution: one with example
content (the demo profile) and one without, so both branches of
``profiles.json`` are covered.
"""

import unittest

from plone import api
from plone.app.testing import IntegrationTesting
from plone.app.testing.interfaces import PLONE_SITE_ID
from plone.distribution.api import distribution as dist_api
from plone.distribution.testing.layer import PloneDistributionFixture
from zope.annotation.interfaces import IAnnotations

from zopyx.surveyjs.constants import THEMES_KEY
from zopyx.surveyjs.demo_profile import DEFAULT_THEMES, DEMO_FOLDER_ID, DEMO_FORMS

DISTRIBUTION_NAME = "surveyjs"
# The primary site must use the framework site id: IntegrationTesting resolves
# the ``portal`` resource as ``app[PLONE_SITE_ID]``.
SITE_WITH_CONTENT = PLONE_SITE_ID
SITE_WITHOUT_CONTENT = "surveyjs-plain"

ANSWERS = {
    "site_id": SITE_WITH_CONTENT,
    "title": "Privacy Forms Studio",
    "description": "SurveyJS demo site",
    "default_language": "en",
    "portal_timezone": "Europe/Berlin",
    "setup_content": True,
}

ANSWERS_WITHOUT_CONTENT = dict(
    ANSWERS,
    site_id=SITE_WITHOUT_CONTENT,
    title="Privacy Forms Studio (no example content)",
    setup_content=False,
)


class BaseFixture(PloneDistributionFixture):
    PACKAGE_NAME = "zopyx.surveyjs"
    SITES = (
        (DISTRIBUTION_NAME, ANSWERS),
        (DISTRIBUTION_NAME, ANSWERS_WITHOUT_CONTENT),
    )
    _distribution_products = (
        ("plone.app.contenttypes", {"loadZCML": True}),
        ("plone.restapi", {"loadZCML": True}),
        ("plone.distribution", {"loadZCML": True}),
    )


BASE_FIXTURE = BaseFixture()


DISTRIBUTION_INTEGRATION_TESTING = IntegrationTesting(
    bases=(BASE_FIXTURE,),
    name="ZopyxSurveyjsDistribution:IntegrationTesting",
)


class TestDistributionRegistration(unittest.TestCase):
    """The distribution is registered and describes itself correctly."""

    layer = DISTRIBUTION_INTEGRATION_TESTING

    def setUp(self):
        self.distribution = dist_api.get(DISTRIBUTION_NAME)

    def test_registered(self):
        names = [dist.name for dist in dist_api.get_distributions(filter=False)]
        self.assertIn(DISTRIBUTION_NAME, names)
        self.assertIn("Privacy Forms Studio", str(self.distribution.title))
        self.assertIn("SurveyJS", str(self.distribution.description))

    def test_is_not_headless(self):
        """A Classic UI distribution renders its own pages."""
        self.assertFalse(self.distribution.headless)

    def test_base_and_content_profiles(self):
        self.assertEqual(
            self.distribution.profiles,
            [
                "plone.app.contenttypes:default",
                "plone.app.layout:default",
                "plonetheme.barceloneta:default",
                "zopyx.surveyjs:default",
            ],
        )
        self.assertEqual(
            self.distribution.contents["profiles"], ["zopyx.surveyjs:demo"]
        )
        # No JSON content export is shipped; the demo profile creates content.
        self.assertIsNone(self.distribution.contents["json"])

    def test_schema_and_data_files(self):
        schema = self.distribution.schema
        self.assertIn("site_id", schema["properties"])
        self.assertIn("title", schema["properties"])
        self.assertTrue(schema["properties"]["setup_content"]["default"])
        for filename in ("profiles.json", "schema.json", "image.png"):
            self.assertTrue(
                (self.distribution.directory / filename).exists(),
                f"{filename} is missing in the distribution directory",
            )
        image = self.distribution.image
        self.assertEqual(image.name, "image.png")
        self.assertEqual(image.parent, self.distribution.directory)


class TestDistributionSite(unittest.TestCase):
    """A site created with the distribution behaves like a demo site."""

    layer = DISTRIBUTION_INTEGRATION_TESTING

    def setUp(self):
        self.site = self.layer["portal"]

    def test_creation_report(self):
        report = dist_api.get_creation_report(self.site)
        self.assertIsNotNone(report)
        self.assertEqual(report.name, DISTRIBUTION_NAME)
        self.assertTrue(report.answers["setup_content"])

    def test_current_distribution(self):
        self.assertEqual(
            dist_api.get_current_distribution(self.site).name, DISTRIBUTION_NAME
        )

    def test_addon_installed_and_types_available(self):
        setup_tool = self.site.portal_setup
        self.assertTrue(setup_tool.profileExists("zopyx.surveyjs:default"))
        self.assertNotEqual(
            setup_tool.getLastVersionForProfile("zopyx.surveyjs:default"), "unknown"
        )
        self.assertIn("Survey", self.site.portal_types.objectIds())

    def test_demo_forms_created_by_the_content_profile(self):
        folder = self.site.get(DEMO_FOLDER_ID)
        self.assertIsNotNone(folder)
        self.assertEqual(api.content.get_state(folder), "published")
        surveys = {
            obj.id: obj for obj in folder.objectValues() if obj.portal_type == "Survey"
        }
        self.assertEqual(set(surveys), {spec.id for spec in DEMO_FORMS})
        for survey in surveys.values():
            self.assertEqual(api.content.get_state(survey), "published")
            self.assertEqual(survey.language, "en")

    def test_demo_themes_seeded_with_distinct_selection(self):
        themes = IAnnotations(self.site).get(THEMES_KEY, {})
        by_id = {theme["id"]: theme["name"] for theme in themes.values()}
        self.assertEqual(set(by_id.values()), {theme.name for theme in DEFAULT_THEMES})
        folder = self.site.get(DEMO_FOLDER_ID)
        assigned = {folder[spec.id].theme for spec in DEMO_FORMS}
        self.assertEqual(len(assigned), len(DEMO_FORMS))
        self.assertEqual(
            {by_id[theme_id] for theme_id in assigned},
            {spec.theme for spec in DEMO_FORMS},
        )

    def test_demo_forms_are_anonymously_viewable(self):
        folder = self.site.get(DEMO_FOLDER_ID)
        for spec in DEMO_FORMS:
            survey = folder[spec.id]
            view = survey.restrictedTraverse("@@viewer")
            self.assertIn("surveyViewerContainer", view())


class TestDistributionWithoutContent(unittest.TestCase):
    """``setup_content = false`` installs the add-on but no demo content."""

    layer = DISTRIBUTION_INTEGRATION_TESTING

    def setUp(self):
        self.site = self.layer["app"][SITE_WITHOUT_CONTENT]

    def test_addon_installed(self):
        self.assertTrue(self.site.portal_setup.profileExists("zopyx.surveyjs:default"))
        self.assertIn("Survey", self.site.portal_types.objectIds())

    def test_no_demo_content(self):
        self.assertIsNone(self.site.get(DEMO_FOLDER_ID))
        self.assertEqual(IAnnotations(self.site).get(THEMES_KEY, {}), {})
