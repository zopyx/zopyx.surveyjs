
SurveyCreatorCore.registerSurveyTheme(SurveyTheme);

document.addEventListener("DOMContentLoaded", function () {
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
