Changelog
=========


1.0b2 (released 2026-09-13)
---------------------------

- Set the package version to ``1.0b2``.
- Add the optional GenericSetup profile ``zopyx.surveyjs:demo``
  (``profiles/demo/``, handlers in ``demo_profile.py``). It seeds the four
  SurveyJS theme presets (``light``, ``dark``, ``light-no-panels``,
  ``dark-no-panels``) and creates a published ``demo-forms`` folder with three
  complex English example forms, one per scope and each using a different
  theme: employee onboarding, customer satisfaction and conference
  registration. Both import steps are idempotent, and a form gets a new version
  only when its shipped definition changed, so re-applying the profile after an
  upgrade refreshes the demo content without duplicating anything.
- Add the Plone site distribution ``surveyjs`` (``distributions.zcml`` plus
  ``distributions/surveyjs/``). It creates a Classic UI site with this add-on
  installed and uses the demo profile as its example content, so the themes and
  the ``demo-forms`` folder are created when a site is created with example
  content (``setup_content``). Documented in ``docs/distribution.rst``.
- Add seven diagrams to the documentation (``docs/_static/diagrams/``): the
  component overview and the submission lifecycle, the validation pipeline, the
  deployment topology, the token lifecycle, the export pipeline and the storage
  backends. Every raster image links to its interactive HTML artifact (zoom,
  pan, light/dark themes, guided views, search), the generator specifications
  ship alongside so the diagrams stay reproducible, and the images are embedded
  in ``overview.rst``, ``actions.rst``, ``validation.rst``, ``storage.rst``,
  ``security.rst``, ``exports.rst`` and ``installation.rst``.
- Fix ``browser/ai.py``: ``_to_jsonable()`` logged from its ``except`` branches
  through a module logger that was never defined, so a serializer method that
  raised turned the whole call into a ``NameError`` instead of falling through
  to the next strategy (``vars(value)``). The logger is defined now, and
  ``tests/test_ai.py::AIViewTests::test_to_jsonable_survives_failing_serializer_methods``
  covers the fallback.
- Make the repository pass ``ruff`` completely: ``ruff format`` and
  ``ruff check --fix`` reformatted 41 files (docstring whitespace, blank lines
  after the import block, import grouping, comment indentation) without any
  behaviour change, and the ten findings that survived the automatic fixes were
  fixed by hand — the missing logger above, an unused
  ``PDFFormNotFoundError`` re-export in ``browser/fillable_pdf.py``, and unused
  locals in the token-store and theme-manager tests, which now assert the
  behaviour their comments only described. ``RELEASE.rst`` requires a clean
  ``ruff check``/``ruff format --check`` run as part of the release gate and no
  longer tolerates pre-existing findings.


1.0b1 (released 2026-09-12)
---------------------------

First beta release. The functional changes since the last published version on
PyPI (``1.0a4``) are described in the ``1.0a5``–``1.0a7`` sections below; the
entries here are the release-preparation changes of the beta itself.

- Set the package version to ``1.0b1``.
- Declare the runtime dependencies that previously existed only in this
  repository's buildout: ``privacyforms.ai`` (imported by the AI generator,
  the AI service and the model vocabulary) and ``privacyforms.pdf`` (the
  fillable-PDF workflow). PDF *filling* needs PyMuPDF, which is shipped as the
  optional extra ``zopyx.surveyjs[pdf]`` instead of a hard requirement because
  it is dual-licensed (AGPL-3.0 or a commercial Artifex licence).
- Import ``privacyforms_ai`` lazily (``browser/services/ai.py:get_ai_helper()``)
  instead of at module level in ``browser/ai.py``. A deployment without the
  helper now fails the single AI feature with an actionable message instead of
  failing while Zope configures the add-on (ZCML resolves ``.ai.AIView``).
- Remove unreachable PDF code: ``browser/services/pdf.py`` (no caller at all,
  its ``extract_mode="llm"`` branch imported the deleted ``ai_generator``
  module) and ``pdf_forms.py`` (the unwired pdfcpu pipeline, reachable only
  from the removed module). The supported paths are the AI generator
  (``@@ai-upload``) and the fillable-PDF workflow.
- Documentation corrections: the fillable-PDF pages no longer claim that
  survey data is merged into a PDF template (values come from the fill form,
  keyed by raw PDF field names; signature fields are never written), the
  ``todo`` page is replaced by ``limitations.rst`` documenting the known gaps
  (rate limiting, automatic PDF merge, security items tracked in SECURITY.md,
  multi-server KV behaviour), the stale test-baseline numbers in ``SECURITY.md``
  and ``docs/security.rst`` are refreshed to the measured 475 Plone tests /
  115 pytest tests, and ``docs/old/`` carries a README marking its files as
  historical, non-authoritative notes.
- Add ``RELEASE.rst`` with the release checklist, and use Python 3.14 in the
  PyPI/TestPyPI publish workflows so the publishing interpreter matches the
  one the test suite runs on.
