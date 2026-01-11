"""Initialize a demo Plone site with zopyx.surveyjs installed."""

from AccessControl.SecurityManagement import newSecurityManager
from BTrees.OOBTree import OOBTree
from plone.app.textfield.value import RichTextValue
from plone.app.theming.browser.controlpanel import ThemingControlpanel
from Products.CMFPlone.factory import addPloneSite
from datetime import datetime, timezone
from Testing.makerequest import makerequest
from plone import api
from zopyx.surveyjs.browser.views import FORM_VERSIONS_KEY, RESULTS_KEY
from zope.annotation.interfaces import IAnnotations
from zope.component.hooks import setSite
import transaction
import uuid


SITE_ID = "demo"
ADMIN = "admin"


def create_demo_survey(
    site,
    survey_id,
    title,
    description,
    form_json,
    intro_html=None,
    actions=None,
):
    survey = api.content.create(
        type="Survey",
        container=site,
        title=title,
        id=survey_id,
        description=description,
        text=RichTextValue(intro_html, "text/html", "text/html") if intro_html else None,
    )
    if actions:
        survey.actions = actions
    survey.reindexObject()
    api.content.transition(obj=survey, transition="publish")

    annos = IAnnotations(survey)
    annos.setdefault(FORM_VERSIONS_KEY, OOBTree())
    annos.setdefault(RESULTS_KEY, OOBTree())

    version_id = str(uuid.uuid4())
    annos[FORM_VERSIONS_KEY][version_id] = dict(
        id=version_id,
        created=datetime.now(timezone.utc),
        user=ADMIN,
        form_json=form_json,
    )
    return survey


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

allowed_types = {"Folder", "Document", "Survey"}
portal_types = api.portal.get_tool("portal_types")
for fti in portal_types.objectValues():
    fti.global_allow = fti.getId() in allowed_types


for obj_id in ("events", "news", "Members"):
    if obj_id in site.objectIds():
        site.manage_delObjects([obj_id])

event_form = {
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
}

create_demo_survey(
    site,
    survey_id="event-registration",
    title="Event registration",
    description="Register for the event.",
    form_json=event_form,
)

welcome = api.content.create(
    type="Document",
    container=site,
    title="Welcome",
    id="welcome",
    text=RichTextValue(
        """
<h2>Privacy Forms Studio</h2>
<p>Build, publish, and export forms or surveys with SurveyJS creator, viewer, and results.</p>
<p>Privacy Form Studio adds a dedicated Survey content type to your Plone site, powered by SurveyJS. Keep data on-premise or in your own SaaS stack with no required cloud integrations or external services.</p>
<ul>
  <li>Visual SurveyJS creator with live preview and localization.</li>
  <li>Embed the responsive survey viewer across your site.</li>
  <li>Optional AI assistant for form drafting (keep it off for fully local workflows).</li>
  <li>Results dashboard for managing and exporting submissions.</li>
  <li>Converter pipeline for PDF, HTML, Markdown, CSV, XLSX, DOCX, XML, JSON, and TXT exports.</li>
  <li>Email notifications using your infrastructure; attachments handled safely.</li>
</ul>
<p><strong>Demo login:</strong> user <code>forms</code> with password <code>formsarecool</code> (Editor role).</p>
<p>Need help with a privacy-first rollout? Email <a href="mailto:info@zopyx.com">info@zopyx.com</a> to discuss your requirements.</p>
""",
        "text/html",
        "text/html",
    ),
)
api.content.transition(obj=welcome, transition="publish")
welcome.reindexObject()
site.setDefaultPage("welcome")

# Mental Health Check-In survey (demo)
mental_intro = """
<h2>Welcome to the Mental Health Survey</h2>
<p>This brief, anonymous survey helps you reflect on your current wellbeing. It is not a diagnostic tool. If you are in crisis, please reach out to a professional or your local emergency number immediately.</p>
<p>The questions focus on mood, stress, sleep, support, and focus. Provide honest answers to get the most from your reflection.</p>
<p><em>Note:</em> This survey is for demonstration purposes. Always seek professional guidance for mental health concerns.</p>
<figure style="margin: 16px 0;">
  <img src="https://images.unsplash.com/photo-1506126613408-eca07ce68773?auto=format&fit=crop&w=800&q=80" alt="Calm landscape" style="width:100%;max-width:720px;border-radius:12px;">
</figure>
""".strip()

