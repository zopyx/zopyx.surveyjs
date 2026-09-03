Changelog
=========


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


1.0a4 (unreleased)
------------------

- Fix: the generated demo site (``scripts/init_plone.py``) showed up without
  any theme. ``addPloneSite`` was called with an invalid ``distribution``
  keyword (the parameter is ``distribution_name`` since Plone 6.1), so the
  classic distribution never ran and the Plone Classic theme (Barceloneta)
  was never applied. Use ``distribution_name`` and enable the ``barceloneta``
  theme instead of ``privacyforms.theme``.


1.0a3 (unreleased)
------------------

- Nothing changed yet.


1.0a2 (unreleased)
------------------

- Nothing changed yet.


1.0a1 (unreleased)
------------------

- Initial release.
  [zopyx]
