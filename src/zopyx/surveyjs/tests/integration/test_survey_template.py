# -*- coding: utf-8 -*-
from datetime import datetime, timezone

import orjson
from BTrees.OOBTree import OOBTree
from plone import api
from plone.app.testing import setRoles, TEST_USER_ID
from zope.annotation.interfaces import IAnnotations
from zope.publisher.browser import TestRequest

from zopyx.surveyjs.browser import views
from zopyx.surveyjs.browser.survey_template_views import SurveyTemplateViewer
from zopyx.surveyjs.constants import FORM_VERSIONS_KEY
from zopyx.surveyjs.content.survey import ISurvey
from zopyx.surveyjs.content.survey_template import ISurveyTemplate
from zopyx.surveyjs.testing import ZOPYX_SURVEYJS_INTEGRATION_TESTING

import unittest


class SurveyTemplateWorkflowIntegrationTests(unittest.TestCase):
    layer = ZOPYX_SURVEYJS_INTEGRATION_TESTING

    def setUp(self):
        self.portal = self.layer["portal"]
        setRoles(self.portal, TEST_USER_ID, ["Manager"])

    def test_create_template_from_version_copies_metadata(self):
        survey = api.content.create(
            container=self.portal,
            type="Survey",
            id="source-survey",
            title="Source Survey",
        )
        survey.actions = {"mail"}
        survey.email_subject = "Subject A"
        survey.access_mode = "trusted"
        survey.embedding_mode = "iframe"
        survey.force_server_side_validation = False

        annos = IAnnotations(survey)
        annos[FORM_VERSIONS_KEY] = OOBTree()
        version_id = "version-1"
        form_json = {"title": "Version Form", "pages": []}
        annos[FORM_VERSIONS_KEY][version_id] = {
            "id": version_id,
            "created": datetime(2024, 1, 1, tzinfo=timezone.utc),
            "user": TEST_USER_ID,
            "form_json": form_json,
        }

        req = TestRequest(form={"version_id": version_id, "template_title": "T-1"})
        view = views.Views(survey, req)
        view.create_template_from_version()

        brains = api.content.find(portal_type="SurveyTemplate", Title="T-1")
        self.assertEqual(len(brains), 1)
        template = brains[0].getObject()

        self.assertTrue(ISurveyTemplate.providedBy(template))
        self.assertTrue(ISurvey.providedBy(template))
        self.assertEqual(template.actions, survey.actions)
        self.assertEqual(template.email_subject, survey.email_subject)
        self.assertEqual(template.access_mode, survey.access_mode)
        self.assertEqual(template.embedding_mode, survey.embedding_mode)
        self.assertEqual(
            template.force_server_side_validation, survey.force_server_side_validation
        )
        self.assertEqual(orjson.loads(template.template_json), form_json)

    def test_create_survey_from_template_copies_metadata_and_form(self):
        template = api.content.create(
            container=self.portal,
            type="SurveyTemplate",
            id="template-survey",
            title="Template Survey",
            template_json='{"title": "Template Form", "pages": []}',
        )
        template.actions = {"store", "post"}
        template.email_subject = "Template Subject"
        template.access_mode = "trusted"
        template.embedding_mode = "iframe"
        template.force_server_side_validation = False

        req = TestRequest(
            form={
                "pfs_action": "create_from_template",
                "template_uid": template.UID(),
            }
        )
        req["REQUEST_METHOD"] = "POST"
        view = views.PFSView(self.portal, req)
        view()

        brains = api.content.find(portal_type="Survey", Title="Template Survey")
        self.assertEqual(len(brains), 1)
        survey = brains[0].getObject()

        self.assertEqual(survey.actions, template.actions)
        self.assertEqual(survey.email_subject, template.email_subject)
        self.assertEqual(survey.access_mode, template.access_mode)
        self.assertEqual(survey.embedding_mode, template.embedding_mode)
        self.assertEqual(
            survey.force_server_side_validation, template.force_server_side_validation
        )

        annos = IAnnotations(survey)
        form_versions = annos.get(FORM_VERSIONS_KEY, {})
        self.assertEqual(len(form_versions), 1)
        version_data = list(form_versions.values())[0]
        self.assertEqual(
            version_data["form_json"], orjson.loads(template.template_json)
        )

    def test_survey_template_viewer_get_template_json(self):
        template = api.content.create(
            container=self.portal,
            type="SurveyTemplate",
            id="template-view",
            title="Template View",
            template_json='{"title": "Viewer Template", "pages": []}',
        )
        req = TestRequest()
        view = SurveyTemplateViewer(template, req)
        view.get_template_json()

        self.assertEqual(req.response.getStatus(), 200)
        payload = orjson.loads(req.response.getBody())
        self.assertEqual(payload["title"], "Viewer Template")
