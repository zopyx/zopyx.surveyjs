from BTrees.OOBTree import OOBTree
from datetime import datetime, timezone
from Products.Five import BrowserView
from zope.annotation.interfaces import IAnnotations
import plone.api

from .. import _

import orjson
import uuid
import operator


RESULTS_KEY = "zopyx.surveyjs.results"
FORM_VERSIONS_KEY = "zopyx.surveyjs.form_versions"


def ensure_timezone_aware(dt):
    """Convert naive datetime to UTC-aware datetime"""
    if dt.tzinfo is None or dt.tzinfo.utcoffset(dt) is None:
        # Naive datetime - assume it's UTC
        return dt.replace(tzinfo=timezone.utc)
    return dt


class Views(BrowserView):

    def get_form_json(self):
        """ JSON for SurveyJS renderer """

        annos = IAnnotations(self.context)

        # Initialize if doesn't exist
        if FORM_VERSIONS_KEY not in annos:
            annos[FORM_VERSIONS_KEY] = OOBTree()

        form_versions = [d for d in annos[FORM_VERSIONS_KEY].values()]
        form_versions = sorted(form_versions, key=lambda x: ensure_timezone_aware(x["created"]))

        form_data = {}
        if form_versions:
            form_data = form_versions[-1]["form_json"]

        self.request.response.setHeader("content-type", "application/json")
        self.request.response.write(orjson.dumps(form_data))

    def save_form_json(self):

        json_form = orjson.loads(self.request.form["surveyText"])

        annos = IAnnotations(self.context)
        if FORM_VERSIONS_KEY not in annos:
            annos[FORM_VERSIONS_KEY] = OOBTree()

        data = dict(
                id=str(uuid.uuid4()),
                created=datetime.now(timezone.utc),
                user=plone.api.user.get_current().getId(),
                form_json=json_form)

        annos[FORM_VERSIONS_KEY][data["id"]] = data

        result = dict(isSuccess=True)
        self.request.response.setStatus(200)
        self.request.response.setHeader("content-type", "application/json")
        self.request.response.write(orjson.dumps(result))

    def save_poll(self):
        poll_result = orjson.loads(self.request.form["pollResult"])

        annos = IAnnotations(self.context)
        if RESULTS_KEY not in annos:
            annos[RESULTS_KEY] = OOBTree()

        data = dict(
                poll_id=str(uuid.uuid1()),
                created=datetime.now(timezone.utc),
                user=plone.api.user.get_current().getId(),
                result=poll_result,)


        annos[RESULTS_KEY][data["poll_id"]] = data

        result = dict(isSuccess=True)
        self.request.response.setStatus(200)
        self.request.response.setHeader("content-type", "application/json")
        self.request.response.write(orjson.dumps(result))


    def clear_results(self):

        annos = IAnnotations(self.context)
        annos[RESULTS_KEY] = OOBTree()

        plone.api.portal.show_message(_("Results cleared"))
        self.request.response.redirect(self.context.absolute_url() + "/view")


    def get_polls_json(self):
        """ get polls """

        annos = IAnnotations(self.context)

        # Initialize if doesn't exist
        if RESULTS_KEY not in annos:
            annos[RESULTS_KEY] = OOBTree()

        results = list(annos[RESULTS_KEY].values())
        results = sorted(results, key=lambda x: ensure_timezone_aware(x["created"]), reverse=True)

        self.request.response.setHeader("content-type", "application/json")
        self.request.response.write(orjson.dumps(results))


    def get_polls_json2(self):
        """ get polls """

        annos = IAnnotations(self.context)

        # Initialize if doesn't exist
        if RESULTS_KEY not in annos:
            annos[RESULTS_KEY] = OOBTree()

        results = list(annos[RESULTS_KEY].values())
        results = [d["result"] for d in results]

        self.request.response.setHeader("content-type", "application/json")
        self.request.response.write(orjson.dumps(results))

    def download_form_json(self):
        """Download current form JSON as attachment"""
        annos = IAnnotations(self.context)

        # Initialize if doesn't exist
        if FORM_VERSIONS_KEY not in annos:
            annos[FORM_VERSIONS_KEY] = OOBTree()

        form_versions = [d for d in annos[FORM_VERSIONS_KEY].values()]
        form_versions = sorted(form_versions, key=lambda x: ensure_timezone_aware(x["created"]))

        form_data = {}
        if form_versions:
            form_data = form_versions[-1]["form_json"]

        # Prepare download with attachment header
        filename = f"survey-form-{self.context.getId()}.json"
        json_content = orjson.dumps(form_data, option=orjson.OPT_INDENT_2)

        self.request.response.setHeader("Content-Type", "application/json")
        self.request.response.setHeader(
            "Content-Disposition",
            f'attachment; filename="{filename}"'
        )
        self.request.response.write(json_content)

    def download_polls_json(self):
        """Download poll results JSON as attachment"""
        annos = IAnnotations(self.context)

        # Initialize if doesn't exist
        if RESULTS_KEY not in annos:
            annos[RESULTS_KEY] = OOBTree()

        results = list(annos[RESULTS_KEY].values())
        results = sorted(results, key=lambda x: ensure_timezone_aware(x["created"]), reverse=True)

        # Prepare download with attachment header
        filename = f"survey-data-{self.context.getId()}.json"
        json_content = orjson.dumps(results, option=orjson.OPT_INDENT_2)

        self.request.response.setHeader("Content-Type", "application/json")
        self.request.response.setHeader(
            "Content-Disposition",
            f'attachment; filename="{filename}"'
        )
        self.request.response.write(json_content)

    @property
    def versions(self):
        """Get all form versions sorted by date (newest first)"""
        annos = IAnnotations(self.context)

        # Initialize if doesn't exist
        if FORM_VERSIONS_KEY not in annos:
            annos[FORM_VERSIONS_KEY] = OOBTree()

        # Get all versions
        form_versions = list(annos[FORM_VERSIONS_KEY].values())

        # Sort by created date, newest first
        return sorted(form_versions, key=lambda x: ensure_timezone_aware(x["created"]), reverse=True)

    @property
    def has_versions(self):
        """Check if any versions exist"""
        return len(self.versions) > 0

    def download_version(self):
        """Download a specific version as JSON file"""
        version_id = self.request.form.get('version_id')

        if not version_id:
            plone.api.portal.show_message(_("No version ID provided"), type="error")
            return self.request.response.redirect(
                self.context.absolute_url() + "/@@form-versions"
            )

        annos = IAnnotations(self.context)
        form_versions = annos.get(FORM_VERSIONS_KEY, {})

        version_data = form_versions.get(version_id)
        if not version_data:
            plone.api.portal.show_message(_("Version not found"), type="error")
            return self.request.response.redirect(
                self.context.absolute_url() + "/@@form-versions"
            )

        # Prepare download
        filename = f"survey-form-{version_id[:8]}.json"
        json_content = orjson.dumps(
            version_data['form_json'],
            option=orjson.OPT_INDENT_2
        )

        self.request.response.setHeader('Content-Type', 'application/json')
        self.request.response.setHeader(
            'Content-Disposition',
            f'attachment; filename="{filename}"'
        )
        self.request.response.write(json_content)

    def restore_version(self):
        """Restore an old version by creating a new version with old content"""
        version_id = self.request.form.get('version_id')

        if not version_id:
            plone.api.portal.show_message(_("No version ID provided"), type="error")
            return self.request.response.redirect(
                self.context.absolute_url() + "/@@form-versions"
            )

        annos = IAnnotations(self.context)
        form_versions = annos.get(FORM_VERSIONS_KEY, {})

        old_version = form_versions.get(version_id)
        if not old_version:
            plone.api.portal.show_message(_("Version not found"), type="error")
            return self.request.response.redirect(
                self.context.absolute_url() + "/@@form-versions"
            )

        # Create new version with old content (preserves history)
        new_version = dict(
            id=str(uuid.uuid4()),
            created=datetime.now(timezone.utc),
            user=plone.api.user.get_current().getId(),
            form_json=old_version['form_json']
        )

        annos[FORM_VERSIONS_KEY][new_version["id"]] = new_version

        plone.api.portal.show_message(
            _("Version restored successfully. A new version has been created."),
            type="info"
        )
        return self.request.response.redirect(
            self.context.absolute_url() + "/@@form-versions"
        )

    def upload_version(self):
        """Upload a JSON file and save as new version"""
        uploaded_file = self.request.form.get('json_file')

        if not uploaded_file:
            plone.api.portal.show_message(_("No file uploaded"), type="error")
            return self.request.response.redirect(
                self.context.absolute_url() + "/@@form-versions"
            )

        try:
            # Read file content
            file_content = uploaded_file.read()
            if isinstance(file_content, bytes):
                file_content = file_content.decode('utf-8')

            # Parse and validate JSON
            json_data = orjson.loads(file_content)

            # Basic SurveyJS validation - check for required fields
            if not isinstance(json_data, dict):
                raise ValueError("JSON must be an object")

            # Optional: Add more specific SurveyJS structure validation
            # For now, basic validation that it's a dict is sufficient

        except (orjson.JSONDecodeError, ValueError) as e:
            plone.api.portal.show_message(
                _("Invalid JSON file: ${error}", mapping={'error': str(e)}),
                type="error"
            )
            return self.request.response.redirect(
                self.context.absolute_url() + "/@@form-versions"
            )

        # Save as new version
        annos = IAnnotations(self.context)
        if FORM_VERSIONS_KEY not in annos:
            annos[FORM_VERSIONS_KEY] = OOBTree()

        new_version = dict(
            id=str(uuid.uuid4()),
            created=datetime.now(timezone.utc),
            user=plone.api.user.get_current().getId(),
            form_json=json_data
        )

        annos[FORM_VERSIONS_KEY][new_version["id"]] = new_version

        plone.api.portal.show_message(
            _("JSON uploaded successfully as new version"),
            type="info"
        )
        return self.request.response.redirect(
            self.context.absolute_url() + "/@@form-versions"
        )

    def view_version_json(self):
        """Return JSON for a specific version for viewing"""
        version_id = self.request.form.get('version_id')

        annos = IAnnotations(self.context)
        form_versions = annos.get(FORM_VERSIONS_KEY, {})

        version_data = form_versions.get(version_id)
        if not version_data:
            result = {"error": "Version not found"}
        else:
            result = version_data['form_json']

        self.request.response.setHeader("content-type", "application/json")
        self.request.response.write(orjson.dumps(result, option=orjson.OPT_INDENT_2))

    @property
    def results(self):
        """Get all poll results sorted by creation date (newest first)"""
        annos = IAnnotations(self.context)

        # Initialize if doesn't exist
        if RESULTS_KEY not in annos:
            annos[RESULTS_KEY] = OOBTree()

        # Get all results
        results = list(annos[RESULTS_KEY].values())

        # Sort by created date, newest first
        return sorted(results, key=lambda x: ensure_timezone_aware(x["created"]), reverse=True)

    def get_paginated_results(self):
        """Return paginated results"""
        b_start = int(self.request.form.get("b_start", 0))
        pagesize = 10
        results = self.results
        total = len(results)
        numpages = total // pagesize
        if total % pagesize > 0:
            numpages += 1
        page = b_start // pagesize + 1
        return dict(
            items=results[b_start : b_start + pagesize],
            total=total,
            numpages=numpages,
            page=page,
            pagesize=pagesize,
        )

    def view_result_json(self):
        """Return JSON for a specific poll result for viewing"""
        poll_id = self.request.form.get('poll_id')

        annos = IAnnotations(self.context)
        results = annos.get(RESULTS_KEY, {})

        result_data = results.get(poll_id)
        if not result_data:
            result = {"error": "Poll result not found"}
        else:
            result = result_data['result']

        self.request.response.setHeader("content-type", "application/json")
        self.request.response.write(orjson.dumps(result, option=orjson.OPT_INDENT_2))

    @property
    def plone_api(self):
        return plone.api
