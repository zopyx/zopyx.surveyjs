"""Initialize a demo Plone site with zopyx.surveyjs installed."""
import plone.api
from plone.app.theming.browser.controlpanel import ThemingControlpanel
from plone.app.textfield.value import RichTextValue
from AccessControl.SecurityManagement import newSecurityManager
from BTrees.OOBTree import OOBTree
from Products.CMFPlone.factory import addPloneSite
from Testing.makerequest import makerequest
from datetime import datetime, timezone
from plone import api
from zopyx.surveyjs.browser.views import FORM_VERSIONS_KEY
from zope.annotation.interfaces import IAnnotations
from zope.component.hooks import setSite
import transaction
import uuid


SITE_ID = "demo"
ADMIN = "admin"

class MyThemingControlpanel(ThemingControlpanel):
    """
    A subclass of the standard ThemingControlpanel to override authorization.
    This allows the script to programmatically change theme settings without
    requiring the usual browser-based authentication and permissions.
    """

    def authorize(self):
        # Always return True to allow theme modifications.
        return True



acl = app.acl_users
admin_user = acl.getUser(ADMIN)
newSecurityManager(None, admin_user.__of__(acl))

if SITE_ID in app.objectIds():
    app.manage_delObjects([SITE_ID])
    transaction.commit()

addPloneSite(
    app,
    SITE_ID,
    distribution="classic",
    extension_ids=["plone.app.contenttypes:default"],
)
site = makerequest(app[SITE_ID])
setSite(site)
api.addon.install("zopyx.surveyjs")


print("Enabling Barceloneta theme...")
site.REQUEST.form["form.button.Enable"] = "DONE"
site.REQUEST.form["themeName"] = "barceloneta"
view = MyThemingControlpanel(site, site.REQUEST)
view.update()


transaction.commit()

site._p_jar.sync()



for obj_id in ("events", "news", "Members"):
    if obj_id in site.objectIds():
        site.manage_delObjects([obj_id])

survey = api.content.create(
    type="Survey",
    container=site,
    title="Event registration",
    id="event-registration",
)
survey.reindexObject()
api.content.transition(obj=survey, transition="publish")

annos = IAnnotations(survey)
annos.setdefault(FORM_VERSIONS_KEY, OOBTree())
version_id = str(uuid.uuid4())
annos[FORM_VERSIONS_KEY][version_id] = dict(
    id=version_id,
    created=datetime.now(timezone.utc),
    user=ADMIN,
    form_json={
        "title": "Event registration",
        "description": "Register for the event.",
        "showQuestionNumbers": "off",
        "completedHtml": "<h3>Thank you for registering!</h3>",
        "pages": [
            {
                "name": "attendee",
                "elements": [
                    {
                        "type": "text",
                        "name": "fullName",
                        "title": "Full name",
                        "isRequired": True,
                    },
                    {
                        "type": "text",
                        "name": "email",
                        "title": "Email",
                        "inputType": "email",
                        "isRequired": True,
                    },
                    {
                        "type": "dropdown",
                        "name": "ticketType",
                        "title": "Ticket type",
                        "isRequired": True,
                        "choices": [
                            "Standard",
                            "Student",
                            "VIP",
                        ],
                    },
                    {
                        "type": "boolean",
                        "name": "newsletter",
                        "title": "Keep me updated about future events",
                        "labelTrue": "Yes",
                        "labelFalse": "No",
                    },
                ],
            }
        ],
    },
)

welcome = api.content.create(
    type="Document",
    container=site,
    title="Welcome",
    id="welcome",
    text=RichTextValue(
        "<p>Welcome to the demo site. Use the Event registration form to collect responses and explore the results views.</p>",
        "text/html",
        "text/html",
    ),
)
api.content.transition(obj=welcome, transition="publish")
welcome.reindexObject()

transaction.commit()
