# -*- coding: utf-8 -*-
# from plone.autoform import directives
from plone.dexterity.content import Item
from plone.namedfile import field as namedfile
from plone.supermodel import model
from zope.interface import implementer

# from plone.supermodel.directives import fieldset
# from z3c.form.browser.radio import RadioFieldWidget
from z3c.form.browser.checkbox import CheckBoxFieldWidget
from z3c.form.browser.textarea import TextAreaFieldWidget
from zope import schema
from BTrees.OOBTree import OOBTree
from Persistence import Persistent
from zope.schema.vocabulary import SimpleVocabulary, SimpleTerm
from zopyx.surveyjs import _
from plone.autoform import directives as form
from plone.supermodel.directives import fieldset
from zope.annotation.interfaces import IAnnotations

from ..constants import FORM_VERSIONS_KEY, RESULTS_KEY

survey_actions_vocabulary = SimpleVocabulary(
    [
        SimpleTerm(value="store", title=_("Store")),
        SimpleTerm(value="mail", title=_("Mail")),
        SimpleTerm(value="mail-notification", title=_("Mail (notification only)")),
        SimpleTerm(value="post", title=_("POST to endpoint")),
    ]
)

survey_formats_vocabulary = SimpleVocabulary(
    [
        SimpleTerm(value="text", title=_("Text (.txt)")),
        SimpleTerm(value="md", title=_("Markdown (.md)")),
        SimpleTerm(value="html", title=_("HTML (.html)")),
        SimpleTerm(value="pdf", title=_("PDF (.pdf)")),
        SimpleTerm(value="csv", title=_("CSV (.csv)")),
        SimpleTerm(value="xlsx", title=_("Excel (.xlsx)")),
        SimpleTerm(value="xml", title=_("XML (.xml)")),
        SimpleTerm(value="docx", title=_("Word (.docx)")),
        SimpleTerm(value="json", title=_("JSON (.json)")),
    ]
)

survey_embedding_vocabulary = SimpleVocabulary(
    [
        SimpleTerm(value="none", title=_("None")),
        SimpleTerm(value="iframe", title=_("Iframe")),
    ]
)

survey_access_vocabulary = SimpleVocabulary(
    [
        SimpleTerm(value="public", title=_("Public")),
        SimpleTerm(value="trusted", title=_("Trusted access token")),
    ]
)


class Counter(Persistent):
    def __init__(self, count=0):
        self.count = count

    def increment(self):
        self.count = self.count + 1
        return self.count

    def _p_resolveConflict(self, oldState, savedState, newState):
        # Figure out how each state is different:
        savedDiff = savedState["count"] - oldState["count"]
        newDiff = newState["count"] - oldState["count"]

        # Apply both sets of changes to old state:
        oldState["count"] = oldState["count"] + savedDiff + newDiff

        return oldState


