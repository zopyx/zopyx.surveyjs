document.addEventListener("DOMContentLoaded", function () {
  const t = window._t || function (msgid) { return msgid; };
  const rawLocale = window.SURVEYJS_I18N_LOCALE || navigator.language || "en";
  const normalizedLocale = String(rawLocale).replace("_", "-");
  const surveyLocale = normalizedLocale.split("-")[0] || "en";
  const accessToken = new URLSearchParams(window.location.search).get("access_token");
  const url = accessToken
    ? ACTUAL_URL + "/get-form-json?access_token=" + encodeURIComponent(accessToken)
    : ACTUAL_URL + "/get-form-json";

  // Load the survey JSON configuration
  fetch(url, {
    credentials: 'same-origin'
  })
    .then((response) => {
      if (!response.ok) {
        throw new Error("Failed to load form");
      }
      return response.json();
    })
    .then((result) => {
      // Create the survey from the loaded JSON
        console.log(result)
      const survey = new Survey.Model(result);
        survey.applyTheme(SurveyTheme.LayeredDarkPanelless);
        survey.locale = surveyLocale;
        if (Survey && Survey.surveyLocalization) {
          Survey.surveyLocalization.currentLocale = surveyLocale;
        }

      // Set up the onComplete handler to save results
      survey.onComplete.add(function (sender) {

        // Save the survey results
        const formData = new FormData();
        formData.append("pollResult", JSON.stringify(sender.data));
        formData.append("_authenticator", CSRF_TOKEN);
        if (typeof AUTH_TOKEN !== "undefined" && AUTH_TOKEN) {
          formData.append("auth_token", AUTH_TOKEN);
        }
        if (accessToken) {
          formData.append("access_token", accessToken);
        }

        fetch(ACTUAL_URL + "/save-poll", {
          method: "POST",
          body: formData,
          credentials: 'same-origin'
        })
          .then((response) => {
            if (!response.ok) {
              throw new Error(t("Save failed"));
            }
          })
          .catch((error) => {
            alert(t("Not saved"));
            console.error(error);
          });
      });

      // Render the survey
      survey.render(document.getElementById("surveyContainer"));
    })
    .catch((error) => {
      console.error(t("Error loading survey:"), error);
    });
});