- Enable the ``pdf`` extra in this repository's buildout (``base.cfg``) so the
  documented "Download Filled PDF" workflow actually works in the dev and demo
  instance; PyMuPDF was previously missing there, so the feature failed with
  "PyMuPDF is required". PyMuPDF stays an extra because of its dual licence
  (AGPL-3.0 or commercial).
- Remove the pdfcpu binary from the container image and delete the unreachable
  pdfcpu CLI wrapper ``pdf_form_extract.py`` together with its tests. With
  ``pdf_forms.py`` gone, nothing used the binary any more; the supported PDF
  extraction path is ``privacyforms.pdf``.
- Remove the remaining add-on-template leftovers: ``constraints.txt`` (it only
  contained ``-c constraints_plone52.txt``), ``.travis.yml`` and
  ``.gitlab-ci.yml`` (both pinned to ``python:2.7``). GitHub Actions is the CI.
- Ignore the local buildout variant ``test-6.2.x.cfg`` and the local ``uv.lock``
  in ``.gitignore`` (``requirements.txt`` pins the buildout toolchain).
- ``SECURITY.md`` now itemises the unfixed security findings with location,
  impact and recommendation — SSRF via ``post_endpoint_url``, missing rate
  limiting, CSV/XLSX formula injection, unaudited exports, token-store
  atomicity, key length/rotation, missing token/session binding, container
  hardening, dependency pinning, bot controls, output encoding and CSRF —
  instead of naming them in prose only.
- Add ``scripts/invalidate_tokens.py`` to invalidate the tokens of a leaked
  CSV export across all surveys (dry run by default, ``--apply`` to write).


1.0a7 (unreleased)
------------------

- Update the vendored SurveyJS browser bundles, translations, and server-side
  validator to SurveyJS 3.0.4.
- Build the validator without Deno's 24-hour minimum-dependency-age window, so
  a deliberately pinned ``survey-core`` release compiles immediately instead of
  failing the CI validator job and install-time builds for a day after each
  upstream release.
- Remove a timing race from the KV store TTL expiry test that failed
  intermittently on loaded CI runners.
- Correct the package metadata: the PyPI project URLs now point at the actual
  repository (``zopyx/zopyx.surveyjs``) instead of the never-existing
  ``collective/zopyx.surveyjs``, and they document where the documentation
  and the changelog live. The classifiers now list only the supported
  platform (Plone 6.2, replacing the obsolete Plone 5.2 entry) and the
  Python versions that CI actually exercises (3.12, 3.13, 3.14).
- Add a CI job that installs the built distribution and runs the Plone-free
  test subset (converters, schema, validator wrapper) on Python 3.12, 3.13
  and 3.14, so the advertised Python support is verified rather than assumed.
- Remove the legacy Plone 5.2 buildout configuration (``test_plone52.cfg``)
  and the ``tox.ini`` inherited from the add-on template, which still
  targeted Python 2.7/3.7 and Plone 4.3–5.2 and referred to a constraints
  file that no longer exists.
- Exclude local-only documentation from the source distribution:
  ``docs/old`` describes removed features, ``docs/html``/``docs/_build`` are
  artifacts of a local ``make docs`` run.
- Tag pre-releases (``a``/``b``/``rc``) are published as GitHub pre-releases
  instead of full releases, so a beta is never offered as the latest release.
- Ignore generated security-review artifacts and local scratch files
  (``tokens.csv``, the vulnerability report snapshots, ``tmp/``, local
  agent/tool directories) so they cannot be committed accidentally.


1.0a6 (unreleased)
------------------

- Add per-survey SurveyJS theme selection with default theme support.
- Add the Theme Manager configlet, theme creation/upload actions, and
  improved upload and creation button styling with icons.
- Improve the theme editor toolbar with semantic action colors and a restore
  version action icon.
- Apply panelless SurveyJS themes correctly in the editor preview.
- Show version numbers in the theme history and restore-version dialog.
- Update the vendored SurveyJS browser bundles, translations, and server-side
  validator to SurveyJS 3.0.2.
- Fix CI buildout action paths and use Python 3.14 for the Plone environment.


1.0a5 (unreleased)
------------------

- Version bump to 1.0a5 to trigger a fresh CI run of all workflows.


1.0a4 (released 2026-08-11)
---------------------------

- Fix: the generated demo site (``scripts/init_plone.py``) showed up without
  any theme. ``addPloneSite`` was called with an invalid ``distribution``
  keyword (the parameter is ``distribution_name`` since Plone 6.1), so the
  classic distribution never ran and the Plone Classic theme (Barceloneta)
  was never applied. Use ``distribution_name`` and enable the ``barceloneta``
  theme instead of ``privacyforms.theme``.


1.0a3 (released 2026-08-11)
---------------------------

- Nothing changed yet.


1.0a2 (released 2026-08-11)
---------------------------

- Nothing changed yet.


1.0a1 (unreleased)
------------------

- Initial release.
  [zopyx]