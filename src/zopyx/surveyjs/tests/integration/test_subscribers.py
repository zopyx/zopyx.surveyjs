from __future__ import annotations

import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch

from BTrees.OOBTree import OOBTree
from plone import api
from plone.app.testing import TEST_USER_ID, setRoles
from plone.registry.interfaces import IRegistry
from zope.annotation.interfaces import IAnnotations
from zope.component import getUtility

from zopyx.surveyjs import subscribers
from zopyx.surveyjs.constants import FORM_VERSIONS_KEY
from zopyx.surveyjs.interfaces import IFormsSettings
from zopyx.surveyjs.testing import ZOPYX_SURVEYJS_INTEGRATION_TESTING


class DummyEvent:
    def __init__(self, form_data: dict) -> None:
        self.form_data = form_data


class SubscribersIntegrationTests(unittest.TestCase):
    layer = ZOPYX_SURVEYJS_INTEGRATION_TESTING

    def setUp(self) -> None:
        self.portal = self.layer["portal"]
        setRoles(self.portal, TEST_USER_ID, ["Manager"])
        self.survey = api.content.create(
            container=self.portal,
            type="Survey",
            id="survey-subscribers",
            title="Survey Subscribers",
        )
        annos = IAnnotations(self.survey)
        annos[FORM_VERSIONS_KEY] = OOBTree()

    def _add_form_version(
        self, version_id: str, created: datetime, payload: dict
    ) -> None:
        annos = IAnnotations(self.survey)
        annos[FORM_VERSIONS_KEY][version_id] = {
            "id": version_id,
            "created": created,
            "form_json": payload,
        }

    def test_latest_form_json_picks_most_recent(self) -> None:
        self._add_form_version(
            "v1", datetime(2024, 1, 1, tzinfo=timezone.utc), {"a": 1}
        )
        self._add_form_version(
            "v2", datetime(2024, 2, 1, tzinfo=timezone.utc), {"b": 2}
        )
        annos = IAnnotations(self.survey)
        latest = subscribers._latest_form_json(annos)
        self.assertEqual(latest, {"b": 2})

    def test_send_submission_email_renders_exports_and_sends(self) -> None:
        self.survey.actions = {"mail"}
        self.survey.email_to = "recipient@example.com"
        self.survey.email_subject = "Subject {poll_id}"
        self.survey.email_body = "Body {creator} {formats}"
        self.survey.email_formats = {"md", "json"}
        self._add_form_version(
            "v1", datetime(2024, 1, 1, tzinfo=timezone.utc), {"pages": []}
        )
        event = DummyEvent(
            {
                "poll_id": "poll-1",
                "result": {"q1": "yes"},
                "user": "tester",
                "created": datetime(2024, 1, 1, tzinfo=timezone.utc),
            }
        )

        def fake_export(format_key, poll_id, *_args, **_kwargs):
            return Path(f"/tmp/{poll_id}.{format_key}")

        with (
            patch("zopyx.surveyjs.subscribers.SurveyConverter") as converter_cls,
            patch(
                "zopyx.surveyjs.subscribers._write_export", side_effect=fake_export
            ) as writer,
        ):
            converter = converter_cls.return_value
            converter.collect_items.return_value = (["item"], [])
            converter.save_attachments.return_value = []

            subscribers.send_submission_email(self.survey, event)

            format_calls = [call.args[0] for call in writer.call_args_list]
            self.assertIn("pdf", format_calls)
            self.assertIn("json", format_calls)
            self.assertNotIn("md", format_calls)
            converter.send_email_mailhost.assert_called_once()
            call_kwargs = converter.send_email_mailhost.call_args.kwargs
            self.assertIn("poll-1", call_kwargs["subject"])
            self.assertIn("tester", call_kwargs["body"])

    def test_send_submission_notification_dispatches_mailhost_message(self) -> None:
        self.survey.actions = {"mail-notification"}
        self.survey.email_to = "notify@example.com"
        self.survey.email_notification_subject = "Form submitted {poll_id}"
        self.survey.email_notification_body = "Details {detail_url}"
        event = DummyEvent({"poll_id": "poll-99"})

        mailhost = MagicMock()
        with (
            patch("plone.api.portal.get", return_value=self.portal),
            patch("plone.api.portal.get_tool", return_value=mailhost),
            patch(
                "zopyx.surveyjs.converters.cli.SurveyConverter._normalize_recipients",
                return_value=["notify@example.com"],
            ),
        ):
            subscribers.send_submission_notification(self.survey, event)

        mailhost.send.assert_called_once()
        send_kwargs = mailhost.send.call_args.kwargs
        self.assertIn("poll-99", send_kwargs["subject"])
        self.assertEqual(send_kwargs["mto"], ["notify@example.com"])

    def test_post_submission_payload_sends_payload(self) -> None:
        self.survey.actions = {"post"}
        self.survey.post_endpoint_url = "https://example.com/post"
        self._add_form_version(
            "v1", datetime(2024, 1, 1, tzinfo=timezone.utc), {"pages": []}
        )
        event = DummyEvent(
            {
                "poll_id": "poll-42",
                "created": datetime(2024, 1, 1, tzinfo=timezone.utc),
                "result": {"q1": "yes"},
            }
        )

        response = MagicMock()
        response.raise_for_status.return_value = None
        response.status_code = 200
        with patch(
            "zopyx.surveyjs.subscribers.httpx.post", return_value=response
        ) as post:
            subscribers.post_submission_payload(self.survey, event)

        payload = post.call_args.kwargs["json"]
        self.assertEqual(payload["poll"]["poll_id"], "poll-42")
        self.assertEqual(payload["form"], {"pages": []})
        self.assertEqual(payload["survey_url"], self.survey.absolute_url())

    def test_store_submission_result_records_metadata(self) -> None:
        self.survey.actions = {"store"}
        self._add_form_version(
            "v1", datetime(2024, 1, 1, tzinfo=timezone.utc), {"pages": []}
        )
        event = DummyEvent({"result": {"q1": "yes"}})

        registry = getUtility(IRegistry)
        settings = registry.forInterface(IFormsSettings, check=False)
        original_ip = settings.log_ip_addresses
        original_user_agent = settings.log_user_agent
        settings.log_ip_addresses = True
        settings.log_user_agent = True

        class DummyRequest:
            def getClientAddr(self):
                return "1.2.3.4"

            def getHeader(self, _name):
                return "agent/1.0"

        storage = MagicMock()
        try:
            with (
                patch(
                    "zopyx.surveyjs.subscribers.getRequest", return_value=DummyRequest()
                ),
                patch(
                    "zopyx.surveyjs.subscribers.get_result_storage",
                    return_value=storage,
                ),
            ):
                subscribers.store_submission_result(self.survey, event)
        finally:
            settings.log_ip_addresses = original_ip
            settings.log_user_agent = original_user_agent

        stored_payload = storage.store_result.call_args.args[1]
        self.assertEqual(stored_payload["ip_address"], "1.2.3.4")
        self.assertEqual(stored_payload["user_agent"], "agent/1.0")
        self.assertEqual(stored_payload["seq_no"], 1)
