---
title: "Installation"
sidebar_position: 3
---

This package is intended for Buildout-based Plone projects.

## Buildout

1.  Add `zopyx.surveyjs` to your buildout eggs and rerun buildout.

    ``` ini
    [buildout]
    eggs +=
        zopyx.surveyjs
    ```

2.  Restart Plone and install the add-on in the Add-ons control panel.

## Optional components

Relational result storage  
The SQLModel backend supports SQLite, PostgreSQL, and MySQL. Ensure the
configured database URI is reachable by the Plone process (default:
`sqlite:///var/surveyjs-results.db`). Each row stores the Plone
`site_id` to support multi-site deployments.

External SurveyJS validation (Deno binary)  
Build the Deno validator in `data-validation/` and place the binary in
`data-validation/dist`. See `data-validation/README.md` for details.

AI Generator  
The AI Generator uses the Python `llm` package and optionally an API key
or a local Ollama server. See `ai` for configuration.
