Release checklist
=================

How a release of ``zopyx.surveyjs`` is cut. ``setup.py`` is the single version
source; ``pyproject.toml`` deliberately has no ``[project]`` table (it would
switch setuptools into PEP 621 hybrid mode and break the buildout develop
step).

For the 1.0 beta the sequence below is the gate. Steps marked **(gate)** must
pass before the version is published.

1. Version and changelog
------------------------

- Bump ``version=`` in ``setup.py``.
- Add a new ``<version> (unreleased)`` section at the top of ``CHANGES.rst``
  describing what accumulated since the previous section.
- ``(unreleased)`` states that the version is not on PyPI yet. After a
  successful publish (step 8) the heading is switched to
  ``<version> (released YYYY-MM-DD)`` using the upload date. A version that was
  never published keeps ``(unreleased)`` permanently (``1.0a5``–``1.0a7`` and
  ``1.0b2`` so far); the label is never flipped before the upload.
- If the last published version on PyPI is older than the previous section,
  the new section must summarise the changes users get on upgrade from that
  published version.

2. Local gates **(gate)**
-------------------------

.. code-block:: shell

    make test           # bin/test -s zopyx.surveyjs + coverage pytest subset
    make docs           # Sphinx with -W (warnings are errors)
    uv run --no-project ruff check --fix .
    uv run --no-project ruff format --check .
    git diff --check

Expected baseline: 496 Plone tests with 0 failures and 0 errors (75 skipped
without ``RUN_DB_CONTAINER_TESTS=1``), 115 pytest tests, 100 % converter
coverage, docs build clean. ``ruff check`` and ``ruff format --check`` report
nothing; the findings that used to be tolerated in untouched files have been
fixed, so any finding is a blocker now.

3. Source distribution **(gate)**
---------------------------------

.. code-block:: shell

    make sdist
    tar -tzf dist/zopyx_surveyjs-<version>.tar.gz > /tmp/sdist.txt

Check:

- ``PKG-INFO``: ``Name``, ``Version``, the Project-URLs (Source/Tracker/
  Documentation/Changelog point at ``github.com/zopyx/zopyx.surveyjs``) and
  the classifiers;
- Plone metadata present: ``configure.zcml``, ``profiles/default/metadata.xml``,
  ``profiles/default/controlpanel.xml``, ``browser/static``;
- excluded: ``docs/old``, ``docs/html``, ``docs/_build``, ``tokens.csv``.

4. CI **(gate)**
----------------

Push the release commit to ``master`` and wait for all workflows: ``Test``
(includes the ``package-matrix`` job for Python 3.12/3.13/3.14 and the
validator-binary job), ``Docs``, ``Build source distribution``, ``Demo Docker
image -> Prod``, ``Playwright Screenshots``. A red or cancelled run blocks the
release; the Docker job is cancelled by ``concurrency`` when a newer commit
arrives, in which case re-run it on the release commit.

5. Upgrade path **(gate)**
--------------------------

Install the previous published version (currently ``1.0b1``) into a throwaway
Plone site, then upgrade to the release candidate of this version and check:

- the add-on installs and the GenericSetup profile chain
  (``1001``→``1002``→``1003``) runs without error,
- existing surveys, form versions, result storage and themes survive,
- the Forms control panel, ``@@theme-manager`` and the fillable-PDF screen
  render.

6. Tag and pre-release
----------------------

.. code-block:: shell

    git tag -a v<version> -m "Release <version>"
    git push origin v<version>

The ``Build source distribution`` workflow builds the sdist for the tag and
creates a GitHub release. Versions containing ``a``/``b``/``rc``/``dev``/``post``
are automatically flagged as GitHub **pre-releases** (see ``sdist.yml``), so a
beta is never offered as the project's latest release. For ``1.0b2`` expect a
pre-release entry, not "Latest".

7. Publish to PyPI
------------------

``publish-pypi.yml`` and ``publish-testpypi.yml`` are ``workflow_dispatch``
only — a push never publishes. Both use Trusted Publishing (no tokens) and
build with Python 3.14, matching CI.

1. Dry run: dispatch ``Publish to TestPyPI`` on the tag, then
   ``uv pip install --index-url https://test.pypi.org/simple/ zopyx.surveyjs==<version>``
   into a scratch environment and check the metadata.
2. Dispatch ``Publish to PyPI`` on the tag and verify the release page:
   description renders, project URLs resolve, classifiers list only Plone 6.2
   and Python 3.12/3.13/3.14.

8. After publishing
-------------------

- Switch the ``CHANGES.rst`` section of the released version from
  ``(unreleased)`` to ``(released YYYY-MM-DD)``, using the PyPI upload date
  (the date in the release's file listing), and use the same date in the
  GitHub release notes.
- Verify the installed distribution in a real site
  (``pip install zopyx.surveyjs==<version>`` into a Plone buildout, run
  ``bin/instance fg``, log in, open a survey).
- Update the demo/website deployments if the release contains user-visible
  changes.
- GitHub release notes: mention the known limitations
  (``docs/limitations.rst``) and any accepted security risks tracked in
  ``SECURITY.md``.
