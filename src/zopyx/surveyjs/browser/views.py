from BTrees.OOBTree import OOBTree
from datetime import datetime
from Products.Five import BrowserView
from zope.annotation.interfaces import IAnnotations
import plone.api

from plone.protect.interfaces import IDisableCSRFProtection
from zope.interface import alsoProvides

from .. import _

import orjson
import uuid
import operator


RESULTS_KEY = "zopyx.surveyjs.results"
FORM_VERSIONS_KEY = "zopyx.surveyjs.form_versions"


class Views(BrowserView):

    def get_form_json(self):
        """ JSON for SurveyJS renderer """

        annos = IAnnotations(self.context)
        form_versions = [d for d in annos[FORM_VERSIONS_KEY].values()]
        form_versions = sorted(form_versions, key=lambda x: x["created"])

        form_data = {}
        if form_versions:
            form_data = form_versions[-1]["form_json"]

        self.request.response.setHeader("content-type", "application/json")
        self.request.response.write(orjson.dumps(form_data))

    def save_form_json(self):

        alsoProvides(self.request, IDisableCSRFProtection)

        json_form = orjson.loads(self.request.form["surveyText"])

        annos = IAnnotations(self.context)
        if FORM_VERSIONS_KEY not in annos:
            annos[FORM_VERSIONS_KEY] = OOBTree()

        data = dict(
                id=str(uuid.uuid4()),
                created=datetime.utcnow(),
                user=plone.api.user.get_current().getId(),
                form_json=json_form)

        annos[FORM_VERSIONS_KEY][data["id"]] = data

        result = dict(isSuccess=True)
        self.request.response.setStatus(200)
        self.request.response.setHeader("content-type", "application/json")
        self.request.response.write(orjson.dumps(result))

    def save_poll(self):
        alsoProvides(self.request, IDisableCSRFProtection)

        poll_result = orjson.loads(self.request.form["pollResult"])

        annos = IAnnotations(self.context)
        if RESULTS_KEY not in annos:
            annos[RESULTS_KEY] = OOBTree()

        data = dict(
                poll_id=str(uuid.uuid1()),
                created=datetime.utcnow(),
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
        results = list(annos[RESULTS_KEY].values())
        results = sorted(results, key=operator.itemgetter("created"), reverse=True)

        self.request.response.setHeader("content-type", "application/json")
        self.request.response.write(orjson.dumps(results))
    

    def get_polls_json2(self):
        """ get polls """

        annos = IAnnotations(self.context)
        results = list(annos[RESULTS_KEY].values())
        results = [d["result"] for d in results]

        self.request.response.setHeader("content-type", "application/json")
        self.request.response.write(orjson.dumps(results))
