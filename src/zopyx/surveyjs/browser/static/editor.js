
SurveyCreatorCore.registerSurveyTheme(SurveyTheme);

document.addEventListener("DOMContentLoaded", function () {
  const t = window._t || function (msgid) { return msgid; };

  function registerRichTextPropertyEditor() {
    if (
      typeof SurveyCreatorCore === "undefined" ||
      !SurveyCreatorCore.PropertyGridEditorCollection ||
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

    function getPropertyValue(obj, property, question) {
      if (obj && property && property.name && typeof obj.getPropertyValue === "function") {
        return obj.getPropertyValue(property.name);
      }
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

    function setPropertyValue(obj, property, value, question) {
      if (obj && property && property.name && typeof obj.setPropertyValue === "function") {
        obj.setPropertyValue(property.name, value);
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

      const setValue = function (value) {
        const html = value || "";
        if (quill.root.innerHTML !== html) {
          quill.root.innerHTML = html;
        }
        if (textarea && textarea.value !== html) {
          textarea.value = html;
        }
      };

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
        typeof question.onValueChanged.add === "function"
      ) {
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
        typeof obj.onPropertyChanged.add === "function"
      ) {
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
      fit: function (property) {
        return isHtmlProperty(property);
      },
      getJSON: function (obj, property, options) {
        return {
          type: "comment",
          rows: 8,
        };
      },
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

  const locale = window.SURVEYJS_I18N_LOCALE || navigator.language || "en";
  let hasUnsavedChanges = false;
  let isInitializing = true;
  let userInteracted = false;
  const creatorOptions = {
    autoSaveEnabled: true,
    collapseOnDrag: true,
    showToolbox: "right",
    showState: true,
    showPropertyGrid: "right",
    showThemeTab: true,
    rightContainerActiveItem: "toolbox",
    autoSaveEnabled: false,
  };

  if (typeof LICENSE_KEY !== "undefined" && LICENSE_KEY) {
    if (typeof SurveyCreator !== "undefined" && SurveyCreator.slk) {
      SurveyCreator.slk(LICENSE_KEY);
    }
    if (typeof SurveyCreatorCore !== "undefined" && SurveyCreatorCore.slk) {
      SurveyCreatorCore.slk(LICENSE_KEY);
    }
    if (typeof Survey !== "undefined" && Survey.slk) {
      Survey.slk(LICENSE_KEY);
    }
  }

  const creator = new SurveyCreator.SurveyCreator(creatorOptions);
  creator.locale = locale;
  if (typeof Survey !== "undefined" && Survey.surveyLocalization) {
    Survey.surveyLocalization.currentLocale = locale;
  }
  creator.render("surveyContainer");

  const editorRoot = document.getElementById("surveyEditorContainer");
  const fullscreenToggle = document.getElementById("surveyFullscreenToggle");
  const fullscreenClass = "survey-editor-fullscreen";

  const setFullscreen = function (enabled) {
    document.body.classList.toggle(fullscreenClass, Boolean(enabled));
    if (!fullscreenToggle) {
      return;
    }
    fullscreenToggle.textContent = enabled ? t("Exit fullscreen") : t("Fullscreen");
    fullscreenToggle.setAttribute("aria-pressed", enabled ? "true" : "false");
  };

  if (editorRoot) {
    const markInteraction = function () {
      userInteracted = true;
    };
    editorRoot.addEventListener("pointerdown", markInteraction, { once: true });
    editorRoot.addEventListener("keydown", markInteraction, { once: true });
  }

  if (fullscreenToggle) {
    fullscreenToggle.addEventListener("click", function (event) {
      event.preventDefault();
      const isFullscreen = document.body.classList.contains(fullscreenClass);
      setFullscreen(!isFullscreen);
    });
    document.addEventListener("keydown", function (event) {
      if (
        event.key === "Escape" &&
        document.body.classList.contains(fullscreenClass)
      ) {
        setFullscreen(false);
      }
    });
  }

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

  const setUnsavedState = function (isDirty) {
    hasUnsavedChanges = isDirty;
    document.body.classList.toggle("survey-has-unsaved", Boolean(isDirty));
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
  creator.onModified.add(function () {
    if (isInitializing || !userInteracted) {
      return;
    }
    setUnsavedState(true);
  });

  window.addEventListener("beforeunload", function (event) {
    if (!hasUnsavedChanges) {
      return undefined;
    }
    event.preventDefault();
    event.returnValue = "";
    return "";
  });

  var url = ACTUAL_URL + "/get-form-json";

  $.getJSON(url, function (result) {
    creator.JSON = result;
    window.setTimeout(function () {
      isInitializing = false;
      setUnsavedState(false);
    }, 0);
  }).fail(function () {
    isInitializing = false;
  });

  creator.saveSurveyFunc = function (saveNo, callback) {
    $.ajax({
      url: ACTUAL_URL + "/save-form-json",
      type: "POST",
      data: {
        surveyId: "42",
        surveyText: creator.text,
        _authenticator: CSRF_TOKEN,
      },
      success: function (data) {
        setUnsavedState(!data.isSuccess);
        callback(saveNo, data.isSuccess);
      },
      error: function (xhr, ajaxOptions, thrownError) {
        callback(saveNo, false);
        alert(thrownError);
      },
    });
  };
});