class ISurvey(model.Schema):
    """Marker interface and Dexterity Python Schema for Survey"""

    fieldset(
        "actions",
        label=_("Actions"),
        fields=(
            "actions",
            "post_endpoint_url",
        ),
    )

    fieldset(
        "mail",
        label=_("Mail"),
        fields=(
            "email_sender",
            "email_subject",
            "email_to",
            "email_cc",
            "email_bcc",
            "email_formats",
            "email_body",
        ),
    )

    fieldset(
        "mail_notifications",
        label=_("Mail notifications"),
        fields=(
            "email_notification_subject",
            "email_notification_body",
        ),
    )

    fieldset(
        "form_settings",
        label=_("Form Settings"),
        fields=(
            "validation_enabled",
            "force_server_side_validation",
            "max_payload_size_mb",
            "access_mode",
            "trusted_access_ttl_hours",
        ),
    )
    fieldset(
        "pdf_form",
        label=_("PDF Form"),
        fields=("pdf_form",),
    )
    fieldset(
        "embedding",
        label=_("Embedding"),
        fields=("embedding_mode",),
    )

    form.widget("actions", CheckBoxFieldWidget)
    form.widget("email_body", TextAreaFieldWidget, rows=10, cols=80)
    actions = schema.Set(
        title=_("Actions"),
        description=_(
            "Select how to handle survey submissions (multiple options possible). "
            "Store saves the submission in Plone; Mail sends exported results as attachments; "
            "Mail (notification only) sends a notification without attachments; "
            "POST to endpoint forwards the submission payload to the configured HTTP endpoint."
        ),
        value_type=schema.Choice(vocabulary=survey_actions_vocabulary),
        required=True,
        default={"store"},
    )

    validation_enabled = schema.Bool(
        title=_("Enable validation (experimental)"),
        description=_(
            "Validate submissions against the form schema before saving. "
            "Experimental: may reject valid submissions on complex forms."
        ),
        required=False,
        default=False,
    )

    force_server_side_validation = schema.Bool(
        title=_("Force Server Side Validation"),
        description=_(
            "Run the external SurveyJS validator binary for every save/submit."
        ),
        required=False,
        default=False,
    )

    max_payload_size_mb = schema.Int(
        title=_("Max size payload (MB)"),
        description=_("Maximum allowed payload size for submissions in megabytes."),
        required=False,
        default=1,
        min=1,
    )

    access_mode = schema.Choice(
        title=_("Access mode"),
        description=_(
            "Choose whether this form is publicly accessible or requires a trusted "
            "access token in the URL."
        ),
        vocabulary=survey_access_vocabulary,
        required=True,
        default="public",
    )

    trusted_access_ttl_hours = schema.Int(
        title=_("Trusted access token TTL (hours)"),
        description=_("Lifetime of trusted access tokens in hours."),
        required=False,
        default=168,
        min=1,
    )

    embedding_mode = schema.Choice(
        title=_("Embedding mode"),
        description=_(
            "Controls whether this survey may be embedded. Use Iframe to allow embedding."
        ),
        vocabulary=survey_embedding_vocabulary,
        required=True,
        default="none",
    )

    email_sender = schema.TextLine(
        title=_("E-Mail sender"),
        description=_(
            "Sender address for outgoing mail. Mandatory when the Mail action is selected."
        ),
        required=False,
    )

    email_to = schema.TextLine(
        title=_("E-Mail recipient"),
        description=_(
            "Primary recipient for notifications and result exports (single address). "
            "Mandatory when the Mail action is selected."
        ),
        required=False,
    )

    email_subject = schema.TextLine(
        title=_("Subject"),
        description=_(
            "Subject for result export emails. Supports {poll_id} for the submission ID. "
            "Mandatory when the Mail action is selected."
        ),
        required=False,
    )

    email_cc = schema.List(
        title=_("E-Mail CC"),
        description=_(
            "Optional CC recipients for result exports (one address per line)."
        ),
        value_type=schema.TextLine(
            title=_("CC recipient"),
            description=_("Email address to receive a copy"),
            required=False,
        ),
        required=False,
        defaultFactory=list,
    )

    email_bcc = schema.List(
        title=_("E-Mail BCC"),
        description=_(
            "Optional BCC recipients for result exports (one address per line)."
        ),
        value_type=schema.TextLine(
            title=_("BCC recipient"),
            description=_("Email address to receive a blind copy"),
            required=False,
        ),
        required=False,
        defaultFactory=list,
    )

    form.widget("email_formats", CheckBoxFieldWidget)
    email_formats = schema.Set(
        title=_("Formats"),
        description=_(
            "Select export formats to attach when the Mail action sends results."
        ),
        value_type=schema.Choice(vocabulary=survey_formats_vocabulary),
        required=False,
        default=set(),
    )

    email_body = schema.Text(
        title=_("Body"),
        description=_(
            "Body text for result export emails. Supports {created}, {creator}, {formats}."
        ),
        required=False,
    )

    email_notification_subject = schema.TextLine(
        title=_("Subject for notifications"),
        description=_(
            "Subject for notification-only emails. Supports {title}, {detail_url}, {poll_id}."
        ),
        required=False,
        default="Form submitted ({title})",
    )

    email_notification_body = schema.Text(
        title=_("Body for notifications"),
        description=_(
            "Body text for notification-only emails. Supports {title}, {detail_url}, {poll_id}."
        ),
        required=False,
        default=(
            "Hello,\n\n"
            'A new form submission was received for "{title}".\n'
            "You can review the submitted data here:\n"
            "{detail_url}\n\n"
            "Regards,\n"
            "Privacy Forms Studio\n"
        ),
    )

    post_endpoint_url = schema.URI(
        title=_("POST endpoint URL"),
        description=_(
            "Optional HTTP endpoint to receive submissions as JSON when the POST action is enabled."
        ),
        required=False,
    )

    pdf_form = namedfile.NamedBlobFile(
        title=_("Fillable PDF form"),
        description=_(
            "Optional fillable PDF form. Uploading a PDF enables the PDF-based "
            "form workflow for this Survey."
        ),
        required=False,
    )


@implementer(ISurvey)
class Survey(Item):
    """Content-type class for ISurvey"""

    def __init__(self, *args, **kw):
        for k, v in kw.items():
            setattr(self, k, v)

        annos = IAnnotations(self)
        annos[FORM_VERSIONS_KEY] = OOBTree()
        annos[RESULTS_KEY] = OOBTree()
        self.seq_no = Counter()

        super().__init__(*args, **kw)
