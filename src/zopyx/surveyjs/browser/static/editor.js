
SurveyCreatorCore.registerSurveyTheme(SurveyTheme);

document.addEventListener("DOMContentLoaded", function () {
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

    function mountQuillEditor(question, htmlElement) {
      if (!question || !htmlElement || question.__quillEditor) {
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

      const setValue = function (value) {
        const html = value || "";
        if (quill.root.innerHTML !== html) {
          quill.root.innerHTML = html;
        }
      };

      setValue(question.value);
      quill.on("text-change", function () {
        question.value = quill.root.innerHTML;
      });

      if (
        question.onValueChanged &&
        typeof question.onValueChanged.add === "function"
      ) {
        question.onValueChanged.add(function (sender, options) {
          const nextValue =
            options && Object.prototype.hasOwnProperty.call(options, "value")
              ? options.value
              : sender.value;
          setValue(nextValue);
        });
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
        mountQuillEditor(question, htmlElement);
      },
    });
  }

  registerRichTextPropertyEditor();

  const locale = window.SURVEYJS_I18N_LOCALE || navigator.language || "en";
  let hasUnsavedChanges = false;
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
  creator.onModified.add(function () {
    hasUnsavedChanges = true;
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
    hasUnsavedChanges = false;
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
        hasUnsavedChanges = !data.isSuccess;
        callback(saveNo, data.isSuccess);
      },
      error: function (xhr, ajaxOptions, thrownError) {
        callback(saveNo, false);
        alert(thrownError);
      },
    });
  };
});
