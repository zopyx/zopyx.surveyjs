/**
 * Theme Editor — standalone SurveyJS Creator with only the Theme tab.
 * - Loads theme JSON from the server
 * - Save New Version, Restore Version, Import, Export
 */
SurveyCreatorCore.registerSurveyTheme(SurveyTheme);

document.addEventListener("DOMContentLoaded", function () {

  var t = window._t || function (msgid, mapping) {
    if (!mapping) {
      return msgid;
    }
    return msgid.replace(/\$\{([a-zA-Z0-9_]+)\}/g, function (match, key) {
      if (Object.prototype.hasOwnProperty.call(mapping, key)) {
        return String(mapping[key]);
      }
      return match;
    });
  };

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
    showLogicTab: false,
    showJSONEditorTab: false,
    showToolbox: false,
    showSidebar: true,
    showState: false,
  });
  creator.activeTab = "theme";

  // Representative sample form for preview
  creator.JSON = {
    "locale": "en",
    "title": t("Customer Satisfaction Survey"),
    "description": t("Please share your experience with us."),
    "pages": [{
      "name": "page1",
      "title": t("About You"),
      "elements": [
        { "type": "text", "name": "full_name", "title": t("Full Name *"), "isRequired": true, "placeholder": t("Enter your name") },
        { "type": "text", "name": "email", "title": t("Email *"), "isRequired": true, "inputType": "email" },
        { "type": "radiogroup", "name": "age_group", "title": t("Age Group"), "choices": [{ "value": "18_30", "text": "18–30" }, { "value": "31_45", "text": "31–45" }, { "value": "46_60", "text": "46–60" }], "colCount": 2 },
        { "type": "checkbox", "name": "interests", "title": t("Interests"), "choices": [{ "value": "tech", "text": t("Technology") }, { "value": "sports", "text": t("Sports") }, { "value": "music", "text": t("Music") }], "colCount": 2 }
      ]
    }, {
      "name": "page2",
      "title": t("Feedback"),
      "elements": [
        { "type": "rating", "name": "satisfaction", "title": t("Overall Satisfaction"), "rateCount": 5, "rateType": "labels" },
        { "type": "boolean", "name": "recommend", "title": t("Would you recommend us?") },
        { "type": "comment", "name": "suggestions", "title": t("Suggestions"), "rows": 3 },
        { "type": "file", "name": "attachment", "title": t("Attach File") }
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
            t("Version ${number} · ${date}", {number: latestVersion.number, date: formatDateTime(latestVersion.created)}) : t("version unknown");
          showToast(t("Theme loaded: ${name} · ${version}", {name: themeName, version: versionText}));
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
          showToast(t("Theme loaded: ${name} · ${version}", {name: themeName, version: t("version ${number}", {number: 1})}));
        }
      } catch (e) {
        renderCreator();
        showToast(t("Theme could not be loaded"), true);
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
      setStatus(t("No theme to save"), true);
      return;
    }
    var themeStr = JSON.stringify(theme, null, 2);
    postData({ action: action, themeJson: themeStr }, function (resp, status) {
      if (resp && resp.success) {
        setStatus(t(successMessage, {count: resp.versions ? resp.versions.length : "?"}));
      } else {
        setStatus(t("Save failed: ${error}", {error: (resp && resp.error) || ("HTTP " + status)}), true);
      }
    });
  }

  if (saveCurrentBtn) {
    saveCurrentBtn.addEventListener("click", function () {
      saveTheme("save_current", "Theme saved (${count} versions)");
    });
  }
  if (saveVersionBtn) {
    saveVersionBtn.addEventListener("click", function () {
      saveTheme("save_version", "New version saved (${count} versions)");
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
      versions.forEach(function (v, index) {
        var tr = document.createElement("tr");
        var td1 = document.createElement("td");
        // New payloads include the stable number; derive it for older or
        // cached payloads where the field is not present yet.
        var versionNumber = Number(v.number) || (versions.length - index);
        td1.textContent = t("Version ${number}", {number: versionNumber});
        var td2 = document.createElement("td");
        td2.textContent = formatDateTime(v.created);
        td2.title = v.created;
        var td3 = document.createElement("td");
        td3.textContent = v.user;
        var td4 = document.createElement("td");
        var btn = document.createElement("button");
        btn.className = "btn btn-sm btn-primary";
        btn.textContent = t("Restore");
        btn.addEventListener("click", function () {
          postData({ action: "restore_version", version_id: v.id }, function (resp, status) {
            if (resp && resp.success && resp.theme_json) {
              creator.theme = resp.theme_json;
              setStatus(t("Restored version from ${date}", {date: v.created}));
              if (restoreModal) restoreModal.setAttribute("hidden", "hidden");
            } else {
              setStatus(t("Restore failed: ${error}", {error: (resp && resp.error) || ("HTTP " + status)}), true);
            }
          });
        });
        td4.appendChild(btn);
        tr.appendChild(td1);
        tr.appendChild(td2);
        tr.appendChild(td3);
        tr.appendChild(td4);
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

  // --- View theme JSON (read-only modal) ---
  var viewJsonBtn = document.getElementById("viewJsonBtn");
  var viewJsonModal = document.getElementById("viewJsonModal");
  var viewJsonText = document.getElementById("viewJsonText");
  var viewJsonCloseBtn = document.getElementById("viewJsonCloseBtn");
  var viewJsonCancel = document.getElementById("viewJsonCancel");
  var viewJsonCopyBtn = document.getElementById("viewJsonCopyBtn");

  function closeJsonModal() {
    if (viewJsonModal) viewJsonModal.setAttribute("hidden", "hidden");
    if (viewJsonCopyBtn) {
      viewJsonCopyBtn.textContent = t("Copy");
      viewJsonCopyBtn.disabled = false;
    }
  }
  function copyJsonToClipboard() {
    var text = viewJsonText ? viewJsonText.value : "";
    if (!text) {
      setStatus(t("Nothing to copy"), true);
      return;
    }
    function done() {
      if (!viewJsonCopyBtn) return;
      viewJsonCopyBtn.textContent = t("Copied ✓");
      setStatus(t("Theme JSON copied to clipboard"));
      setTimeout(function () {
        viewJsonCopyBtn.textContent = t("Copy");
      }, 2000);
    }
    function fallback() {
      try {
        viewJsonText.removeAttribute("readonly");
        viewJsonText.select();
        viewJsonText.setSelectionRange(0, text.length);
        var ok = document.execCommand("copy");
        viewJsonText.setAttribute("readonly", "readonly");
        if (ok) done();
        else setStatus(t("Copy failed"), true);
      } catch (e) {
        viewJsonText.setAttribute("readonly", "readonly");
        setStatus(t("Copy failed: ${error}", {error: e.message}), true);
      }
    }
    if (navigator.clipboard && navigator.clipboard.writeText) {
      navigator.clipboard.writeText(text).then(done, fallback);
    } else {
      fallback();
    }
  }
  if (viewJsonBtn && viewJsonModal) {
    viewJsonBtn.addEventListener("click", function () {
      var theme = creator.theme;
      if (!theme || Object.keys(theme).length === 0) {
        setStatus(t("No theme to show"), true);
        return;
      }
      viewJsonText.value = JSON.stringify(theme, null, 2);
      viewJsonModal.removeAttribute("hidden");
    });
    if (viewJsonCloseBtn) {
      viewJsonCloseBtn.addEventListener("click", closeJsonModal);
    }
    if (viewJsonCancel) {
      viewJsonCancel.addEventListener("click", closeJsonModal);
    }
    if (viewJsonCopyBtn) {
      viewJsonCopyBtn.addEventListener("click", copyJsonToClipboard);
    }
    viewJsonModal.addEventListener("click", function (e) {
      if (e.target === viewJsonModal) closeJsonModal();
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
            setStatus(t("Invalid theme JSON"), true);
            return;
          }
          creator.theme = themeJson;
          setStatus(t("Imported: ${name}", {name: file.name}));
        } catch (err) {
          setStatus(t("Parse error: ${error}", {error: err.message}), true);
        }
      };
      reader.readAsText(file);
    });
  }

  // --- Export (download JSON) ---
  var exportBtn = document.getElementById("exportThemeBtn");
  if (exportBtn) {
    exportBtn.addEventListener("click", function () {
      var theme = creator.theme;
      if (!theme || Object.keys(theme).length === 0) {
        setStatus(t("No theme to export"), true);
        return;
      }
      var params = [
        "action=export_theme",
        "themeJson=" + encodeURIComponent(JSON.stringify(theme, null, 2)),
        "_authenticator=" + encodeURIComponent(csrfToken)
      ];
      var xhr = new XMLHttpRequest();
      xhr.open("POST", baseUrl, true);
      xhr.setRequestHeader("Content-Type", "application/x-www-form-urlencoded");
      xhr.responseType = "blob";
      xhr.onload = function () {
        if (xhr.status !== 200) {
          setStatus(t("Export failed: HTTP ${status}", {status: xhr.status}), true);
          return;
        }
        var filename = themeName + ".json";
        var disposition = xhr.getResponseHeader("Content-Disposition") || "";
        var match = disposition.match(/filename="?([^";]+)"?/i);
        if (match) filename = match[1];
        var url = URL.createObjectURL(xhr.response);
        var link = document.createElement("a");
        link.href = url;
        link.download = filename;
        document.body.appendChild(link);
        link.click();
        link.remove();
        setTimeout(function () { URL.revokeObjectURL(url); }, 1000);
        setStatus(t("Exported ${name}", {name: filename}));
      };
      xhr.onerror = function () {
        setStatus(t("Export failed"), true);
      };
      xhr.send(params.join("&"));
    });
  }
});
