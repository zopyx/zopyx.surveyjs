document.addEventListener("DOMContentLoaded", function () {
  const t = window._t || function (msgid) { return msgid; };
  const rawLocale = window.SURVEYJS_I18N_LOCALE || navigator.language || "en";
  const normalizedLocale = String(rawLocale).replace("_", "-");
  const surveyLocale = normalizedLocale.split("-")[0] || "en";
  const url = ACTUAL_URL + "/@@get-template-json";
  const surveyContainer = document.getElementById("surveyContainer");
  const errorContainer = document.getElementById("surveyTemplateError");
  const errorMessage = document.getElementById("surveyTemplateErrorMessage");
  const fullscreenToggle = document.getElementById("surveyViewerFullscreenToggle");
  const fullscreenClass = "survey-viewer-fullscreen";
  const fullscreenParam = new URLSearchParams(window.location.search).get("fullscreen");

  const showError = function (message) {
    if (surveyContainer) {
      surveyContainer.style.display = "none";
    }
    if (errorMessage) {
      errorMessage.textContent = message;
    }
    if (errorContainer) {
      errorContainer.hidden = false;
    }
  };

  const setFullscreen = function (enabled) {
    document.body.classList.toggle(fullscreenClass, Boolean(enabled));
    if (!fullscreenToggle) {
      return;
    }
    fullscreenToggle.textContent = enabled ? t("Exit fullscreen") : t("Fullscreen");
    fullscreenToggle.setAttribute("aria-pressed", enabled ? "true" : "false");
  };

  if (fullscreenToggle) {
    fullscreenToggle.addEventListener("click", function (event) {
      event.preventDefault();
      const isFullscreen = document.body.classList.contains(fullscreenClass);
      setFullscreen(!isFullscreen);
    });
    document.addEventListener("keydown", function (event) {
      if (event.key === "Escape" && document.body.classList.contains(fullscreenClass)) {
        setFullscreen(false);
      }
    });
  }

  if (fullscreenParam === "1" || fullscreenParam === "true" || fullscreenParam === "yes") {
    setFullscreen(true);
  }

  fetch(url, {
    credentials: "same-origin"
  })
    .then((response) => {
      if (!response.ok) {
        return response.json().then((payload) => {
          const error = new Error("Failed to load template");
          error.payload = payload;
          throw error;
        }).catch(() => {
          throw new Error("Failed to load template");
        });
      }
      return response.json();
    })
    .then((result) => {
      const survey = new Survey.Model(result);
      survey.applyTheme(SurveyTheme.LayeredDarkPanelless);
      survey.locale = surveyLocale;
      if (Survey && Survey.surveyLocalization) {
        Survey.surveyLocalization.currentLocale = surveyLocale;
      }
      if (surveyContainer) {
        survey.render(surveyContainer);
      }
    })
    .catch((error) => {
      const message = (error && error.payload && error.payload.message)
        ? error.payload.message
        : t("Template JSON could not be loaded.");
      showError(message);
      console.error(error);
    });
});
