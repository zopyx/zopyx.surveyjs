import json
import uuid
from datetime import datetime
from Products.Five import BrowserView

from zope.annotation.interfaces import IAnnotations
from BTrees.OOBTree import OOBTree

KEY = "zopyx.surveyjs.results"


class Views(BrowserView):

    def get_form_json(self):
        """ JSON for SurveyJS renderer """

        json_form = self.context.form_json

        # verify JSON validity
        data = json.loads(json_form)

        self.request.response.setHeader("content-type", "application/json")
        self.request.response.write(json_form.encode("utf8"))

    def save_form_json(self):
        json_form = self.request.form["surveyText"]
        self.context.form_json = json_form

        result = dict(isSuccess=True)
        self.request.response.setStatus(200)
        self.request.response.setHeader("content-type", "application/json")
        self.request.response.write(json.dumps(result).encode("utf8"))

    def save_poll(self):

        poll_result = self.request.form

        annos = IAnnotations(self.context)
        if KEY not in annos:
            annos[KEY] = OOBTree()

        data = dict(
                poll_id=str(uuid.uuid4()),
                created=datetime.utcnow(),
                result=self.request.form)

        annos[KEY][data["poll_id"]] = data

        result = dict(isSuccess=True)
        self.request.response.setStatus(200)
        self.request.response.setHeader("content-type", "application/json")
        self.request.response.write(json.dumps(result).encode("utf8"))
