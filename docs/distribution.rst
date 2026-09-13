=================
Site distribution
=================

Plone creates sites from a *distribution*: a package that bundles the
GenericSetup profiles, the site creation form and the preview image for one
kind of site. This add-on registers the distribution **surveyjs**, which
creates a Classic UI Plone site with Privacy Forms Studio / SurveyJS installed
— and, on request, with the demo content described in
:ref:`demo-content-profile`.

What the distribution installs
==============================

.. list-table::
   :header-rows: 1

   * - Phase
     - GenericSetup profiles
   * - Base profile (always)
     - ``plone.app.contenttypes:default``, ``plone.app.layout:default``,
       ``plonetheme.barceloneta:default``, ``zopyx.surveyjs:default``
   * - Example content (``setup_content``)
     - ``zopyx.surveyjs:demo``

The base set mirrors Plone's built-in ``classic`` distribution plus the
add-on's own default profile. Because the example content is the demo profile,
a site created with *Create Example Content* behaves like the demo instance:
four SurveyJS themes (``light``, ``dark``, ``light-no-panels``,
``dark-no-panels``) and a published ``demo-forms`` folder with the employee
onboarding, customer satisfaction and conference registration forms, each using
a different theme. Without example content you get the add-on and nothing else.

Creating a site
===============

Site creation UI (browser)
--------------------------

Start Plone and open the site creation UI at the Zope application root,
``http://localhost:8082/plone-overview`` (or ``/ploneAddSite``), as a user with
the ``Manager`` role. The overview lists every registered distribution with its
preview image; pick **Privacy Forms Studio (SurveyJS)** and fill in the form.
The fields come from the distribution's ``schema.json``, so site id and title
are prefilled for this kind of site and the *Create Example Content* switch
defaults to on.

REST API
--------

.. code-block:: shell

    curl -X POST http://localhost:8082/@sites \
      -H "Accept: application/json" \
      -H "Content-Type: application/json" \
      -u admin:password \
      -d '{
            "distribution": "surveyjs",
            "site_id": "surveyjs",
            "title": "Privacy Forms Studio",
            "description": "Forms and surveys with SurveyJS.",
            "default_language": "en",
            "portal_timezone": "Europe/Berlin",
            "setup_content": true
          }'

``POST /@sites/surveyjs`` with the same body works as well; the distribution
name then comes from the URL. The service requires the ``Manager`` role. A GET
on ``/@sites`` lists the existing sites.

Programmatic creation (scripts, buildout)
-----------------------------------------

.. code-block:: python

    from Products.CMFPlone.factory import addPloneSite

    addPloneSite(
        app,
        "surveyjs",
        title="Privacy Forms Studio",
        description="Forms and surveys with SurveyJS.",
        distribution_name="surveyjs",
        setup_content=True,
        default_language="en",
        portal_timezone="Europe/Berlin",
    )

``setup_content=False`` installs the add-on without the demo profile; the demo
content can still be added later by applying
``profile-zopyx.surveyjs:demo`` (see :ref:`demo-content-profile`).

Distribution data
=================

.. list-table::
   :header-rows: 1

   * - File
     - Purpose
   * - ``profiles.json``
     - ``base`` (always installed) and ``content`` (installed with example
       content) — lists of GenericSetup profile ids
   * - ``schema.json``
     - JSON schema for the site creation form; ``default_language`` and
       ``portal_timezone`` definitions are added by ``plone.distribution`` at
       runtime
   * - ``image.png``
     - 1080 x 768 preview image shown in the site creation UI
   * - ``content/``
     - *not used here* — optionally a JSON export (``plone.exportimport``) plus
       ``principals.json``/``portals.json`` for distributions that ship content
       as plain data instead of a profile

The distribution is registered in ``distributions.zcml`` with the
``<plone:distribution>`` directive of ``plone.distribution``; its data lives in
``distributions/surveyjs/``. Both paths are inside the package
(``graft src/zopyx`` in ``MANIFEST.in``), so a plain ``pip install
zopyx.surveyjs`` already ships the distribution.

Restricting the offered distributions
=====================================

The environment variable ``ALLOWED_DISTRIBUTIONS`` takes a comma-separated list
of distribution names and limits what the site creation UI offers — for example
``ALLOWED_DISTRIBUTIONS=surveyjs`` for a deployment whose only purpose is
creating Privacy Forms Studio sites.

Tests
=====

``tests/test_distribution.py`` creates two sites from the distribution in one
test layer — one with and one without example content — and asserts the
registration, the installed profiles, the seeded themes and the ``demo-forms``
folder, and that the demo forms render with their themes.
