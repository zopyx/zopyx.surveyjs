/**
 * Survey add wizard for @@survey-add.
 * Renders the add form and posts data to create a survey.
 */
(function () {
  const container = document.getElementById("survey-add-widget");
  if (!container || typeof Survey === "undefined") {
    return;
  }

  const t = window._t || function (msgid) { return msgid; };

  const schemaUrl = container.dataset.schemaUrl;
  const themeName = container.dataset.theme || "flat";
  const theme = themeName === "flach" ? "flat" : themeName;
  const initialDataScript = document.getElementById("survey-add-initial-data");
  const hiddenForm = document.getElementById("survey-add-hidden-form");
  const submitButton = document.getElementById("survey-add-submit");
  let currentSurvey = null;
  let heightResetTimer = null;
  let pendingHeightSyncFrame = null;
  let pendingHeightSyncTimer = null;
  let isSubmitting = false;
  const datasetLocale = container.dataset.surveyLanguage;

/**
 * @function
 */
  function syncContainerHeight() {
    if (heightResetTimer) {
      window.clearTimeout(heightResetTimer);
      heightResetTimer = null;
    }

    // Natural flow: no fixed/min-height reservation. A reserved pixel height
    // either clips the footer (Prev/Next) when the rendered content grows
    // (validation errors, visibleIf toggles, resize), or leaves a gap above
    // "Save Settings" when the content shrinks (page switch back to a shorter
    // page, hidden conditional fields). Letting the container follow its
    // content eliminates both failure modes.
    container.style.transition = "";
    container.style.height = "auto";
    container.style.minHeight = "0";
  }

/**
 * @function
 */
  function scheduleContainerHeightSync() {
    if (pendingHeightSyncFrame) {
      window.cancelAnimationFrame(pendingHeightSyncFrame);
      pendingHeightSyncFrame = null;
    }
    if (pendingHeightSyncTimer) {
      window.clearTimeout(pendingHeightSyncTimer);
      pendingHeightSyncTimer = null;
    }
    pendingHeightSyncFrame = window.requestAnimationFrame(function () {
      pendingHeightSyncFrame = null;
      window.requestAnimationFrame(function () {
        syncContainerHeight();
      });
    });
    // SurveyJS may apply visibility/layout changes asynchronously; re-measure once more.
    pendingHeightSyncTimer = window.setTimeout(function () {
      pendingHeightSyncTimer = null;
      syncContainerHeight();
    }, 260);
  }

  let initialData = {};
  if (initialDataScript) {
    try {
      initialData = JSON.parse(initialDataScript.textContent || "{}");
    } catch (error) {
      console.warn(t("Survey add form: unable to parse initial data"), error);
    }
  }

/**
 * @function
 */
  function normalizeLocale(value) {
    const raw = value == null ? "" : String(value);
    return raw.trim().replace("_", "-");
  }

/**
 * @function
 */
  function toSurveyLocale(value) {
    const normalized = normalizeLocale(value);
    const base = normalized.split("-")[0];
    return base || "en";
  }

/**
 * @function
 */
  function getSurveyLocale() {
    const initialLocale =
      (initialData && (initialData.language || initialData.locale || initialData.defaultLanguage)) ||
      "";
    const fallbackLocale =
      datasetLocale ||
      initialLocale ||
      window.SURVEYJS_I18N_LOCALE ||
      navigator.language ||
      "en";
    return toSurveyLocale(fallbackLocale);
  }

/**
 * @function
 */
  function submitData(data) {
    if (!hiddenForm) {
      return;
    }
    const payload = data || {};
    const titleField = hiddenForm.querySelector('input[name="title"]');
    const descriptionField = hiddenForm.querySelector('input[name="description"]');
    if (titleField) {
      titleField.value = payload.title || "";
    }
    if (descriptionField) {
      descriptionField.value = payload.description || "";
    }
    const payloadField = hiddenForm.querySelector('input[name="payload"]');
    if (payloadField) {
      try {
        payloadField.value = JSON.stringify(payload);
      } catch (error) {
        console.warn("Survey add form: unable to serialize payload", error);
        payloadField.value = "";
      }
    }
    hiddenForm.submit();
  }

/**
 * @function
 */
  function getDynamicSurveyLanguageChoices() {
    if (!initialData || !Array.isArray(initialData.__survey_languages_choices)) {
      return [];
    }
    return initialData.__survey_languages_choices.filter(function (item) {
      return item && item.value && item.text;
    });
  }

  function getDynamicAIModelChoices() {
    if (!initialData || !Array.isArray(initialData.__ai_model_choices)) {
      return [];
    }
    return initialData.__ai_model_choices.filter(function (item) {
      return item && item.value && item.text;
    });
  }

/**
 * @function
 */
  function applyDynamicSchemaChoices(schema) {
    if (!schema || !Array.isArray(schema.pages)) {
      return;
    }
    const languageChoices = getDynamicSurveyLanguageChoices();
    const aiModelChoices = getDynamicAIModelChoices();
    schema.pages.forEach(function (page) {
      if (!page || !Array.isArray(page.elements)) {
        return;
      }
      page.elements.forEach(function (element) {
        if (element && element.name === "survey_languages" && languageChoices.length) {
          element.choices = languageChoices;
        }
        if (element && element.name === "ai_model" && aiModelChoices.length) {
          element.choices = aiModelChoices;
        }
      });
    });
  }

/**
 * @function
 */
  function updateSubmitState(forceDisable) {
    if (!submitButton) {
      return;
    }
    if (forceDisable || isSubmitting || !currentSurvey) {
      submitButton.disabled = true;
      submitButton.setAttribute("aria-disabled", "true");
      return;
    }
    let isValid = true;
    try {
      isValid = currentSurvey.validate(false, true);
    } catch (error) {
      isValid = false;
    }
    submitButton.disabled = !isValid;
    submitButton.setAttribute("aria-disabled", isValid ? "false" : "true");
  }

/**
 * @function
 */
  function renderSurvey(schema) {
    const surveyLocale = getSurveyLocale();
    applyDynamicSchemaChoices(schema);
/**
 * @function
 */
    if (Survey.StylesManager && typeof Survey.StylesManager.applyTheme === "function") {
      try {
        Survey.StylesManager.applyTheme(theme);
      } catch (error) {
        console.warn("Survey add form: unable to apply theme, falling back to index", error);
        Survey.StylesManager.applyTheme("index");
      }
    }
    const survey = new Survey.Model(schema);
    survey.fitToContainer = false;
    survey.locale = surveyLocale;
    if (Survey && Survey.surveyLocalization) {
      Survey.surveyLocalization.currentLocale = surveyLocale;
    }
    currentSurvey = survey;
    if (initialData && Object.keys(initialData).length > 0) {
      const surveyData = Object.assign({}, initialData);
      delete surveyData.__survey_languages_choices;
      delete surveyData.__ai_model_choices;
      survey.data = surveyData;
    }
/**
 * @function
 */
    survey.onComplete.add(function (sender) {
      isSubmitting = true;
      updateSubmitState(true);
      submitData(sender.data || {});
    });
/**
 * @function
 */
    if (survey.onValueChanged && typeof survey.onValueChanged.add === "function") {
/**
 * @function
 */
      survey.onValueChanged.add(function () {
        updateSubmitState(false);
        scheduleContainerHeightSync();
      });
    }
/**
 * @function
 */
    if (survey.onValidated && typeof survey.onValidated.add === "function") {
/**
 * @function
 */
      survey.onValidated.add(function () {
        updateSubmitState(false);
        // Validation errors grow the page (error boxes under questions);
        // re-sync so the footer (Prev/Next) stays visible.
        scheduleContainerHeightSync();
      });
    }
/**
 * @function
 */
    survey.onCurrentPageChanging.add(function (sender, options) {
      if (options && options.allow === false) {
        options.allow = true;
      }
      if (options) {
        options.allowChanging = true;
        options.cancel = false;
      }
    });
/**
 * @function
 */
    survey.onCurrentPageChanging.add(function (sender, options) {
      if (options) {
        options.allow = true;
        options.allowChanging = true;
        options.cancel = false;
      }
    });
/**
 * @function
 */
    survey.onAfterRenderSurvey.add(function () {
      container.classList.add("is-ready");
      container.style.minHeight = "0";
      syncContainerHeight(false);
      updateSubmitState(false);
    });
/**
 * @function
 */
    survey.onAfterRenderPage.add(function () {
      scheduleContainerHeightSync();
    });
/**
 * @function
 */
    survey.onCurrentPageChanged.add(function () {
      updateSubmitState(false);
      scheduleContainerHeightSync();
    });
    survey.render(container);
  }

/**
 * @function
 */
  function showError(message) {
    container.classList.remove("is-ready");
    container.innerHTML =
      '<div class="survey-add-error-message">' +
      (message || t("We cannot load the form right now. Please reload the page.")) +
      "</div>";
  }

  if (!schemaUrl) {
    showError(t("Missing form definition."));
    return;
  }

  fetch(schemaUrl, { cache: "no-store" })
/**
 * @function
 */
    .then(function (response) {
      if (!response.ok) {
        throw new Error("Schema fetch failed");
      }
      return response.json();
    })
    .then(renderSurvey)
/**
 * @function
 */
    .catch(function (error) {
      console.error(t("Survey add form failed"), error);
      showError();
    });

  if (submitButton) {
    submitButton.disabled = true;
    submitButton.setAttribute("aria-disabled", "true");
/**
 * @function
 */
    submitButton.addEventListener("click", function (event) {
      event.preventDefault();
      if (!currentSurvey || submitButton.disabled || isSubmitting) {
        return;
      }
      currentSurvey.completeLastPage();
    });
  }

  // Window resizes / zoom change the rendered height (wrapping of 100%-width
  // fields, fonts); re-sync so the footer (Prev/Next) never gets clipped.
  let resizeSyncTimer = null;
  window.addEventListener("resize", function () {
    if (resizeSyncTimer) {
      window.clearTimeout(resizeSyncTimer);
    }
    resizeSyncTimer = window.setTimeout(function () {
      resizeSyncTimer = null;
      scheduleContainerHeightSync();
    }, 150);
  });
})();
