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
  function getVisibleHeight(el) {
    if (!el) {
      return 0;
    }
    const style = window.getComputedStyle(el);
    if (style.display === "none" || style.visibility === "hidden") {
      return 0;
    }
    return el.getBoundingClientRect().height;
  }

/**
 * @function
 */
  function syncContainerHeight(animate) {
    if (heightResetTimer) {
      window.clearTimeout(heightResetTimer);
      heightResetTimer = null;
    }

    const root =
      container.querySelector(".sd-root-modern") ||
      container.querySelector(".sv-root-modern") ||
      container.firstElementChild;
    if (!root) {
      return;
    }

    const startHeight = container.getBoundingClientRect().height;

    const activePage =
      root.querySelector(".sd-page.sd-page--active") ||
      root.querySelector(".sv-page.sv-page--active") ||
      root.querySelector(".sd-page:not(.sd-page--invisible)") ||
      root.querySelector(".sv-page:not([style*='display: none'])");

    const navButtons =
      root.querySelector(".sd-action-bar") ||
      root.querySelector(".sv-action-bar") ||
      root.querySelector(".sd-footer") ||
      root.querySelector(".sv-footer");

    const pageTitle = activePage ? activePage.querySelector(".sd-title, .sv-title") : null;
    const pageDescription = activePage ? activePage.querySelector(".sd-page__description, .sv-page__description") : null;

    let targetHeight = 0;

    if (activePage) {
      targetHeight += getVisibleHeight(activePage);
    }

    if (navButtons) {
      const buttonsHeight = getVisibleHeight(navButtons);
      targetHeight += buttonsHeight;
    }

    targetHeight = Math.ceil(targetHeight) + 180;

    if (!targetHeight || !Number.isFinite(targetHeight)) {
      return;
    }

    if (!animate) {
      container.style.height = targetHeight + "px";
      container.style.minHeight = "0";
      return;
    }

    if (Math.abs(startHeight - targetHeight) < 2) {
      container.style.height = targetHeight + "px";
      return;
    }

    container.style.height = startHeight + "px";
    container.style.minHeight = "0";
    container.offsetHeight;
    container.style.transition = "height 160ms ease";
    container.style.height = targetHeight + "px";

/**
 * @function
 */
    heightResetTimer = window.setTimeout(function () {
      container.style.transition = "";
      heightResetTimer = null;
    }, 220);
  }

/**
 * @function
 */
  function scheduleContainerHeightSync(animate) {
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
        syncContainerHeight(animate);
      });
    });
    // SurveyJS may apply visibility/layout changes asynchronously; re-measure once more.
    pendingHeightSyncTimer = window.setTimeout(function () {
      pendingHeightSyncTimer = null;
      syncContainerHeight(animate);
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

/**
 * @function
 */
  function applyDynamicSchemaChoices(schema) {
    if (!schema || !Array.isArray(schema.pages)) {
      return;
    }
    const languageChoices = getDynamicSurveyLanguageChoices();
    if (!languageChoices.length) {
      return;
    }
    schema.pages.forEach(function (page) {
      if (!page || !Array.isArray(page.elements)) {
        return;
      }
      page.elements.forEach(function (element) {
        if (element && element.name === "survey_languages") {
          element.choices = languageChoices;
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
        scheduleContainerHeightSync(true);
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
      scheduleContainerHeightSync(true);
    });
/**
 * @function
 */
    survey.onCurrentPageChanged.add(function () {
      updateSubmitState(false);
      scheduleContainerHeightSync(true);
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
})();
