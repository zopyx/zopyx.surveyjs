Changelog
=========


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
