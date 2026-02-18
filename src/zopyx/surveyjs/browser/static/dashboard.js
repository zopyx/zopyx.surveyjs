/**
 * Dashboard view interactions for analytics/summary widgets.
 * Wires UI controls to data refresh and chart rendering.
 */
document.addEventListener("DOMContentLoaded", function () {
/**
 * @function
 */
  const t = window._t || function (msgid) { return msgid; };
  const container = document.getElementById("surveyDashboardContainer");
  const rawLocale = window.SURVEYJS_I18N_LOCALE || navigator.language || "en";
  const normalizedLocale = String(rawLocale).replace("_", "-");
  const surveyLocale = normalizedLocale.split("-")[0] || "en";

  if (!container) {
    return;
  }

  if (!window.Survey || !window.SurveyAnalytics) {
    container.innerHTML = "<div class=\"dashboard-error\">" +
      t("SurveyJS Dashboard libraries failed to load.") + "</div>";
    return;
  }

  const formUrl = ACTUAL_URL + "/get-form-json";
  const resultsUrl = ACTUAL_URL + "/get-polls-json2";

  Promise.all([
/**
 * @function
 */
    fetch(formUrl, { credentials: "same-origin" }).then((response) => response.json()),
/**
 * @function
 */
    fetch(resultsUrl, { credentials: "same-origin" }).then((response) => response.json())
  ])
/**
 * @function
 */
    .then(([formJson, results]) => {
      const survey = new Survey.Model(formJson || {});
      survey.locale = surveyLocale;
      if (Survey && Survey.surveyLocalization) {
        Survey.surveyLocalization.currentLocale = surveyLocale;
      }

      const surveyData = Array.isArray(results) ? results : [];
      if (!surveyData.length) {
        container.innerHTML = "<div class=\"dashboard-empty\">" +
          t("No stored results yet. Once responses are saved, analytics will appear here.") +
          "</div>";
        return;
      }

      const options = {
        allowHideQuestions: true,
        allowShowEmptyCharts: false
      };
      const panel = new SurveyAnalytics.VisualizationPanel(
        survey.getAllQuestions(),
        surveyData,
        options
      );

      panel.render("surveyDashboardContainer");
    })
/**
 * @function
 */
    .catch((error) => {
      console.error(t("Error loading dashboard data:"), error);
      container.innerHTML = "<div class=\"dashboard-error\">" +
        t("Failed to load dashboard data. Please check the console for details.") +
        "</div>";
    });
});
