# From forms to Privacy Forms Studio

## Introduction

A huge of amount of work went over the last weeks into a new product call
Privacy Forms Studio (PFS). PFS started as a successor of collective.easyform.
In one of our latest project, we had a lot of complex forms that could not be
implemented with EasyForm because the functionality is too limited beside
various issue with configurabilty, look & feel, user experience and so on. I
posted about this journey in detail
[here](https://community.plone.org/t/from-ploneformgen-via-easyform-to-surveyjs/22724/4).

Now with PFS, the scope of the project became much broader with focus on
privacy, digitalisation of business processes, optional AI support. Part of the
motivation is the fact that we - in Germany - still have a certain fetish for
fax machines and paper forms. A major lack of digitalization.

## Features (compared with EasyForms)

Let me try to describe the main features of PFS from the prospective of what we
have in EasyForm or formerly in Plone FormGen. The core functionality is to
create and manage forms in a modern way. The underlying technology is
[SurveyJS](https://surveyjs.io) - a family of Javascript libraries for building
online surveys and forms. The core format is JSON for form data and form schema
definitions. The core benefits of SurveyJS are:

- Modern and highly customizable UI
- Wide range of question types
- Advanced logic and branching
- Integration capabilities with various backend systems
- Responsive design for mobile and desktop
- Support for various data formats (JSON, CSV, etc.)
- Extensibility through custom widgets and themes
- Active community and commercial support options
- Regular updates and improvements

With Privacy Forms Studio we provide a Plone integration for SurveyJS with the
following main features:

- Create and manage forms in Plone with SurveyJS
- Store form definitions as JSON in Plone - including versioning (restore older
version, preview older version, export any form version as JSON)
- Integration with the SurveyJS Creator - a visual form designer supporting drag
& drop to create and modify forms
- transformation of form data to various formats (Text, PDF, Markdown, DOCX,
JSON, CSV, Excel)
- various (optional) actions (similar to adapters in Easyform) to process form submissions:
  - Store submissions in Plone (with export options)
  - Send submission data via email (in any of the supported formats) 
  - Send email notifications (privacy option if you don't want to include form data in the notification)
  - Webhooks to send submission data to external systems
  - Custom Python actions to implement any custom logic (via event notifications)

- management of stored submissions (view, filter, export, delete) - either per
form submission or for all form submissions 

- storage options for form submissions: in Plone or external databases (e.g. PostgreSQL, MySQL, etc.)
- storage of form schema defintions (JSON): in Plone but can be exported as JSON for further usage
- full i18n support for most of the known languages (since form definitions are self-contained, you can create forms in any language)

This is the core functionality of Privacy Forms Studio. There are many more
features. Think of it as bringing the ideas of PloneFormGen and
collective.easyform to the modern age with a focus on privacy and
digitalization. The primary focus of Privacy Forms Studio is on forms but as the
name `SurveyJS` implies, you can also create surveys with it. SurveyJS has
various question types for rating, ranking, Likert scales and so on. For more
complex survey scenarios. A survey is just a form so you can easily create nice
surveys now with in Plone.

And of course, all Plone security and privacy features apply here as well. You have
full control over your data, who can access forms and submissions, and how data
is processed. The stack of Plone options regarding workflows, permissions, access control and authorization applies here as well.

## AI Features

Privacy Forms Studio also comes with optional AI features to enhance form
creation and form processing. These features are optional and can be enabled or
disabled based on user preferences and privacy considerations. The AI features
include:

- AI-assisted form creation: Use AI to create and refine forms based on user
prompts. For example, you can ask the AI to create a customer feedback form or a
job application form. The AI will generate a form schema with relevant. You are
free to accept, modify or discard the generated form. An AI-generated form can
be edited later with the build-in SurveyJS Creator. So you are free to use AI
but there is no obligation

- support for almost all AI providers (OpenAI, Azure OpenAI, HuggingFace, etc.)
where you can choose the model you want to use (GPT-4, GPT-3.5, etc.) and
configure your API key as a global option within the Plone configuration. If you want, you can also set up a local AI endpoint (e.g. with Ollama).

AI usage is completely optional. Form data never leaves your system (unless you
configure a webhook or mail actions with form data delivery by email). AI is
only used to create or refine form definitions - not for processing form
submissions. This way, you can benefit from AI while maintaining full control
over your data and privacy. 

## Extended features and roadmap

We are currently experimenting with additional features for integrating fillable
PDF forms and digital signatures. These features are not yet part of the main
release but are in the prototype stage. This includes:

- Fillable PDFs can be uploaded into Privacy Forms Studio and the system will
automatically create a corresponding form definition based on the PDF form
fields. This way, you can easily digitize existing paper forms that are already
available as fillable PDFs. This works either algorithmically or with AI
assistance. The quality and results depend on the complexity of the PDF form and
how they are implemented. The electronic version of a fillable PDF can then be
used to collect form submissions digitally. The full core functionality of such an
imported fillable PDF applies here. 

 - Fillable PDF generation from form submissions: Based on a form submission, a
fillable PDF can be generated with the submitted data. This way, you can
digitally fill out PDF forms and provide them to users for download or further
processing. This is especially useful for scenarios where a filled PDF form is
required for legal or administrative purposes. Privacy Forms Studio supports the incremental shift from paper-based forms and non-digital processes and workflows to fully digital solutions. 

- Vision of a central "form server": We have plans to extend Privacy Forms
Studio to act as a central "form server" for multiple Plone instances or any web
application. Embedding is the key. The idea is that any web application would be
able to reference a form hosted in Privacy Forms Studio and embed it seamlessly.
This would allow organizations to centralize their form management and ensure
consistency across different platforms and applications. Embedding would be done
via iframe or direct Javascript embedding. This is still in the early conceptual
stage but we see a lot of potential here for supporting digitalization
initiatives across an organization where the technology stack is diverse and
heterogeneous (and non-Plone).


## Privacy Feature and target audience

Privacy is one of the core principles of Privacy Forms Studio. By default, all
data belong to you, all your data stays within your infrastructure and organization.
AI feature are optional and can be disabled. No data is sent to third-party services.

The focus and target audience of Privacy Forms Studio are organizations and
businesses that need to comply with strict privacy regulations (e.g. GDPR) and
want to ensure that their data is handled securely and responsibly. In the
context of Plone, we see traditional Plone customers and origanizations using
Plone on a large scale as the primary target audience for Privacy Forms Studio.
In the near future, we also see potential for small and medium-sized businesses
that want to leverage the power of Plone and Privacy Forms Studio for their
digitalization initiatives.  

## Deployment options availability

We are currently working on making Privacy Forms Studio available through
various deployment options including:

- Plone Add-on via PyPI for manual installation
- as dedicated "form server" Docker container for easy deployment and scaling
- perhaps: as SaaS solution for easy access and usage without the need for
  infrastructure management

## Licensing and Contributions

We are currently evaluating the best licensing model for Privacy Forms Studio in
cooperation with the `SurveyJS` team. Parts of SurveyJS are publically available
as open source while other parts are commercial. We want to ensure that Privacy
Forms Studio remains accessible and affordable for the Plone community while
also respecting the licensing terms of SurveyJS. In general the pricing model of
SurveyJS is quite reasonable and affordable even for small organizations and we
are currently in discussion with the SurveyJS team to find the best way forward,
in particular for open source projects and non-profits and regarding the scope
of our personal developer licenses.


## Websites and further information

We are currently working on a dedicated website for Privacy Forms Studio
where you can find more information, documentation, tutorials, and a demo
website to try out the features of Privacy Forms Studio. 

- Main website: https://privacyforms.studio
- Demo website: https://demo.privacyforms.studio


