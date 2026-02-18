/**
 * PDF generator view logic for @@pdf-generator.
 * Submits generation requests and manages UI state/progress.
 */
document.addEventListener("DOMContentLoaded", function () {
/**
 * @function
 */
  const t = window._t || function (msgid) { return msgid; };
  const button = document.getElementById("generatePdfButton");
  const message = document.getElementById("pdfGeneratorMessage");
  const rawLocale = window.SURVEYJS_I18N_LOCALE || navigator.language || "en";
  const normalizedLocale = String(rawLocale).replace("_", "-");
  const surveyLocale = normalizedLocale.split("-")[0] || "en";

  if (!button || !message) {
    return;
  }

  const surveyPdfLib = window.SurveyPDF || (window.Survey && window.Survey.PDF) || null;
  const SurveyPdfCtor = surveyPdfLib && (surveyPdfLib.SurveyPDF || surveyPdfLib);

  if (!SurveyPdfCtor || !window.Survey) {
    message.textContent = t("SurveyJS PDF library failed to load.");
    message.classList.add("is-error");
    return;
  }

  const formUrl = ACTUAL_URL + "/get-form-json";

/**
 * @function
 */
  button.addEventListener("click", function () {
    message.textContent = t("Preparing PDF...");
    message.classList.remove("is-error");

    fetch(formUrl, { credentials: "same-origin" })
/**
 * @function
 */
      .then((response) => response.json())
/**
 * @function
 */
      .then((formJson) => {
        const surveyPDF = new SurveyPdfCtor(formJson || {}, {
          locale: surveyLocale
        });

        surveyPDF.save("survey.pdf");
        message.textContent = t("PDF download started.");
      })
/**
 * @function
 */
      .catch((error) => {
        console.error(t("Error generating PDF:"), error);
        message.textContent = t("Failed to generate PDF. Please check the console for details.");
        message.classList.add("is-error");
      });
  });
});
