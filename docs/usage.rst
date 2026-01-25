=====
Usage
=====

Typical workflow
================

1. Create a Survey content item in Plone.
2. Open ``@@editor`` to design the form using SurveyJS Creator.
3. Configure actions and settings on the Survey (see :doc:`configuration`).
4. Publish and distribute the Survey URL or embed it (see :doc:`embedding`).
5. Use ``@@results2`` and exports to review submissions.

Roles
=====

Authors
  Create and refine form JSON via the editor or AI Generator.

Managers
  Configure actions, exports, and embeddings. Review results and handle
  exports or notifications.

End users
  Access the survey via ``@@viewer`` or embedded views and submit responses.

Storage backends
================

Survey results can be stored in the ZODB (default) or in a relational database
using SQLModel. Relational rows include the Plone ``site_id`` and survey
identifier so a single database can serve multiple sites. Switch the backend
in the Forms control panel. To migrate existing ZODB results to a relational
database, call ``migrate_zodb_results_to_rdbms(context)`` from a Zope/Plone
console script.
