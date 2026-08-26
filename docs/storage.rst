Storage Backends
================

SurveyJS submissions are stored through one of two result-storage backends:

* **ZODB** — Plone's object database, stored with the survey object.
* **RDBMS** — a relational database accessed through SQLAlchemy/SQLModel.

The storage backend is configured globally in **Site Setup > Forms > Storage**.
It applies to survey results and the access-token store.

.. note::

   The default **backend** is currently ``zodb``.  The default database URI
   shown for the relational backend is ``sqlite:///var/surveyjs-results.db``;
   selecting the SQLite URI does not activate relational storage by itself.
   Select ``rdbms`` as the backend as well.

Choosing a backend
==================

ZODB
----

ZODB requires no external database service and is convenient for development,
small installations, and forms with a low submission rate. Results are kept in
annotations on the survey object.

ZODB uses optimistic concurrency. Concurrent requests that update the same
object can produce ``ConflictError`` exceptions. Submission bursts and several
workers writing the same survey therefore increase conflicts and retries. For
that reason, ZODB is suitable for polls and forms with **low utilization**, but
is not the preferred backend for high-rate or heavily concurrent forms.

ZEO setup
~~~~~~~~~

ZEO allows multiple Plone processes to share a ZODB, but it does not make the
ZODB write path a good fit for heavily concurrent result storage. In a ZEO
deployment, multiple workers may need to write submissions at the same time,
and updates to shared survey or result objects can consequently cause
conflicts and retries. For forms or pools with high submission volume, an
RDBMS backend—preferably PostgreSQL or MySQL—is recommended instead. SQLite is
also not recommended for high-volume writes because it has a single-writer
constraint; use it only for local or low-volume deployments.

RDBMS via SQLAlchemy/SQLModel
-----------------------------

The ``rdbms`` backend stores results in relational tables. The records contain
the Plone ``site_id`` and survey identifier, so one database can be shared by
multiple Plone sites while keeping their results separate.

Supported database families are:

* **SQLite** — simple, local, and the default URI for the RDBMS option:
  ``sqlite:///var/surveyjs-results.db``.
* **PostgreSQL** — recommended for sustained concurrent writes and multiple
  Plone workers.
* **MySQL** — suitable when it is already part of the deployment platform.

SQLite is an RDBMS and is generally a better choice than ZODB for a local,
moderately busy form. The backend enables WAL mode and a busy timeout for
SQLite. SQLite still has a single-writer constraint, however; for sustained
high submission rates, many workers, or multiple application hosts, use
PostgreSQL or MySQL instead.

Configuration
=============

In **Site Setup > Forms > Storage**:

#. Set **Result storage backend** to ``rdbms``.
#. Set **Database URI** to a SQLAlchemy-style URI.
#. Save the Forms settings.

Examples::

    sqlite:///var/surveyjs-results.db
    postgresql+psycopg2://[USER]:[PASSWORD]@[HOST]/[DATABASE]
    mysql+pymysql://[USER]:[PASSWORD]@[HOST]/[DATABASE]

The database URI must be reachable by the Plone process. Do not put database
passwords in documentation, source control, or publicly readable configuration
files. Use the deployment's protected configuration mechanism.

Operational recommendations
===========================

====================  ================================================
Workload              Recommended configuration
====================  ================================================
Development           ``zodb`` or local ``rdbms`` with SQLite
Low-rate production   ``zodb`` or SQLite, depending on concurrency needs
Moderate local rate   ``rdbms`` with SQLite and WAL enabled
High-rate production  ``rdbms`` with PostgreSQL or MySQL
Multiple app hosts    ``rdbms`` with PostgreSQL or MySQL
====================  ================================================

For high-rate forms, also monitor database connections, transaction latency,
failed writes, and application logs for conflict or lock errors. Load-test the
chosen backend with the expected number of Plone workers before production use.
See :doc:`load-testing` for the project's load-testing observations.

Migrating existing results
==========================

Existing ZODB results can be copied to the relational backend from a Zope or
Plone console script::

    from zopyx.surveyjs.storage_migration import migrate_zodb_results_to_rdbms

    count = migrate_zodb_results_to_rdbms(
        context,
        database_uri="postgresql+psycopg2://[USER]:[PASSWORD]@[HOST]/[DATABASE]",
    )

The migration copies results; it does not delete the original ZODB entries.
Verify the row count and representative results in the relational backend
before switching the configured backend. During a migration, avoid accepting
new submissions if an exact cut-over snapshot is required.

Backend differences
===================

* The two backends are independent. Switching the setting does not merge or
  automatically move existing results.
* Result queries and exports use the configured backend transparently.
* The RDBMS backend is preferable when results must be queried externally with
  SQL or reported across multiple Plone sites.
* Database backups must be configured separately for an external RDBMS or
  SQLite file. A normal Plone/ZODB backup does not replace an RDBMS backup.

Related documentation
=====================

* :doc:`global-options` — Forms control-panel settings
* :doc:`installation` — optional relational-storage setup
* :doc:`usage` — storage backend overview
* :doc:`load-testing` — observed concurrency and ZODB conflict behavior
