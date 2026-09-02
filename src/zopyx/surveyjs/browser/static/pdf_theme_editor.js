/**
 * PDF Theme Editor — standalone SurveyJS Creator with only the Theme tab.
 * Import: file picker -> load JSON -> apply to creator.theme
 * Export: POST creator.theme -> server writes /tmp/theme.json
 */
SurveyCreatorCore.registerSurveyTheme(SurveyTheme);

document.addEventListener("DOMContentLoaded", function () {

  var licenseEl = document.getElementById("survey-editor-config");
  var licenseKey = licenseEl
    ? licenseEl.getAttribute("data-license-key") || ""
    : "";

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

  var creator = new SurveyCreator.SurveyCreator({
    showDesignerTab: false,
    showSurveySettingsTab: false,
    showTranslationTab: false,
    showThemeTab: true,
    showToolbox: false,
    showSidebar: false,
    showState: false,
  });

  // Representative sample form — exercises most theme CSS variables
  creator.JSON = {
    "locale": "en",
    "title": "Customer Satisfaction Survey",
    "description": "Help us improve our products and services by sharing your experience. All fields marked with * are required.",
    "logoPosition": "right",
    "pages": [
      {
        "name": "page1",
        "title": "About You",
        "description": "Please tell us a little about yourself.",
        "elements": [
          {
            "type": "text",
            "name": "full_name",
            "title": "Full Name *",
            "isRequired": true,
            "placeholder": "Enter your full name"
          },
          {
            "type": "text",
            "name": "email",
            "title": "Email Address *",
            "isRequired": true,
            "inputType": "email",
            "validators": [{ "type": "email" }],
            "placeholder": "you@example.com"
          },
          {
            "type": "radiogroup",
            "name": "age_group",
            "title": "Age Group",
            "choices": [
              { "value": "under_18", "text": "Under 18" },
              { "value": "18_30", "text": "18–30" },
              { "value": "31_45", "text": "31–45" },
              { "value": "46_60", "text": "46–60" },
              { "value": "over_60", "text": "Over 60" }
            ],
            "colCount": 2
          },
          {
            "type": "dropdown",
            "name": "country",
            "title": "Country *",
            "isRequired": true,
            "placeholder": "Select your country",
            "choicesByUrl": {
              "url": "https://surveyjs.io/api/CountriesExample",
              "valueName": "name"
            }
          },
          {
            "type": "checkbox",
            "name": "interests",
            "title": "Topics of Interest",
            "description": "Select all that apply.",
            "choices": [
              { "value": "technology", "text": "Technology" },
              { "value": "science", "text": "Science" },
              { "value": "sports", "text": "Sports" },
              { "value": "music", "text": "Music" },
              { "value": "art", "text": "Art & Design" },
              { "value": "travel", "text": "Travel" }
            ],
            "colCount": 2
          }
        ]
      },
      {
        "name": "page2",
        "title": "Your Experience",
        "description": "Rate different aspects of your experience with us.",
        "elements": [
          {
            "type": "rating",
            "name": "overall_satisfaction",
            "title": "Overall Satisfaction *",
            "isRequired": true,
            "rateCount": 5,
            "rateMin": 1,
            "rateMax": 5,
            "rateValues": [
              { "value": 1, "text": "Very Poor" },
              { "value": 2, "text": "Poor" },
              { "value": 3, "text": "Average" },
              { "value": 4, "text": "Good" },
              { "value": 5, "text": "Excellent" }
            ],
            "rateType": "labels"
          },
          {
            "type": "boolean",
            "name": "would_recommend",
            "title": "Would you recommend us to a friend?",
            "labelTrue": "Yes, definitely",
            "labelFalse": "No, probably not",
            "indeterminate": true
          },
          {
            "type": "matrix",
            "name": "quality_metrics",
            "title": "Please rate the following aspects",
            "columns": [
              { "value": 1, "text": "Poor" },
              { "value": 2, "text": "Fair" },
              { "value": 3, "text": "Good" },
              { "value": 4, "text": "Excellent" }
            ],
            "rows": [
              { "value": "product_quality", "text": "Product Quality" },
              { "value": "customer_service", "text": "Customer Service" },
              { "value": "delivery_speed", "text": "Delivery Speed" },
              { "value": "value_for_money", "text": "Value for Money" }
            ]
          },
          {
            "type": "matrixdropdown",
            "name": "detailed_feedback",
            "title": "Detailed Feedback",
            "columns": [
              { "name": "rating", "title": "Rating", "cellType": "dropdown", "choices": [1, 2, 3, 4, 5], "isRequired": true },
              { "name": "comment", "title": "Comment", "cellType": "text", "validators": [{ "type": "maxlength", "maxLength": 200 }] }
            ],
            "rows": [
              { "value": "usability", "text": "Ease of Use" },
              { "value": "design", "text": "Visual Design" },
              { "value": "performance", "text": "Performance" }
            ]
          }
        ]
      },
      {
        "name": "page3",
        "title": "Feedback",
        "description": "Any additional thoughts?",
        "elements": [
          {
            "type": "panel",
            "name": "contact_preferences",
            "title": "Contact Preferences",
            "elements": [
              {
                "type": "boolean",
                "name": "contact_me",
                "title": "May we contact you for follow-up?",
                "defaultValue": false
              },
              {
                "type": "text",
                "name": "phone_number",
                "title": "Phone Number",
                "inputType": "tel",
                "visibleIf": "{contact_me} = true",
                "placeholder": "+1 (555) 123-4567"
              }
            ]
          },
          {
            "type": "comment",
            "name": "suggestions",
            "title": "Your Suggestions",
            "placeholder": "Tell us what we can improve...",
            "maxLength": 1000,
            "rows": 4
          },
          {
            "type": "file",
            "name": "attachments",
            "title": "Attach Files",
            "maxSize": 5242880,
            "acceptTypes": ".jpg,.png,.pdf,.docx"
          },
          {
            "type": "signaturepad",
            "name": "signature",
            "title": "Digital Signature"
          },
          {
            "type": "html",
            "name": "info",
            "html": "<p style='text-align:center;color:#64748b;font-size:0.9rem;'>Thank you for taking the time to provide your feedback. Your responses help us improve.</p>"
          }
        ]
      }
    ],
    "showProgressBar": "aboveHeader",
    "progressBarType": "pages",
    "showQuestionNumbers": "on",
    "questionTitleLocation": "top",
    "requiredText": "*",
    "validators": [],
    "pageNextText": "Next →",
    "pagePrevText": "← Back",
    "completeText": "Submit Survey",
    "widthMode": "static",
    "width": 800
  };

  console.log("PDFThemeEditor initial creator.theme:", JSON.stringify(creator.theme));
  creator.render("surveyContainer");

  // --- Import ---
  var importBtn = document.getElementById("importThemeBtn");
  var importInput = document.getElementById("importThemeInput");
  var exportBtn = document.getElementById("exportThemeBtn");
  var statusEl = document.getElementById("themeStatus");

  function setStatus(msg, isError) {
    if (!statusEl) return;
    statusEl.textContent = msg;
    statusEl.style.color = isError ? "#dc2626" : "#16a34a";
  }

  if (importBtn && importInput) {
    importBtn.addEventListener("click", function () {
      importInput.value = "";
      importInput.click();
    });
    importInput.addEventListener("change", function () {
      var file = importInput.files && importInput.files[0];
      if (!file) return;
      var reader = new FileReader();
      reader.onload = function (e) {
        try {
          var themeJson = JSON.parse(e.target.result);
          if (!themeJson || typeof themeJson !== "object") {
            setStatus("Invalid theme JSON", true);
            return;
          }
          creator.theme = themeJson;
          setStatus("Theme imported: " + file.name);
        } catch (err) {
          setStatus("Parse error: " + err.message, true);
        }
      };
      reader.readAsText(file);
    });
  }

  // --- Export ---
  if (exportBtn) {
    exportBtn.addEventListener("click", function () {
      var theme = creator.theme;
      console.log("PDFThemeEditor export click — creator.theme:", JSON.stringify(theme));
      if (!theme || (typeof theme === "object" && Object.keys(theme).length === 0)) {
        setStatus("No theme to export", true);
        return;
      }
      var themeStr = JSON.stringify(theme, null, 2);
      console.log("PDFThemeEditor exporting theme JSON:", themeStr);
      var xhr = new XMLHttpRequest();
      xhr.open("POST", window.location.pathname, true);
      xhr.setRequestHeader("Content-Type", "application/x-www-form-urlencoded");
      xhr.onload = function () {
        if (xhr.status === 200) {
          try {
            var resp = JSON.parse(xhr.responseText);
            if (resp.success) {
              setStatus("Exported to " + resp.path);
            } else {
              setStatus("Export failed: " + (resp.error || "unknown"), true);
            }
          } catch (e) {
            setStatus("Export OK (server)", false);
          }
        } else {
          setStatus("Export error: HTTP " + xhr.status, true);
        }
      };
      xhr.onerror = function () {
        setStatus("Export network error", true);
      };
      var csrfToken =
        window.CSRF_TOKEN ||
        (document.getElementById("surveyjs-csrf-token") || {}).textContent ||
        "";
      xhr.send(
        "themeJson=" + encodeURIComponent(themeStr) +
        "&_authenticator=" + encodeURIComponent(csrfToken)
      );
    });
  }
});