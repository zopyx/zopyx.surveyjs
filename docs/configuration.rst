=============
Configuration
=============

Survey configuration is split into two levels:

* :doc:`survey-options` — per-survey settings, stored on the Survey item
  itself and edited in the survey's edit form. They control how a single
  survey handles submissions, mails, validation, access, embedding and PDF
  output.
* :doc:`global-options` — site-wide settings, stored in the Plone registry
  and edited in the Forms control panel (Site Setup > Forms). They provide
  defaults and global switches.

Per-survey settings generally take precedence over the global defaults
(notably for the Mail settings: surveys without their own Mail settings
inherit the global ones, surveys with their own settings override them).

.. toctree::
   :maxdepth: 2

   survey-options
   global-options
