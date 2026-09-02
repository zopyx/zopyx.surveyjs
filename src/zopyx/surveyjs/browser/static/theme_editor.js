/**
 * Theme Editor — standalone SurveyJS Creator with only the Theme tab.
 * - Loads theme JSON from the server
 * - Save New Version, Restore Version, Import, Export
 */
SurveyCreatorCore.registerSurveyTheme(SurveyTheme);

document.addEventListener("DOMContentLoaded", function () {

  var configEl = document.getElementById("survey-editor-config");
  var licenseKey = configEl ? configEl.getAttribute("data-license-key") || "" : "";
  var themeId = configEl ? configEl.getAttribute("data-theme-id") || "" : "";
  var themeName = configEl ? configEl.getAttribute("data-theme-name") || "" : "";

  if (licenseKey) {
    if (typeof SurveyCreator !== "undefined" && SurveyCreator.slk) SurveyCreator.slk(licenseKey);
    if (typeof SurveyCreatorCore !== "undefined" && SurveyCreatorCore.slk) SurveyCreatorCore.slk(licenseKey);
    if (typeof Survey !== "undefined" && Survey.slk) Survey.slk(licenseKey);
  }

  var creator = new SurveyCreator.SurveyCreator({
    showDesignerTab: false,
    showSurveySettingsTab: false,
    showTranslationTab: false,
    showThemeTab: true,
    showToolbox: false,
    showSidebar: true,
    showState: false,
  });
  creator.activeTab = "theme";

  // Representative sample form for preview
  creator.JSON = {
    "locale": "en",
    "title": "Customer Satisfaction Survey",
    "description": "Please share your experience with us.",
    "pages": [{
      "name": "page1",
      "title": "About You",
      "elements": [
        { "type": "text", "name": "full_name", "title": "Full Name *", "isRequired": true, "placeholder": "Enter your name" },
        { "type": "text", "name": "email", "title": "Email *", "isRequired": true, "inputType": "email" },
        { "type": "radiogroup", "name": "age_group", "title": "Age Group", "choices": [{ "value": "18_30", "text": "18–30" }, { "value": "31_45", "text": "31–45" }, { "value": "46_60", "text": "46–60" }], "colCount": 2 },
        { "type": "checkbox", "name": "interests", "title": "Interests", "choices": [{ "value": "tech", "text": "Technology" }, { "value": "sports", "text": "Sports" }, { "value": "music", "text": "Music" }], "colCount": 2 }
      ]
    }, {
      "name": "page2",
      "title": "Feedback",
      "elements": [
        { "type": "rating", "name": "satisfaction", "title": "Overall Satisfaction", "rateCount": 5, "rateType": "labels" },
        { "type": "boolean", "name": "recommend", "title": "Would you recommend us?" },
        { "type": "comment", "name": "suggestions", "title": "Suggestions", "rows": 3 },
        { "type": "file", "name": "attachment", "title": "Attach File" }
      ]
    }],
    "showProgressBar": "aboveHeader",
    "progressBarType": "pages",
    "widthMode": "static",
    "width": 800
  };

  var csrfToken = window.CSRF_TOKEN ||
    (document.getElementById("surveyjs-csrf-token") || {}).textContent || "";
  // Keep the theme_id query parameter: the view reads it from the request
  // when handling POST actions.
  var baseUrl = window.location.pathname + window.location.search;

  function setStatus(msg, isError) {
    var el = document.getElementById("themeStatus");
    if (!el) return;
    el.textContent = msg;
    el.style.color = isError ? "#dc2626" : "#16a34a";
  }

  function postData(data, callback) {
    var params = [];
    for (var key in data) {
      if (data.hasOwnProperty(key)) {
        params.push(encodeURIComponent(key) + "=" + encodeURIComponent(data[key]));
      }
    }
    params.push("_authenticator=" + encodeURIComponent(csrfToken));
    var xhr = new XMLHttpRequest();
    xhr.open("POST", baseUrl, true);
    xhr.setRequestHeader("Content-Type", "application/x-www-form-urlencoded");
    xhr.onload = function () {
      var resp = null;
      try { resp = JSON.parse(xhr.responseText); } catch (e) {}
      callback(resp, xhr.status);
    };
    xhr.onerror = function () { callback(null, 0); };
    xhr.send(params.join("&"));
  }

  function showToast(message, isError) {
    var toast = document.createElement("div");
    toast.className = "theme-toast" + (isError ? " theme-toast-error" : "");
    toast.setAttribute("role", isError ? "alert" : "status");
    toast.setAttribute("aria-live", isError ? "assertive" : "polite");
    toast.textContent = message;
    document.body.appendChild(toast);
    setTimeout(function () {
      toast.classList.add("theme-toast-hidden");
      setTimeout(function () { toast.remove(); }, 220);
    }, 4200);
  }

  function getLatestVersionInfo() {
    try {
      var versionsEl = document.getElementById("theme-versions-data");
      var versions = JSON.parse(versionsEl.textContent || "[]");
      return versions.length ? {
        number: versions.length,
        created: versions[0].created
      } : null;
    } catch (e) {
      return null;
    }
  }

  function syncThemeControls(theme) {
    var palette = theme && theme.colorPalette;
    var panelless = theme && theme.isPanelless;
    var paletteInput = palette && document.querySelector(
      "#surveyContainer input[type=radio][value='" + palette + "']"
    );
    var panellessInput = document.querySelector(
      "#surveyContainer input[type=radio][value='" + String(!!panelless) + "']"
    );
    if (paletteInput && paletteInput.parentElement) paletteInput.parentElement.click();
    if (panellessInput && panellessInput.parentElement) panellessInput.parentElement.click();
  }

  var creatorRendered = false;
  function renderCreator() {
    if (creatorRendered) return;
    creator.render("surveyContainer");
    creator.activeTab = "theme";
    creatorRendered = true;
  }

  function loadTheme() {
    var xhr = new XMLHttpRequest();
    xhr.open("POST", baseUrl, true);
    xhr.setRequestHeader("Content-Type", "application/x-www-form-urlencoded");
    xhr.onload = function () {
      try {
        var resp = JSON.parse(xhr.responseText);
        if (resp && typeof resp === "object" && Object.keys(resp).length > 0) {
          creator.theme = resp;
          creator.activeTab = "theme";
          var latestVersion = getLatestVersionInfo();
          var versionText = latestVersion ?
            "Version " + latestVersion.number + " · " + formatDateTime(latestVersion.created) : "version unknown";
          showToast("Theme loaded: " + themeName + " · " + versionText);
          renderCreator();
          if (creator.themeEditor && typeof creator.themeEditor.addTheme === "function") {
            creator.themeEditor.addTheme(resp, true);
          }
          syncThemeControls(resp);
          creator.theme = resp;
          creator.activeTab = "theme";
          console.log("ThemeEditor: loaded theme JSON", resp);
        } else {
          renderCreator();
          showToast("Theme loaded: " + themeName + " · version 1");
        }
      } catch (e) {
        renderCreator();
        showToast("Theme could not be loaded", true);
        console.log("ThemeEditor: no existing theme, starting fresh");
      }
    };
    xhr.send("action=get_theme_data&_authenticator=" + encodeURIComponent(csrfToken));
  }

  loadTheme();

  // --- Save current / save new version ---
  var saveCurrentBtn = document.getElementById("saveCurrentBtn");
  var saveVersionBtn = document.getElementById("saveVersionBtn");

  function saveTheme(action, successMessage) {
    var theme = creator.theme;
    if (!theme || Object.keys(theme).length === 0) {
      setStatus("No theme to save", true);
      return;
    }
    var themeStr = JSON.stringify(theme, null, 2);
    postData({ action: action, themeJson: themeStr }, function (resp, status) {
      if (resp && resp.success) {
        setStatus(successMessage + " (" + (resp.versions ? resp.versions.length : "?") + " versions)");
      } else {
        setStatus("Save failed: " + ((resp && resp.error) || "HTTP " + status), true);
      }
    });
  }

  if (saveCurrentBtn) {
    saveCurrentBtn.addEventListener("click", function () {
      saveTheme("save_current", "Theme saved");
    });
  }
  if (saveVersionBtn) {
    saveVersionBtn.addEventListener("click", function () {
      saveTheme("save_version", "New version saved");
    });
  }

  // --- Restore Version ---
  var restoreBtn = document.getElementById("restoreBtn");
  var restoreModal = document.getElementById("restoreModal");
  var restoreModalClose = document.getElementById("restoreModalCloseBtn");
  var restoreModalCancel = document.getElementById("restoreModalCancel");
  var versionsTable = document.getElementById("versionsTable");

  function formatDateTime(value) {
    var date = new Date(value);
    if (isNaN(date.getTime())) return value || "";
    return date.toLocaleString(undefined, {
      dateStyle: "medium",
      timeStyle: "medium"
    });
  }

  function populateVersions() {
    if (!versionsTable) return;
    var tbody = versionsTable.querySelector("tbody");
    if (!tbody) return;
    try {
      var versionsEl = document.getElementById("theme-versions-data");
      var versions = JSON.parse(versionsEl.textContent || "[]");
      tbody.innerHTML = "";
      versions.forEach(function (v) {
        var tr = document.createElement("tr");
        var td1 = document.createElement("td");
        td1.textContent = formatDateTime(v.created);
        td1.title = v.created;
        var td2 = document.createElement("td");
        td2.textContent = v.user;
        var td3 = document.createElement("td");
        var btn = document.createElement("button");
        btn.className = "btn btn-sm btn-primary";
        btn.textContent = "Restore";
        btn.addEventListener("click", function () {
          postData({ action: "restore_version", version_id: v.id }, function (resp, status) {
            if (resp && resp.success && resp.theme_json) {
              creator.theme = resp.theme_json;
              setStatus("Restored version from " + v.created);
              if (restoreModal) restoreModal.setAttribute("hidden", "hidden");
            } else {
              setStatus("Restore failed: " + ((resp && resp.error) || "HTTP " + status), true);
            }
          });
        });
        td3.appendChild(btn);
        tr.appendChild(td1);
        tr.appendChild(td2);
        tr.appendChild(td3);
        tbody.appendChild(tr);
      });
    } catch (e) {
      console.error("ThemeEditor: failed to parse versions", e);
    }
  }

  if (restoreBtn && restoreModal) {
    restoreBtn.addEventListener("click", function () {
      populateVersions();
      restoreModal.removeAttribute("hidden");
    });
  }
  if (restoreModalClose && restoreModal) {
    restoreModalClose.addEventListener("click", function () {
      restoreModal.setAttribute("hidden", "hidden");
    });
  }
  if (restoreModalCancel && restoreModal) {
    restoreModalCancel.addEventListener("click", function () {
      restoreModal.setAttribute("hidden", "hidden");
    });
  }
  if (restoreModal) {
    restoreModal.addEventListener("click", function (e) {
      if (e.target === restoreModal) restoreModal.setAttribute("hidden", "hidden");
    });
  }

  // --- Import ---
  var importBtn = document.getElementById("importThemeBtn");
  var importInput = document.getElementById("importThemeInput");
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
          setStatus("Imported: " + file.name);
        } catch (err) {
          setStatus("Parse error: " + err.message, true);
        }
      };
      reader.readAsText(file);
    });
  }

  // --- Export to /tmp ---
  var exportBtn = document.getElementById("exportThemeBtn");
  if (exportBtn) {
    exportBtn.addEventListener("click", function () {
      var theme = creator.theme;
      if (!theme || Object.keys(theme).length === 0) {
        setStatus("No theme to export", true);
        return;
      }
      var themeStr = JSON.stringify(theme, null, 2);
      postData({ action: "export_theme", themeJson: themeStr }, function (resp, status) {
        if (resp && resp.success) {
          setStatus("Exported to " + resp.path);
        } else {
          setStatus("Export failed: " + ((resp && resp.error) || "HTTP " + status), true);
        }
      });
    });
  }
});