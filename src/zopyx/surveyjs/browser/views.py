import json
from Products.Five import BrowserView


class Views(BrowserView):

    def get_form_json(self):

        json_form = self.context.form_json
        data = json.loads(json_form)

        self.request.response.setHeader("content-type", "application/json")
        self.request.response.write(json_form.encode("utf8"))
