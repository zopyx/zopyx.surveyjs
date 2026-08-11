#!/bin/bash
# Fetch SurveyJS v3 vendor files from unpkg
# See: https://unpkg.com/survey-core@3.0.0-beta.6/

SURVEY_VERSION="3.0.0-beta.6"

wget https://unpkg.com/jspdf@2.5.1/dist/jspdf.umd.min.js
wget https://unpkg.com/plotly.js-dist-min/plotly.min.js
wget https://unpkg.com/survey-analytics/survey.analytics.min.css
wget https://unpkg.com/survey-analytics/survey.analytics.min.js
wget https://unpkg.com/survey-core@${SURVEY_VERSION}/survey-core.min.css
wget https://unpkg.com/survey-core@${SURVEY_VERSION}/survey.core.min.js
wget https://unpkg.com/survey-core@${SURVEY_VERSION}/survey.i18n.min.js
wget https://unpkg.com/survey-core@${SURVEY_VERSION}/themes/contrast-dark.min.js -O contrast-dark.min.js
wget https://unpkg.com/survey-core@${SURVEY_VERSION}/themes/contrast-light.min.js -O contrast-light.min.js
wget https://unpkg.com/survey-core@${SURVEY_VERSION}/themes/index.min.js -O index.min.js
wget https://unpkg.com/survey-creator-core@${SURVEY_VERSION}/survey-creator-core.i18n.min.js
wget https://unpkg.com/survey-creator-core@${SURVEY_VERSION}/survey-creator-core.min.css
wget https://unpkg.com/survey-creator-core@${SURVEY_VERSION}/survey-creator-core.min.js
mkdir -p ui-presets
wget https://unpkg.com/survey-creator-core@${SURVEY_VERSION}/ui-presets/index.min.js -O ui-presets/index.min.js
wget https://unpkg.com/survey-creator-core@${SURVEY_VERSION}/ui-preset-editor.min.js
wget https://unpkg.com/survey-creator-js@${SURVEY_VERSION}/survey-creator-js.min.js
wget https://unpkg.com/survey-js-ui@${SURVEY_VERSION}/survey-js-ui.min.js
wget https://unpkg.com/survey-pdf/survey.pdf.min.js
