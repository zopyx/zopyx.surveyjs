/**
 * Survey viewer logic for @@viewer and @@viewer_embed.
 * Handles trusted access, fullscreen, and submission flow.
 */
/**
 * Initialize the SurveyJS viewer when the DOM is ready.
 * @param {Event} event
 */
function handleViewerReady(event) {
  /**
   * Default translation function fallback.
   * @param {string} msgid
   * @returns {string}
   */
  const defaultTranslate = function (msgid) {
    return msgid;
  };
  const t = window._t || defaultTranslate;
  const rawLocale = window.SURVEYJS_I18N_LOCALE || navigator.language || "en";
  const normalizedLocale = String(rawLocale).replace("_", "-");
  const surveyLocale = normalizedLocale.split("-")[0] || "en";
  const viewerConfigEl = document.getElementById("survey-viewer-config");
  let viewerConfig = {};
  if (viewerConfigEl && viewerConfigEl.textContent) {
    try {
      viewerConfig = JSON.parse(viewerConfigEl.textContent) || {};
    } catch (error) {
      console.error("Failed to parse viewer config", error);
    }
  }
  const trustedAccessEnabled = typeof viewerConfig.trustedAccessEnabled !== "undefined"
    ? Boolean(viewerConfig.trustedAccessEnabled)
    : Boolean(window.SURVEY_TRUSTED_ACCESS_ENABLED);
  const canManage = typeof viewerConfig.canManage !== "undefined"
    ? Boolean(viewerConfig.canManage)
    : Boolean(window.SURVEY_CAN_MANAGE);
  /**
   * Parse/normalize a locale list from config.
   * @param {unknown} value
   * @returns {string[]}
   */
  const parseLocales = function (value) {
    if (!Array.isArray(value)) {
      return [];
    }
    const seen = {};
    return value
      .map(function (item) {
        const raw = item == null ? "" : String(item);
        const normalized = raw.trim().replace("_", "-");
        return normalized.split("-")[0] || "";
      })
      .filter(function (item) {
        if (!item || seen[item]) {
          return false;
        }
        seen[item] = true;
        return true;
      });
  };
  const configuredSurveyLanguages = parseLocales(viewerConfig.surveyLanguages);
  const configuredSurveyLanguageLabels = (
    viewerConfig && viewerConfig.surveyLanguageLabels &&
    typeof viewerConfig.surveyLanguageLabels === "object"
  ) ? viewerConfig.surveyLanguageLabels : {};
  const urlParams = new URLSearchParams(window.location.search);
  // Support both auth_token (token store) and access_token (cached tokens)
  const accessToken = urlParams.get("auth_token") || urlParams.get("access_token");
  const tokenParam = urlParams.has("auth_token") ? "auth_token" : "access_token";
  const url = accessToken
    ? ACTUAL_URL + "/get-form-json?" + tokenParam + "=" + encodeURIComponent(accessToken)
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
  const fullscreenToggle = document.getElementById("surveyViewerFullscreenToggle");
  const languageSelector = document.getElementById("surveyLanguageSelector");
  const fullscreenClass = "survey-viewer-fullscreen";
  const fullscreenParam = new URLSearchParams(window.location.search).get("fullscreen");
  const urlLocaleParam = new URLSearchParams(window.location.search).get("locale");
  let currentSurvey = null;

  const trustedAccessMessages = {
    trusted_access_token_missing: t("This form requires a trusted access link. Please use the link provided by the form owner."),
    trusted_access_token_invalid: t("This trusted access link is invalid or has expired."),
    trusted_access_token_revoked: t("This trusted access link has been revoked."),
    trusted_access_form_mismatch: t("This trusted access link does not match this form."),
    trusted_access_cache_unavailable: t("Trusted access service is temporarily unavailable. Please try again later."),
    trusted_tokens_token_invalid: t("This access token is invalid or has already been used."),
    trusted_tokens_store_unavailable: t("Token store service is temporarily unavailable. Please try again later."),
  };

  /**
   * Show the trusted-access error state and hide the survey container.
   * @param {string} message
   */
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
      const messageEl = errorContainer.querySelector("#surveyAccessErrorMessage");
      if (messageEl) {
        messageEl.textContent = message;
      } else {
        errorContainer.textContent = message;
      }
      errorContainer.hidden = false;
    }
  };

  /**
   * Toggle fullscreen mode for the viewer container.
   * @param {boolean} enabled
   */
  const setFullscreen = function (enabled) {
    document.body.classList.toggle(fullscreenClass, Boolean(enabled));
    if (!fullscreenToggle) {
      return;
    }
    fullscreenToggle.textContent = enabled ? t("Exit fullscreen") : t("Fullscreen");
    fullscreenToggle.setAttribute("aria-pressed", enabled ? "true" : "false");
  };

  if (fullscreenToggle) {
    /**
     * Handle fullscreen toggle click.
     * @param {MouseEvent} event
     */
    const handleFullscreenClick = function (event) {
      event.preventDefault();
      const isFullscreen = document.body.classList.contains(fullscreenClass);
      setFullscreen(!isFullscreen);
    };
    /**
     * Exit fullscreen on Escape.
     * @param {KeyboardEvent} event
     */
    const handleFullscreenKeydown = function (event) {
      if (event.key === "Escape" && document.body.classList.contains(fullscreenClass)) {
        setFullscreen(false);
      }
    };
    fullscreenToggle.addEventListener("click", handleFullscreenClick);
    document.addEventListener("keydown", handleFullscreenKeydown);
  }

  if (fullscreenParam === "1" || fullscreenParam === "true" || fullscreenParam === "yes") {
    setFullscreen(true);
  }

  /**
   * Copy the trusted access URL to clipboard and show a confirmation.
   * @param {string} text
   */
  const copyTrustedAccessUrl = function (text) {
    if (!text) {
      return;
    }
    /**
     * Update UI to confirm a copy operation.
     */
    /**
     * Clear the copy confirmation message.
     */
    const clearCopyMessage = function () {
      trustedAccessMessage.textContent = "";
    };
    /**
     * Show the copy confirmation message.
     */
    const confirmCopy = function () {
      if (trustedAccessMessage) {
        trustedAccessMessage.textContent = t("Copied");
        window.setTimeout(clearCopyMessage, 2000);
      }
    };
    /**
     * Handle clipboard API errors (fallback to legacy copy).
     * @param {Error} error
     */
    const handleClipboardError = function (error) {
      /* fallback below */
    };
    if (navigator.clipboard && navigator.clipboard.writeText) {
      navigator.clipboard.writeText(text).then(confirmCopy).catch(handleClipboardError);
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
        /**
         * Validate trusted access token response.
         * @param {Response} response
         * @returns {Promise<Object>}
         */
        .then(function handleTrustedAccessResponse(response) {
          if (!response.ok) {
            throw new Error("Failed to load trusted access link");
          }
          return response.json();
        })
        /**
         * Apply trusted access token data to the UI.
         * @param {Object} data
         */
        .then(function handleTrustedAccessData(data) {
          const urlValue = data.url || "";
          trustedAccessUrl.textContent = urlValue || "-";
          trustedAccessUrl.href = urlValue || "#";
          trustedAccessToken.textContent = data.token || "-";
          trustedAccessExpires.textContent = data.expires_at || "-";
          if (trustedAccessCopy && urlValue) {
            /**
             * Copy trusted access URL from the panel.
             * @param {MouseEvent} event
             */
            const handleTrustedAccessCopy = function (event) {
              copyTrustedAccessUrl(urlValue);
            };
            trustedAccessCopy.addEventListener("click", handleTrustedAccessCopy);
          }
        })
        /**
         * Handle trusted access token failures.
         * @param {Error} error
         */
        .catch(function handleTrustedAccessError(error) {
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
  
  // Hide container initially if token is present - will be shown on successful load
  if (trustedAccessEnabled && accessToken && surveyContainer) {
    surveyContainer.classList.add("survey-container-hidden");
    surveyContainer.setAttribute("hidden", "hidden");
    surveyContainer.style.display = "none";
  }

  // Load the survey JSON configuration
  fetch(url, {
    credentials: 'same-origin'
  })
    /**
     * Parse the form JSON payload from the response.
     * @param {Response} response
     * @returns {Promise<Object>}
     */
    .then(function handleFormResponse(response) {
      if (!response.ok) {
        return response.json().then(
          /**
           * Attach payload details to the load error.
           * @param {Object} payload
           * @returns {never}
           */
          function handleErrorPayload(payload) {
          const error = new Error("Failed to load form");
          error.status = response.status;
          error.payload = payload;
          throw error;
        }).catch(
          /**
           * Fallback when error payload parsing fails.
           * @returns {never}
           */
          function handleErrorPayloadFailure() {
          throw new Error("Failed to load form");
        });
      }
      return response.json();
    })
    /**
     * Initialize SurveyJS with the loaded form definition.
     * @param {Object} result
     */
    .then(function handleFormLoaded(result) {
      // Create the survey from the loaded JSON
      const survey = new Survey.Model(result);
      currentSurvey = survey;
      survey.applyTheme(SurveyTheme.LayeredDarkPanelless);
      
      // Determine effective locale: URL param > survey locale > browser locale
      const effectiveLocale = urlLocaleParam || result.locale || surveyLocale;
      survey.locale = effectiveLocale;
      if (Survey && Survey.surveyLocalization) {
        Survey.surveyLocalization.currentLocale = effectiveLocale;
      }
      
      // Set up language selector
      if (languageSelector) {
        // Use survey_languages (viewer config) as the source of truth. Only
        // fall back to form locales when the field is not configured.
        const availableLocales = configuredSurveyLanguages.length > 0
          ? configuredSurveyLanguages
          : (result.locales || [result.locale || "en"]);
        // Populate selector with available locales
        languageSelector.innerHTML = "";
        availableLocales.forEach(function(locale) {
          const option = document.createElement("option");
          option.value = locale;
          const localeLabel = configuredSurveyLanguageLabels[locale];
          if (!localeLabel) {
            console.warn(
              "Missing survey language label from vocabulary for locale:",
              locale
            );
          }
          option.textContent = localeLabel || locale;
          if (locale === effectiveLocale) {
            option.selected = true;
          }
          languageSelector.appendChild(option);
        });
        
        // Show selector only when survey_languages is configured and has
        // multiple values.
        languageSelector.style.display = (
          configuredSurveyLanguages.length > 1 && availableLocales.length > 1
        ) ? "" : "none";
        
        // Handle language change
        languageSelector.addEventListener("change", function(event) {
          const selectedLocale = event.target.value;
          if (currentSurvey) {
            currentSurvey.locale = selectedLocale;
            // Update URL without reloading
            const url = new URL(window.location.href);
            url.searchParams.set("locale", selectedLocale);
            window.history.replaceState({}, "", url);
          }
        });
      }

      // Check if fillable PDF is available
      const hasFillablePdf = Boolean(viewerConfig.hasFillablePdf);
      
      // Set up the onComplete handler to save results
      /**
       * Persist survey results when the form completes.
       * @param {Survey.Model} sender
       */
      const handleSurveyComplete = function (sender) {

        // Save the survey results
        const formData = new FormData();
        formData.append("pollResult", JSON.stringify(sender.data));
        formData.append("_authenticator", CSRF_TOKEN);
        if (typeof AUTH_TOKEN !== "undefined" && AUTH_TOKEN) {
          formData.append("auth_token", AUTH_TOKEN);
        }
        if (accessToken) {
          // Use the same token parameter name that was in the URL
          formData.append(tokenParam, accessToken);
        }

        fetch(ACTUAL_URL + "/save-poll", {
          method: "POST",
          body: formData,
          credentials: 'same-origin'
        })
          /**
           * Validate save response.
           * @param {Response} response
           */
          .then(function handleSaveResponse(response) {
            if (!response.ok) {
              throw new Error(t("Save failed"));
            }
          })
          /**
           * Handle save errors.
           * @param {Error} error
           */
          .catch(function handleSaveError(error) {
            alert(t("Not saved"));
            console.error(error);
          });
      };
      survey.onComplete.add(handleSurveyComplete);

      // Add Fill PDF button if a fillable PDF is available
      if (hasFillablePdf) {
        // Add custom "Fill PDF" navigation button
        survey.addNavigationItem({
          id: "fill-pdf-btn",
          title: t("Fill PDF"),
          action: function() {
            // Get current survey data
            const surveyData = survey.data || {};
            
            // Create a form to submit to the fillable_pdf endpoint
            const form = document.createElement("form");
            form.method = "POST";
            form.action = ACTUAL_URL + "/@@fillable-pdf-fill";
            form.target = "_blank";
            
            // Add CSRF token
            const csrfInput = document.createElement("input");
            csrfInput.type = "hidden";
            csrfInput.name = "_authenticator";
            csrfInput.value = CSRF_TOKEN;
            form.appendChild(csrfInput);
            
            // Add auth token if available
            if (typeof AUTH_TOKEN !== "undefined" && AUTH_TOKEN) {
              const authInput = document.createElement("input");
              authInput.type = "hidden";
              authInput.name = "auth_token";
              authInput.value = AUTH_TOKEN;
              form.appendChild(authInput);
            }
            
            // Add access token if available
            if (accessToken) {
              const accessInput = document.createElement("input");
              accessInput.type = "hidden";
              accessInput.name = "access_token";
              accessInput.value = accessToken;
              form.appendChild(accessInput);
            }
            
            // Add survey data as hidden fields matching PDF field names
            Object.keys(surveyData).forEach(function(key) {
              const value = surveyData[key];
              if (value !== null && value !== undefined) {
                const input = document.createElement("input");
                input.type = "hidden";
                input.name = key;
                // Handle arrays/objects by converting to string
                if (typeof value === "object") {
                  input.value = JSON.stringify(value);
                } else {
                  input.value = String(value);
                }
                form.appendChild(input);
              }
            });
            
            // Append form to body, submit, then remove
            document.body.appendChild(form);
            form.submit();
            document.body.removeChild(form);
          }
        });
      }

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
    /**
     * Handle form load failures.
     * @param {Error} error
     */
    .catch(function handleFormLoadError(error) {
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
}

document.addEventListener("DOMContentLoaded", handleViewerReady);
