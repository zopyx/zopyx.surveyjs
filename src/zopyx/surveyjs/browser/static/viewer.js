document.addEventListener("DOMContentLoaded", function () {
  const t = window._t || function (msgid) { return msgid; };
  const rawLocale = window.SURVEYJS_I18N_LOCALE || navigator.language || "en";
  const normalizedLocale = String(rawLocale).replace("_", "-");
  const surveyLocale = normalizedLocale.split("-")[0] || "en";
  const trustedAccessEnabled = Boolean(window.SURVEY_TRUSTED_ACCESS_ENABLED);
  const canManage = Boolean(window.SURVEY_CAN_MANAGE);
  const accessToken = new URLSearchParams(window.location.search).get("access_token");
  const url = accessToken
    ? ACTUAL_URL + "/get-form-json?access_token=" + encodeURIComponent(accessToken)
    : ACTUAL_URL + "/get-form-json";
  const surveyContainer = document.getElementById("surveyContainer");
  const statusBar = document.querySelector(".survey-status-bar");
  const errorContainer = document.getElementById("surveyAccessError");
  const trustedAccessPanel = document.getElementById("surveyTrustedAccess");
  const trustedAccessUrl = document.getElementById("surveyTrustedAccessUrl");
  const trustedAccessToken = document.getElementById("surveyTrustedAccessToken");
  const trustedAccessExpires = document.getElementById("surveyTrustedAccessExpires");
  const trustedAccessCopy = document.getElementById("surveyTrustedAccessCopy");
  const trustedAccessMessage = document.getElementById("surveyTrustedAccessMessage");

  const trustedAccessMessages = {
    trusted_access_token_missing: t("This form requires a trusted access link. Please use the link provided by the form owner."),
    trusted_access_token_invalid: t("This trusted access link is invalid or has expired."),
    trusted_access_token_revoked: t("This trusted access link has been revoked."),
    trusted_access_form_mismatch: t("This trusted access link does not match this form."),
    trusted_access_cache_unavailable: t("Trusted access service is temporarily unavailable. Please try again later."),
  };

  const showAccessError = function (message) {
    if (surveyContainer) {
      surveyContainer.classList.add("survey-container-hidden");
      surveyContainer.setAttribute("hidden", "hidden");
      surveyContainer.style.display = "none";
    }
    if (statusBar) {
      statusBar.hidden = true;
    }
    if (errorContainer) {
      errorContainer.textContent = message;
      errorContainer.hidden = false;
    }
  };

  const copyTrustedAccessUrl = function (text) {
    if (!text) {
      return;
    }
    const confirmCopy = function () {
      if (trustedAccessMessage) {
        trustedAccessMessage.textContent = t("Copied");
        window.setTimeout(function () {
          trustedAccessMessage.textContent = "";
        }, 2000);
      }
    };
    if (navigator.clipboard && navigator.clipboard.writeText) {
      navigator.clipboard.writeText(text).then(confirmCopy).catch(function () {
        /* fallback below */
      });
    } else {
      if (document.queryCommandSupported && document.queryCommandSupported("copy") === false) {
        return;
      }
      const input = document.createElement("textarea");
      input.value = text;
      input.setAttribute("readonly", "readonly");
      input.style.position = "absolute";
      input.style.left = "-9999px";
      document.body.appendChild(input);
      input.select();
      try {
        document.execCommand("copy");
        confirmCopy();
      } catch (error) {
        console.error(error);
      } finally {
        document.body.removeChild(input);
      }
    }
  };

  if (trustedAccessPanel && trustedAccessUrl && trustedAccessToken && trustedAccessExpires) {
    const tokenEndpoint = trustedAccessPanel.getAttribute("data-token-endpoint");
    if (tokenEndpoint) {
      fetch(tokenEndpoint, { credentials: "same-origin" })
        .then((response) => {
          if (!response.ok) {
            throw new Error("Failed to load trusted access link");
          }
          return response.json();
        })
        .then((data) => {
          const urlValue = data.url || "";
          trustedAccessUrl.textContent = urlValue || "-";
          trustedAccessUrl.href = urlValue || "#";
          trustedAccessToken.textContent = data.token || "-";
          trustedAccessExpires.textContent = data.expires_at || "-";
          if (trustedAccessCopy && urlValue) {
            trustedAccessCopy.addEventListener("click", function () {
              copyTrustedAccessUrl(urlValue);
            });
          }
        })
        .catch((error) => {
          if (trustedAccessUrl) {
            trustedAccessUrl.textContent = t("Failed to load trusted access link.");
          }
          console.error(error);
        });
    }
  }

  if (trustedAccessEnabled && !accessToken && !canManage) {
    showAccessError(
      trustedAccessMessages.trusted_access_token_missing
    );
    return;
  }

  // Load the survey JSON configuration
  fetch(url, {
    credentials: 'same-origin'
  })
    .then((response) => {
      if (!response.ok) {
        return response.json().then((payload) => {
          const error = new Error("Failed to load form");
          error.status = response.status;
          error.payload = payload;
          throw error;
        }).catch(() => {
          throw new Error("Failed to load form");
        });
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
      if (surveyContainer) {
        survey.render(surveyContainer);
        if (!trustedAccessEnabled || (trustedAccessEnabled && (accessToken || canManage))) {
          surveyContainer.classList.remove("survey-container-hidden");
          surveyContainer.removeAttribute("hidden");
          surveyContainer.style.display = "";
        }
      }
    })
    .catch((error) => {
      const errorKey = error && error.payload && error.payload.error;
      if (trustedAccessEnabled && errorKey && trustedAccessMessages[errorKey]) {
        showAccessError(trustedAccessMessages[errorKey]);
        return;
      }
      if (trustedAccessEnabled && errorKey === "trusted_access_token_missing") {
        showAccessError(trustedAccessMessages.trusted_access_token_missing);
        return;
      }
      console.error(t("Error loading survey:"), error);
    });
});
