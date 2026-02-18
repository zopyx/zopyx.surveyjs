/**
 * PDF form view bootstrapping for @@pdf-form.
 * Loads the form JSON and renders the PDF-capable SurveyJS view.
 */
document.addEventListener("DOMContentLoaded", function () {
/**
 * @function
 */
  const t = window._t || function (msgid) { return msgid; };
  const rawLocale = window.SURVEYJS_I18N_LOCALE || navigator.language || "en";
  const normalizedLocale = String(rawLocale).replace("_", "-");
  const surveyLocale = normalizedLocale.split("-")[0] || "en";
  const url = ACTUAL_URL + "/@@get-pdf-form-json";

/**
 * @function
 */
  function parseFilenameFromHeader(headerValue) {
    if (!headerValue) {
      return null;
    }
    const match = headerValue.match(/filename="([^"]+)"/i);
    return match ? match[1] : null;
  }

  fetch(url, {
    credentials: "same-origin"
  })
/**
 * @function
 */
    .then((response) => {
      if (!response.ok) {
        throw new Error(t("Unable to load PDF form."));
      }
      return response.json();
    })
/**
 * @function
 */
    .then((result) => {
      const survey = new Survey.Model(result);
      survey.applyTheme(SurveyTheme.LayeredDarkPanelless);
      survey.locale = surveyLocale;
      if (Survey && Survey.surveyLocalization) {
        Survey.surveyLocalization.currentLocale = surveyLocale;
      }

/**
 * @function
 */
      survey.onComplete.add(function (sender) {
        const formData = new FormData();
        formData.append("pollResult", JSON.stringify(sender.data));
        formData.append("_authenticator", CSRF_TOKEN);
        const authToken =
          (typeof AUTH_TOKEN_PDF !== "undefined" && AUTH_TOKEN_PDF) ||
          (typeof AUTH_TOKEN !== "undefined" && AUTH_TOKEN) ||
          "";
        if (authToken) {
          formData.append("auth_token", authToken);
        }

        fetch(ACTUAL_URL + "/@@fill-pdf-form", {
          method: "POST",
          body: formData,
          credentials: "same-origin"
        })
/**
 * @function
 */
          .then((response) => {
            if (!response.ok) {
/**
 * @function
 */
              return response.json().then((data) => {
                throw new Error(data.message || t("PDF generation failed"));
              });
            }
            const filename = parseFilenameFromHeader(
              response.headers.get("Content-Disposition")
            );
/**
 * @function
 */
            return response.blob().then((blob) => ({ blob, filename }));
          })
/**
 * @function
 */
          .then(({ blob, filename }) => {
            const downloadUrl = URL.createObjectURL(blob);
            const link = document.createElement("a");
            link.href = downloadUrl;
            link.download = filename || "filled-form.pdf";
            document.body.appendChild(link);
            link.click();
            link.remove();
/**
 * @function
 */
            setTimeout(() => URL.revokeObjectURL(downloadUrl), 1000);
          })
/**
 * @function
 */
          .catch((error) => {
            alert(error.message || t("PDF generation failed"));
            console.error(error);
          });
      });

      survey.render(document.getElementById("surveyContainer"));
    })
/**
 * @function
 */
    .catch((error) => {
      console.error(t("Error loading PDF form:"), error);
    });
});
