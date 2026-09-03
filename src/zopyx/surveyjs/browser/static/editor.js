/**
 * SurveyJS visual editor bootstrapping for @@editor.
 * Reads config, applies locale/license, and initializes the creator UI.
 */

SurveyCreatorCore.registerSurveyTheme(SurveyTheme);

/**
 * @function
 */
document.addEventListener("DOMContentLoaded", function () {
/**
 * @function
 */
  const t = window._t || function (msgid) { return msgid; };

/**
 * @function
 */
  function registerRichTextPropertyEditor() {
    if (
      typeof SurveyCreatorCore === "undefined" ||
      !SurveyCreatorCore.PropertyGridEditorCollection ||
/**
 * @function
 */
      typeof SurveyCreatorCore.PropertyGridEditorCollection.register !== "function" ||
      typeof window.Quill === "undefined"
    ) {
      return;
    }

    const toolbar = [
      ["bold", "italic", "underline", "strike"],
      [{ header: [1, 2, 3, false] }],
      [{ list: "ordered" }, { list: "bullet" }],
      ["link", "image", "code-block"],
      ["clean"],
    ];

/**
 * @function
 */
    function isHtmlProperty(prop) {
      if (!prop) {
        return false;
      }
      const name = (prop.name || "").toLowerCase();
      return (
        prop.type === "html" ||
        name === "html" ||
        name.endsWith("html")
      );
    }

/**
 * @function
 */
    function getPropertyValue(obj, property, question) {
/**
 * @function
 */
      if (obj && property && property.name && typeof obj.getPropertyValue === "function") {
        return obj.getPropertyValue(property.name);
      }
/**
 * @function
 */
      if (property && typeof property.getValue === "function") {
        return property.getValue(obj);
      }
      if (obj && property && property.name) {
        if (Object.prototype.hasOwnProperty.call(obj, property.name)) {
          return obj[property.name];
        }
      }
      if (question && Object.prototype.hasOwnProperty.call(question, "value")) {
        return question.value;
      }
      return "";
    }

/**
 * @function
 */
    function setPropertyValue(obj, property, value, question) {
/**
 * @function
 */
      if (obj && property && property.name && typeof obj.setPropertyValue === "function") {
        obj.setPropertyValue(property.name, value);
/**
 * @function
 */
      } else if (property && typeof property.setValue === "function") {
        property.setValue(obj, value);
      } else if (obj && property && property.name) {
        obj[property.name] = value;
      }
      if (
        question &&
        Object.prototype.hasOwnProperty.call(question, "value") &&
        question.value !== value
      ) {
        question.value = value;
      }
    }

/**
 * @function
 */
    function mountQuillEditor(question, htmlElement, obj, property) {
      if (!question || !htmlElement) {
        return;
      }

      if (question.__quillEditor && question.__quillSyncFromProperty) {
        question.__quillContext = { obj: obj, property: property };
        question.__quillSyncFromProperty();
        return;
      }

      const textarea =
        htmlElement.querySelector("textarea") ||
        htmlElement.querySelector("input");
      if (textarea) {
        textarea.style.display = "none";
      }

      const container = document.createElement("div");
      container.className = "sv-quill-editor";
      if (textarea && textarea.parentNode) {
        textarea.parentNode.insertBefore(container, textarea.nextSibling);
      } else {
        htmlElement.appendChild(container);
      }

      const quill = new Quill(container, {
        theme: "snow",
        modules: { toolbar: toolbar },
      });

      let isSyncing = false;
      question.__quillContext = { obj: obj, property: property };

/**
 * @function
 */
      const setValue = function (value) {
        const html = value || "";
        if (quill.root.innerHTML !== html) {
          quill.root.innerHTML = html;
        }
        if (textarea && textarea.value !== html) {
          textarea.value = html;
        }
      };

/**
 * @function
 */
      const syncFromProperty = function () {
        if (isSyncing) {
          return;
        }
        isSyncing = true;
        const context = question.__quillContext || {};
        const value = getPropertyValue(context.obj, context.property, question);
        setValue(value);
        isSyncing = false;
      };

      question.__quillSyncFromProperty = syncFromProperty;
      syncFromProperty();
      setTimeout(syncFromProperty, 0);

/**
 * @function
 */
      quill.on("text-change", function () {
        if (isSyncing) {
          return;
        }
        isSyncing = true;
        const html = quill.root.innerHTML;
        const context = question.__quillContext || {};
        setPropertyValue(context.obj, context.property, html, question);
        if (textarea && textarea.value !== html) {
          textarea.value = html;
        }
        isSyncing = false;
      });

      if (
        question.onValueChanged &&
/**
 * @function
 */
        typeof question.onValueChanged.add === "function"
      ) {
/**
 * @function
 */
        question.onValueChanged.add(function (sender, options) {
          if (isSyncing) {
            return;
          }
          isSyncing = true;
          const nextValue =
            options && Object.prototype.hasOwnProperty.call(options, "value")
              ? options.value
              : sender.value;
          setValue(nextValue);
          isSyncing = false;
        });
      }

      if (
        obj &&
        property &&
        property.name &&
        obj.onPropertyChanged &&
/**
 * @function
 */
        typeof obj.onPropertyChanged.add === "function"
      ) {
/**
 * @function
 */
        obj.onPropertyChanged.add(function (sender, options) {
          if (
            options &&
            options.name &&
            options.name !== property.name
          ) {
            return;
          }
          syncFromProperty();
        });
      }

      if (!question.__quillUpdateButton) {
        const updateButton = document.createElement("button");
        updateButton.type = "button";
        updateButton.className = "btn btn-secondary sv-quill-update";
        updateButton.textContent = t("Update");
/**
 * @function
 */
        updateButton.addEventListener("click", function () {
          const html = quill.root.innerHTML;
          const context = question.__quillContext || {};
          setPropertyValue(context.obj, context.property, html, question);
          if (textarea) {
            textarea.value = html;
            textarea.dispatchEvent(new Event("input", { bubbles: true }));
            textarea.dispatchEvent(new Event("change", { bubbles: true }));
          }
          syncFromProperty();
        });
        container.insertAdjacentElement("afterend", updateButton);
        question.__quillUpdateButton = updateButton;
      }

      question.__quillEditor = quill;
    }

    SurveyCreatorCore.PropertyGridEditorCollection.register({
/**
 * @function
 */
      fit: function (property) {
        return isHtmlProperty(property);
      },
/**
 * @function
 */
      getJSON: function (obj, property, options) {
        return {
          type: "comment",
          rows: 8,
        };
      },
/**
 * @function
 */
      onAfterRenderQuestion: function (obj, property, options) {
        if (!options) {
          return;
        }
        const question = options.question || options;
        const htmlElement =
          options.htmlElement ||
          options.element ||
          options.htmlElement;
        if (!htmlElement || !question) {
          return;
        }
        mountQuillEditor(question, htmlElement, obj, property);
      },
    });
  }

  registerRichTextPropertyEditor();

/**
 * @function
 */
  const normalizeLocale = function (value) {
    const raw = value == null ? "" : String(value);
    return raw.trim().replace("_", "-");
  };

/**
 * @function
 */
  const toSurveyLocale = function (value) {
    const normalized = normalizeLocale(value);
    const base = normalized.split("-")[0];
    return base || "en";
  };

/**
 * @function
 */
  const extractSurveyLocale = function (formJson) {
    if (!formJson || typeof formJson !== "object") {
      return "";
    }
    if (formJson.locale) {
      return formJson.locale;
    }
    if (formJson.defaultLanguage) {
      return formJson.defaultLanguage;
    }
    if (Array.isArray(formJson.languages) && formJson.languages.length > 0) {
      return formJson.languages[0];
    }
    return "";
  };

/**
 * @function
 */
  const isoToCreatorLanguage = function (isoCode) {
    const mapping = {
      de: "german",
      fr: "french",
      es: "spanish",
      it: "italian",
      nl: "dutch",
      pt: "portuguese",
      pl: "polish",
      ru: "russian",
      ja: "japanese",
      zh: "simplified-chinese",
      ko: "korean",
      ar: "arabic",
      bg: "bulgarian",
      hr: "croatian",
      cs: "czech",
      da: "danish",
      fi: "finnish",
      el: "greek",
      he: "hebrew",
      hu: "hungarian",
      id: "indonesian",
      ms: "malay",
      mn: "mongolian",
      no: "norwegian",
      fa: "persian",
      ro: "romanian",
      sk: "slovak",
      sl: "slovenian",
      sv: "swedish",
      th: "thai",
      tr: "turkish",
      en: "english"
    };
    return mapping[isoCode] || null;
  };

/**
 * @function
 */
  const getCreatorI18nUrl = function (localeValue) {
    const languageName = isoToCreatorLanguage(localeValue);
    if (!languageName) {
      return null;
    }
    const base =
      window.SURVEYJS_CREATOR_I18N_BASE ||
      "https://unpkg.com/survey-creator-core/i18n";
    return base.replace(/\/$/, "") + "/survey-creator-i18n-" + languageName + ".js";
  };

  const creatorLocaleCache = {};
/**
 * @function
 */
  const loadCreatorLocale = function (localeValue) {
    const locale = toSurveyLocale(localeValue);
    if (!locale || locale === "en") {
      return Promise.resolve("en");
    }
    if (creatorLocaleCache[locale]) {
      return creatorLocaleCache[locale];
    }
    if (
      window.SurveyCreatorCore &&
      SurveyCreatorCore.localization &&
      SurveyCreatorCore.localization.locales &&
      SurveyCreatorCore.localization.locales[locale]
    ) {
      creatorLocaleCache[locale] = Promise.resolve(locale);
      return creatorLocaleCache[locale];
    }
    const i18nUrl = getCreatorI18nUrl(locale);
    if (!i18nUrl) {
      creatorLocaleCache[locale] = Promise.resolve("en");
      return creatorLocaleCache[locale];
    }
/**
 * @function
 */
    creatorLocaleCache[locale] = new Promise(function (resolve, reject) {
      const script = document.createElement("script");
      script.async = true;
      script.src = i18nUrl;
/**
 * @function
 */
      script.onload = function () {
        resolve(locale);
      };
/**
 * @function
 */
      script.onerror = function () {
        reject(new Error("Failed to load Survey Creator locale: " + locale));
      };
      document.head.appendChild(script);
/**
 * @function
 */
    }).catch(function () {
      return "en";
    });
    return creatorLocaleCache[locale];
  };

  const fallbackLocale = window.SURVEYJS_I18N_LOCALE || navigator.language || "en";
  const initialLocale = toSurveyLocale(fallbackLocale);
  let hasUnsavedChanges = false;
  let isInitializing = true;
  let userInteracted = false;
  let suppressModified = false;
  const parseJsonArray = function (value) {
    if (!value) {
      return [];
    }
    try {
      const parsed = JSON.parse(value);
      if (!Array.isArray(parsed)) {
        return [];
      }
      return parsed
        .map(function (item) { return toSurveyLocale(item); })
        .filter(function (item, index, list) {
          return item && list.indexOf(item) === index;
        });
    } catch (_error) {
      return [];
    }
  };
  const creatorOptions = {
    autoSaveEnabled: false,
    collapseOnDrag: true,
    showToolbox: true,
    showState: true,
    showSidebar: true,
    showThemeTab: false,
    showTranslationTab: false,
    rightContainerActiveItem: "toolbox",
  };

  const licenseEl = document.getElementById("survey-editor-config");
  const configuredSurveyLanguages = licenseEl
    ? parseJsonArray(licenseEl.getAttribute("data-survey-languages"))
    : [];
  const licenseKey = licenseEl
    ? licenseEl.getAttribute("data-license-key")
    : (typeof window.LICENSE_KEY !== "undefined" ? window.LICENSE_KEY : "");
  if (configuredSurveyLanguages.length > 0) {
    creatorOptions.showTranslationTab = true;
  }

  if (licenseKey) {
    if (typeof SurveyCreator !== "undefined" && SurveyCreator.slk) {
      SurveyCreator.slk(licenseKey);
    }
    if (typeof SurveyCreatorCore !== "undefined" && SurveyCreatorCore.slk) {
      SurveyCreatorCore.slk(licenseKey);
    }
    if (typeof Survey !== "undefined" && Survey.slk) {
      Survey.slk(licenseKey);
    }
  }

  const creator = new SurveyCreator.SurveyCreator(creatorOptions);
  if (configuredSurveyLanguages.length > 0) {
    creator.showTranslationTab = true;
    if (
      typeof creator.initialTabs === "function" &&
      typeof creator.setTabs === "function"
    ) {
      creator.setTabs(creator.initialTabs());
    }
    if (typeof creator.setVisibleLocales === "function") {
      creator.setVisibleLocales(configuredSurveyLanguages);
    }
  }
/**
 * @function
 */
  const applyCreatorLocale = function (nextLocale) {
    const localeValue = toSurveyLocale(nextLocale || initialLocale);
/**
 * @function
 */
    return loadCreatorLocale(localeValue).then(function () {
      creator.locale = localeValue;
      if (typeof Survey !== "undefined" && Survey.surveyLocalization) {
        Survey.surveyLocalization.currentLocale = localeValue;
      }
      if (creator.previewSurvey) {
        creator.previewSurvey.locale = localeValue;
      }
    });
  };

/**
 * @function
 */
  const enablePreviewFullscreen = function (survey) {
    if (!survey || typeof survey !== "object") {
      return;
    }
    survey.allowFullScreen = true;
  };

  // Read theme JSON early so it's available for the creator
  var themeJson = null;
  var allThemeJsons = {};
  var themeJsonEl = document.getElementById("survey-editor-config");
  if (themeJsonEl) {
    try {
      var raw = themeJsonEl.getAttribute("data-survey-theme-json");
      if (raw) {
        var parsed = JSON.parse(raw);
        if (parsed && typeof parsed === "object" && Object.keys(parsed).length > 0) {
          themeJson = parsed;
        }
      }
    } catch (e) {}
  }

  // Apply theme via CSS variables on creator container (most reliable for Survey Creator)
  // and also via survey API as fallback
  var _lastThemeVars = null;
  var _lastCreatorTheme = null;

  function applyThemeToElements(theme) {
    var tj = theme || themeJson;
    try {
      var editorContainer = document.getElementById("surveyEditorContainer");
      if (editorContainer) {
        editorContainer.classList.toggle(
          "survey-editor-panelless",
          Boolean(tj && tj.isPanelless)
        );
      }
      // Collect all targets once
      var targets = [
        document.getElementById("surveyEditorContainer"),
        document.getElementById("surveyContainer"),
        document.getElementById("surveyContainer") ? document.getElementById("surveyContainer").parentNode : null,
      ];
      document.querySelectorAll(".svc-creator, .sv_main, .sv_body, .sv-root-modern").forEach(function(el) {
        targets.push(el);
      });

      if (tj) {
        // Keep the Creator's theme model in sync as well.  This is important
        // for preview surveys: the Creator creates those lazily and applies
        // its own theme when the Preview tab is opened.
        if (creator && _lastCreatorTheme !== tj) {
          try {
            if (typeof creator.applyCreatorTheme === "function") {
              creator.applyCreatorTheme(tj);
            } else {
              creator.theme = tj;
            }
            _lastCreatorTheme = tj;
          } catch (e) {}
        }
        var vars = tj.cssVariables || {};
        // Clear previously applied vars that are not in the new theme
        if (_lastThemeVars) {
          targets.forEach(function (el) {
            if (!el) return;
            Object.keys(_lastThemeVars).forEach(function (key) {
              if (!(key in vars)) {
                try { el.style.removeProperty(key); } catch (e) {}
              }
            });
          });
        }
        // Apply new vars
        targets.forEach(function (el) {
          if (!el) return;
          Object.keys(vars).forEach(function (key) {
            try { el.style.setProperty(key, vars[key]); } catch (e) {}
          });
        });
        _lastThemeVars = vars;
        // Apply to creator's survey via API
        if (creator) {
          try {
            if (creator.survey && typeof creator.survey.applyTheme === "function") {
              creator.survey.applyTheme(tj);
            }
            if (creator.previewSurvey && typeof creator.previewSurvey.applyTheme === "function") {
              creator.previewSurvey.applyTheme(tj);
            }
          } catch (e) {}
        }
      } else {
        if (creator && _lastCreatorTheme !== null) {
          try {
            creator.theme = null;
            _lastCreatorTheme = null;
          } catch (e) {}
        }
        // No theme — clear all previously applied CSS variables
        if (_lastThemeVars) {
          targets.forEach(function (el) {
            if (!el) return;
            Object.keys(_lastThemeVars).forEach(function (key) {
              try { el.style.removeProperty(key); } catch (e) {}
            });
          });
          _lastThemeVars = null;
        }
        // Reset survey theme
        if (creator) {
          try {
            if (creator.survey && typeof creator.survey.applyTheme === "function") {
              creator.survey.applyTheme({});
            }
            if (creator.previewSurvey && typeof creator.previewSurvey.applyTheme === "function") {
              creator.previewSurvey.applyTheme({});
            }
          } catch (e) {}
        }
      }
    } catch (e) {}
  }

  // Preview is created lazily by Survey Creator.  Re-apply the selected
  // theme whenever that happens so panelless themes affect the preview too.
  if (creator.onPreviewSurveyCreated && typeof creator.onPreviewSurveyCreated.add === "function") {
    creator.onPreviewSurveyCreated.add(function (_sender, options) {
      if (options && options.survey && themeJson && typeof options.survey.applyTheme === "function") {
        try { options.survey.applyTheme(themeJson); } catch (e) {}
      }
      applyThemeToElements();
    });
  }

  // Poll for the creator to be ready and apply theme repeatedly
  function scheduleThemeApplication() {
    applyThemeToElements();
    // Re-apply a few times to catch the survey being rebuilt
    window.setTimeout(applyThemeToElements, 500);
    window.setTimeout(applyThemeToElements, 1500);
  }

  // Apply after locales are loaded; schedule theme application after render
  applyCreatorLocale(initialLocale).then(function () {
    creator.render("surveyContainer");
    scheduleThemeApplication();
  });

  const editorRoot = document.getElementById("surveyEditorContainer");
  const fullscreenToggle = document.getElementById("surveyFullscreenToggle");
  const fullscreenClass = "survey-editor-fullscreen";

/**
 * @function
 */
  const setFullscreen = function (enabled) {
    suppressModified = true;
    document.body.classList.toggle(fullscreenClass, Boolean(enabled));
    if (!fullscreenToggle) {
/**
 * @function
 */
      setTimeout(function () {
        suppressModified = false;
      }, 0);
      return;
    }
    fullscreenToggle.textContent = enabled ? t("Exit fullscreen") : t("Fullscreen");
    fullscreenToggle.setAttribute("aria-pressed", enabled ? "true" : "false");
/**
 * @function
 */
    setTimeout(function () {
      suppressModified = false;
    }, 0);
  };

  if (editorRoot) {
/**
 * @function
 */
    const markInteraction = function (event) {
      if (fullscreenToggle && event && fullscreenToggle.contains(event.target)) {
        return;
      }
      userInteracted = true;
    };
    editorRoot.addEventListener("pointerdown", markInteraction, { once: true });
    editorRoot.addEventListener("keydown", markInteraction, { once: true });
  }

  if (fullscreenToggle) {
/**
 * @function
 */
    fullscreenToggle.addEventListener("click", function (event) {
      event.preventDefault();
      const isFullscreen = document.body.classList.contains(fullscreenClass);
      setFullscreen(!isFullscreen);
    });
/**
 * @function
 */
    document.addEventListener("keydown", function (event) {
      if (
        event.key === "Escape" &&
        document.body.classList.contains(fullscreenClass)
      ) {
        setFullscreen(false);
      }
    });
  }

/**
 * @function
 */
  const getSaveButton = function () {
    const selectors = [
      ".svc-toolbar__item--save",
      "[data-action-id='save']",
      "[data-name='save']",
      "[data-action='save']",
      "button[title='Save']",
      "button[title='Save Form']",
      "button[aria-label='Save']",
      "button[aria-label='Save Form']",
    ];
    for (let i = 0; i < selectors.length; i += 1) {
      const match = document.querySelector(selectors[i]);
      if (match) {
        return match;
      }
    }
    return null;
  };

/**
 * @function
 */
  const ensureUnsavedIndicator = function () {
    const saveButton = getSaveButton();
    if (!saveButton) {
      return null;
    }
    let indicator = document.querySelector(".survey-unsaved-indicator");
    if (!indicator) {
      indicator = document.createElement("span");
      indicator.className = "survey-unsaved-indicator";
      indicator.textContent = t("Unsaved changes");
      saveButton.insertAdjacentElement("afterend", indicator);
    }
    return indicator;
  };

/**
 * @function
 */
  const setUnsavedState = function (isDirty) {
    hasUnsavedChanges = isDirty;
    document.body.classList.toggle("survey-has-unsaved", Boolean(isDirty));
    document.body.classList.toggle("survey-unsaved-visible", Boolean(isDirty));
    const banner = document.getElementById("editorUnsavedBanner");
    if (banner) {
      banner.hidden = !isDirty;
    }
    const indicator = ensureUnsavedIndicator();
    if (indicator) {
      indicator.hidden = !isDirty;
    }
  };

  setUnsavedState(false);
  ensureUnsavedIndicator();
/**
 * @function
 */
  creator.onModified.add(function () {
    if (isInitializing || !userInteracted || suppressModified) {
      return;
    }
    setUnsavedState(true);
  });

/**
 * @function
 */
  window.addEventListener("beforeunload", function (event) {
    if (!hasUnsavedChanges) {
      return undefined;
    }
    event.preventDefault();
    event.returnValue = "";
    return "";
  });

  var url = ACTUAL_URL + "/get-form-json";

  // --- Theme switcher ---
    var themeSwitcher = document.getElementById("surveyThemeSwitcher");
    var themeSaveBtn = document.getElementById("surveyThemeSaveBtn");
    var savedThemeId = themeJsonEl ? themeJsonEl.getAttribute("data-survey-current-theme") || "" : "";
    // Populate dropdown from config
    if (themeSwitcher && themeJsonEl) {
      try {
        var choicesRaw = themeJsonEl.getAttribute("data-survey-themes-choices");
        if (choicesRaw) {
          var choices = JSON.parse(choicesRaw);
          themeSwitcher.innerHTML = "";
          choices.forEach(function (c) {
            var opt = document.createElement("option");
            opt.value = c.value || "";
            opt.textContent = c.text || "";
            if (c.value === savedThemeId) opt.selected = true;
            themeSwitcher.appendChild(opt);
          });
        }
      } catch (e) {}

      themeSwitcher.addEventListener("change", function () {
        var selectedId = themeSwitcher.value;
        if (themeSaveBtn) {
          themeSaveBtn.style.display = (selectedId !== savedThemeId) ? "inline-block" : "none";
        }
        if (!selectedId) {
          // No theme selected — reset to default or clear
          themeJson = null;
          applyThemeToElements();
          return;
        }
        // Fetch theme JSON for the selected theme
        $.getJSON(ACTUAL_URL + "/@@editor?action=get_theme_json&theme_id=" + encodeURIComponent(selectedId), function (data) {
          if (data && typeof data === "object" && Object.keys(data).length > 0) {
            themeJson = data;
          } else {
            themeJson = null;
          }
          applyThemeToElements();
        });
      });
    }

    if (themeSaveBtn) {
      themeSaveBtn.addEventListener("click", function () {
        var selectedId = themeSwitcher ? themeSwitcher.value : "";
        $.ajax({
          url: ACTUAL_URL + "/@@editor",
          type: "POST",
          data: {
            action: "save_theme",
            theme_id: selectedId,
            _authenticator: CSRF_TOKEN,
          },
          success: function (resp) {
            try {
              var r = JSON.parse(resp);
              if (r.success) {
                savedThemeId = selectedId;
                themeSaveBtn.style.display = "none";
                if (themeSwitcher) themeSwitcher.value = selectedId;
              }
            } catch (e) {}
          },
        });
      });
    }

/**
 * @function
 */
  $.getJSON(url, function (result) {
    if (
      configuredSurveyLanguages.length > 0 &&
      result &&
      typeof result === "object"
    ) {
      result.locales = configuredSurveyLanguages.slice();
      if (!result.locale) {
        result.locale = configuredSurveyLanguages[0];
      }
    }
    const formLocale = extractSurveyLocale(result);
/**
 * @function
 */
    applyCreatorLocale(formLocale || initialLocale).then(function () {
      creator.JSON = result;
      // Apply theme after JSON is loaded (allow creator to rebuild survey)
      window.setTimeout(function () {
        applyThemeToElements();
      }, 200);
/**
 * @function
 */
      window.setTimeout(function () {
        isInitializing = false;
        setUnsavedState(false);
      }, 0);
    });
/**
 * @function
 */
  }).fail(function () {
    isInitializing = false;
  });

/**
 * @function
 */
  creator.saveSurveyFunc = function (saveNo, callback) {
    $.ajax({
      url: ACTUAL_URL + "/save-form-json",
      type: "POST",
      data: {
        surveyId: "42",
        surveyText: creator.text,
        _authenticator: CSRF_TOKEN,
      },
/**
 * @function
 */
      success: function (data) {
        setUnsavedState(!data.isSuccess);
        callback(saveNo, data.isSuccess);
      },
/**
 * @function
 */
      error: function (xhr, ajaxOptions, thrownError) {
        callback(saveNo, false);
        alert(thrownError);
      },
    });
  };
});