mental_form = {
    "title": "Mental Health Survey",
    "description": "A quick, private reflection on how you are feeling this week.",
    "locale": "en",
    "showQuestionNumbers": "off",
    "showProgressBar": "top",
    "progressBarType": "pages",
    "completedHtml": "<h3>Thank you for sharing. If you need support, please contact a professional.</h3>",
    "pages": [
        {
            "name": "intro",
            "elements": [
                {
                    "type": "html",
                    "name": "introText",
                    "html": mental_intro,
                }
            ],
        },
        {
            "name": "mood",
            "elements": [
                {
                    "type": "radiogroup",
                    "name": "overallMood",
                    "title": "How would you describe your overall mood this week?",
                    "isRequired": True,
                    "choices": [
                        "Very positive",
                        "Mostly positive",
                        "Neutral or mixed",
                        "Mostly negative",
                        "Very negative",
                    ],
                }
            ],
        },
        {
            "name": "stress",
            "elements": [
                {
                    "type": "radiogroup",
                    "name": "stressLevel",
                    "title": "How high has your stress felt in the past few days?",
                    "isRequired": True,
                    "choices": [
                        "Very low",
                        "Manageable",
                        "Noticeable but okay",
                        "High",
                        "Overwhelming",
                    ],
                }
            ],
        },
        {
            "name": "sleep",
            "elements": [
                {
                    "type": "radiogroup",
                    "name": "sleepQuality",
                    "title": "How would you rate your sleep quality recently?",
                    "isRequired": True,
                    "choices": [
                        "Restful and consistent",
                        "Mostly okay",
                        "Inconsistent",
                        "Poor",
                        "Very poor",
                    ],
                }
            ],
        },
        {
            "name": "support",
            "elements": [
                {
                    "type": "radiogroup",
                    "name": "supportNetwork",
                    "title": "How supported do you feel by friends, family, or community?",
                    "isRequired": True,
                    "choices": [
                        "Strongly supported",
                        "Supported",
                        "Somewhat supported",
                        "Limited support",
                        "No support",
                    ],
                }
            ],
        },
        {
            "name": "focus",
            "elements": [
                {
                    "type": "radiogroup",
                    "name": "focusLevel",
                    "title": "How easy has it been to focus on daily tasks?",
                    "isRequired": True,
                    "choices": [
                        "Very easy",
                        "Mostly easy",
                        "Manageable",
                        "Difficult",
                        "Very difficult",
                    ],
                }
            ],
        },
    ],
}

create_demo_survey(
    site,
    survey_id="mental-health-survey",
    title="Mental Health Survey",
    description="A short, reflective check-in on wellbeing.",
    form_json=mental_form,
    intro_html=mental_intro,
    actions={"store"},
)

full_demo_intro = """
<h2>Social Media Consumption Demo</h2>
<p>This comprehensive demo form showcases multiple SurveyJS question types in the context of social media habits. It covers frequency, platforms, screen time, uploads, and feedback.</p>
<p>Use it as a starting point to explore panels, matrices, dynamic tables, and file uploads.</p>
""".strip()

