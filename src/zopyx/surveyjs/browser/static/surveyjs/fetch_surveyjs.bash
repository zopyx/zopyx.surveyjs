#!/bin/bash
# Fetch SurveyJS v3 vendor files from unpkg
# See: https://unpkg.com/survey-core@3.0.0/

SURVEY_VERSION="3.0.0"

wget -O jspdf.umd.min.js https://unpkg.com/jspdf@2.5.1/dist/jspdf.umd.min.js
wget -O plotly.min.js https://unpkg.com/plotly.js-dist-min/plotly.min.js
wget -O survey.analytics.min.css https://unpkg.com/survey-analytics@${SURVEY_VERSION}/survey.analytics.min.css
wget -O survey.analytics.min.js https://unpkg.com/survey-analytics@${SURVEY_VERSION}/survey.analytics.min.js
wget -O survey-core.min.css https://unpkg.com/survey-core@${SURVEY_VERSION}/survey-core.min.css
wget -O survey.core.min.js https://unpkg.com/survey-core@${SURVEY_VERSION}/survey.core.min.js
wget -O survey.i18n.min.js https://unpkg.com/survey-core@${SURVEY_VERSION}/survey.i18n.min.js
wget -O contrast-dark.min.js https://unpkg.com/survey-core@${SURVEY_VERSION}/themes/contrast-dark.min.js
wget -O contrast-light.min.js https://unpkg.com/survey-core@${SURVEY_VERSION}/themes/contrast-light.min.js
wget -O index.min.js https://unpkg.com/survey-core@${SURVEY_VERSION}/themes/index.min.js
wget -O survey-creator-core.i18n.min.js https://unpkg.com/survey-creator-core@${SURVEY_VERSION}/survey-creator-core.i18n.min.js
wget -O survey-creator-core.min.css https://unpkg.com/survey-creator-core@${SURVEY_VERSION}/survey-creator-core.min.css
wget -O survey-creator-core.min.js https://unpkg.com/survey-creator-core@${SURVEY_VERSION}/survey-creator-core.min.js
mkdir -p ui-presets
wget -O ui-presets/index.min.js https://unpkg.com/survey-creator-core@${SURVEY_VERSION}/ui-presets/index.min.js
wget -O ui-preset-editor.min.js https://unpkg.com/survey-creator-core@${SURVEY_VERSION}/ui-preset-editor.min.js
wget -O survey-creator-js.min.js https://unpkg.com/survey-creator-js@${SURVEY_VERSION}/survey-creator-js.min.js
wget -O survey-js-ui.min.js https://unpkg.com/survey-js-ui@${SURVEY_VERSION}/survey-js-ui.min.js
wget -O survey.pdf.min.js https://unpkg.com/survey-pdf@${SURVEY_VERSION}/survey.pdf.min.js
