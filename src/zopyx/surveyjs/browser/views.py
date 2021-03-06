from BTrees.OOBTree import OOBTree
from datetime import datetime
from Products.Five import BrowserView
from zope.annotation.interfaces import IAnnotations

from plone.protect.interfaces import IDisableCSRFProtection
from zope.interface import alsoProvides

import orjson
import uuid
import operator


RESULTS_KEY = "zopyx.surveyjs.results"
FORM_VERSIONS_KEY = "zopyx.surveyjs.form_versions"


class Views(BrowserView):

    def get_form_json(self):
        """ JSON for SurveyJS renderer """

        json_form = self.context.form_json

        # verify JSON validity
        data = orjson.loads(json_form)

        self.request.response.setHeader("content-type", "application/json")
        self.request.response.write(json_form.encode("utf8"))

    def save_form_json(self):

        alsoProvides(self.request, IDisableCSRFProtection)

        json_form = self.request.form["surveyText"]
        current_form_json = self.context.form_json
        self.context.form_json = json_form

        annos = IAnnotations(self.context)
        if FORM_VERSIONS_KEY not in annos:
            annos[FORM_VERSIONS_KEY] = OOBTree()

        data = dict(
                id=str(uuid.uuid4()),
                created=datetime.utcnow(),
                form_json=current_form_json)

        annos[FORM_VERSIONS_KEY][data["id"]] = data

        result = dict(isSuccess=True)
        self.request.response.setStatus(200)
        self.request.response.setHeader("content-type", "application/json")
        self.request.response.write(orjson.dumps(result))

    def save_poll(self):
        alsoProvides(self.request, IDisableCSRFProtection)

        poll_result = self.request.form

        annos = IAnnotations(self.context)
        if RESULTS_KEY not in annos:
            annos[RESULTS_KEY] = OOBTree()

        data = dict(
                poll_id=str(uuid.uuid1()),
                created=datetime.utcnow(),
                result=self.request.form.copy())

        annos[RESULTS_KEY][data["poll_id"]] = data

        result = dict(isSuccess=True)
        self.request.response.setStatus(200)
        self.request.response.setHeader("content-type", "application/json")
        self.request.response.write(orjson.dumps(result))

    def get_polls_json(self):
        """ get polls """

        annos = IAnnotations(self.context)
        results = list(annos[RESULTS_KEY].values())
        results = sorted(results, key=operator.itemgetter("created"), reverse=True)

        self.request.response.setHeader("content-type", "application/json")
        self.request.response.write(orjson.dumps(results))