full_demo_form = {
    "title": "Social Media Consumption",
    "description": "Demonstration of SurveyJS features using a social media context.",
    "locale": "en",
    "showQuestionNumbers": "on",
    "showProgressBar": "top",
    "progressBarType": "pages",
    "completedHtml": "<h3>Thanks for exploring the demo!</h3><p>Adjust and extend these questions for your own surveys.</p>",
    "pages": [
        {
            "name": "intro",
            "elements": [
                {
                    "type": "html",
                    "name": "demoIntro",
                    "html": full_demo_intro,
                }
            ],
        },
        {
            "name": "basics",
            "title": "Your profile",
            "elements": [
                {
                    "type": "text",
                    "name": "fullName",
                    "title": "What is your name?",
                    "placeHolder": "Alex Doe",
                },
                {
                    "type": "dropdown",
                    "name": "ageRange",
                    "title": "Your age range",
                    "isRequired": True,
                    "choices": [
                        "Under 18",
                        "18-24",
                        "25-34",
                        "35-44",
                        "45-54",
                        "55-64",
                        "65+",
                    ],
                },
                {
                    "type": "checkbox",
                    "name": "primaryPlatforms",
                    "title": "Which platforms do you use weekly?",
                    "isRequired": True,
                    "hasOther": True,
                    "choices": ["Instagram", "TikTok", "YouTube", "Facebook", "LinkedIn", "Snapchat", "X/Twitter"],
                },
                {
                    "type": "rating",
                    "name": "engagementLevel",
                    "title": "How engaged do you feel with social media overall?",
                    "rateMin": 1,
                    "rateMax": 5,
                    "minRateDescription": "Not engaged",
                    "maxRateDescription": "Highly engaged",
                },
            ],
        },
        {
            "name": "time",
            "title": "Time spent",
            "elements": [
                {
                    "type": "rating",
                    "name": "dailyMinutes",
                    "title": "Average minutes per day on social media",
                    "rateMin": 0,
                    "rateMax": 5,
                    "rateStep": 1,
                    "rateValues": [
                        {"value": 0, "text": "Under 30"},
                        {"value": 1, "text": "30-60"},
                        {"value": 2, "text": "1-2 hours"},
                        {"value": 3, "text": "2-3 hours"},
                        {"value": 4, "text": "3-5 hours"},
                        {"value": 5, "text": "5+ hours"},
                    ],
                },
                {
                    "type": "comment",
                    "name": "timeComments",
                    "title": "When do you usually scroll?",
                    "placeHolder": "Morning commute, lunch break, evenings, before bed...",
                },
            ],
        },
        {
            "name": "matrixSection",
            "title": "Platform frequency",
            "elements": [
                {
                    "type": "matrix",
                    "name": "platformFrequency",
                    "title": "How often do you check these platforms?",
                    "isRequired": True,
                    "columns": [
                        {"value": "rarely", "text": "Rarely"},
                        {"value": "weekly", "text": "Weekly"},
                        {"value": "daily", "text": "Daily"},
                        {"value": "hourly", "text": "Multiple times a day"},
                    ],
                    "rows": [
                        {"value": "instagram", "text": "Instagram"},
                        {"value": "tiktok", "text": "TikTok"},
                        {"value": "youtube", "text": "YouTube"},
                        {"value": "facebook", "text": "Facebook"},
                        {"value": "twitter", "text": "X/Twitter"},
                    ],
                }
            ],
        },
        {
            "name": "matrixDynamicSection",
            "title": "Screen time by device",
            "elements": [
                {
                    "type": "matrixdynamic",
                    "name": "screenTimeByDevice",
                    "title": "Add devices and estimate your weekday/weekend screen time.",
                    "isRequired": True,
                    "rowCount": 2,
                    "minRowCount": 1,
                    "addRowText": "Add device",
                    "columns": [
                        {"name": "device", "title": "Device", "cellType": "dropdown", "choices": ["Phone", "Tablet", "Laptop", "Desktop", "TV", "Other"]},
                        {"name": "weekday", "title": "Weekday (hrs)", "cellType": "text", "inputType": "number", "min": 0, "max": 24},
                        {"name": "weekend", "title": "Weekend (hrs)", "cellType": "text", "inputType": "number", "min": 0, "max": 24},
                    ],
                }
            ],
        },
        {
            "name": "uploads",
            "title": "Uploads and feedback",
            "elements": [
                {
                    "type": "file",
                    "name": "screenshot",
                    "title": "Optional: upload a screenshot of your home screen or feed",
                    "maxSize": 1024000,
                    "imageHeight": 150,
                    "imageWidth": 150,
                },
                {
                    "type": "comment",
                    "name": "improvementIdeas",
                    "title": "What would improve your social media experience?",
                },
                {
                    "type": "boolean",
                    "name": "followUp",
                    "title": "May we follow up with you about these insights?",
                    "labelTrue": "Yes, you can contact me",
                    "labelFalse": "No, keep this anonymous",
                },
            ],
        },
    ],
}

create_demo_survey(
    site,
    survey_id="full-demo",
    title="Social Media Consumption Demo",
    description="A comprehensive SurveyJS demo covering many field types.",
    form_json=full_demo_form,
    intro_html=full_demo_intro,
    actions={"store"},
)

feedback_form = {
    "title": "Food Ordering Service Feedback",
    "description": "Quick 1-5 ratings about your recent experience.",
    "locale": "en",
    "showQuestionNumbers": "off",
    "showProgressBar": "top",
    "progressBarType": "questions",
    "completedHtml": "<h3>Thanks for your feedback!</h3>",
    "pages": [
        {
            "name": "ratings",
            "elements": [
                {
                    "type": "rating",
                    "name": "orderEase",
                    "title": "How easy was it to place your order?",
                    "isRequired": True,
                    "rateMin": 1,
                    "rateMax": 5,
                    "minRateDescription": "Very hard",
                    "maxRateDescription": "Very easy",
                },
                {
                    "type": "rating",
                    "name": "deliverySpeed",
                    "title": "How satisfied are you with the delivery speed?",
                    "isRequired": True,
                    "rateMin": 1,
                    "rateMax": 5,
                    "minRateDescription": "Very slow",
                    "maxRateDescription": "Very fast",
                },
                {
                    "type": "rating",
                    "name": "foodQuality",
                    "title": "How would you rate the food quality?",
                    "isRequired": True,
                    "rateMin": 1,
                    "rateMax": 5,
                    "minRateDescription": "Very poor",
                    "maxRateDescription": "Excellent",
                },
            ],
        }
    ],
}

create_demo_survey(
    site,
    survey_id="food-feedback-demo",
    title="Food Ordering Service Feedback",
    description="Rate a fictive food ordering service on three quick questions.",
    form_json=feedback_form,
    intro_html="<p>Please rate our fictional food ordering service from 1 (worst) to 5 (best).</p>",
    actions={"store"},
)

# Create a demo user with Manager role
if not api.user.get(username="forms"):
    api.user.create(username="forms", email="forms@example.com", password="formsarecool")
    api.user.grant_roles(username="forms", roles=["Editor"])
    print("Created demo user 'forms' with Editor role")
else:
    print("Demo user 'forms' already exists")

transaction.commit()
