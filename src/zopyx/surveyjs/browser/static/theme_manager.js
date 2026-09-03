/**
 * Theme Manager — list, create, delete, upload themes.
 */
(function () {
  var createBtn = document.getElementById("createThemeBtn");
  var createDialog = document.getElementById("createThemeDialog");
  var createCancel = document.getElementById("createDialogCancel");
  var createConfirm = document.getElementById("createDialogConfirm");
  var newThemeName = document.getElementById("newThemeName");

  var deleteDialog = document.getElementById("deleteConfirmDialog");
  var deleteCancel = document.getElementById("deleteDialogCancel");
  var deleteConfirm = document.getElementById("deleteDialogConfirm");
  var deleteThemeName = document.getElementById("deleteThemeName");
  var pendingDeleteId = null;

  var uploadBtn = document.getElementById("uploadThemeBtn");
  var uploadInput = document.getElementById("uploadThemeInput");
  var previewDialog = document.getElementById("themePreviewDialog");
  var previewClose = document.getElementById("themePreviewClose");
  var previewTitle = document.getElementById("themePreviewTitle");
  var previewContainer = document.getElementById("themePreviewContainer");
  var previewSurvey = null;

  var csrfToken = window.CSRF_TOKEN ||
    (document.getElementById("surveyjs-csrf-token") || {}).textContent || "";

  function getBaseUrl() {
    // ACTUAL_URL points to the Plone site root, not this browser view.
    // POSTs must target the current @@theme-manager view.
    return window.location.pathname;
  }

  function getEditorBaseUrl() {
    // ACTUAL_URL is the site root and is suitable for view navigation.
    return (window.ACTUAL_URL || "/").replace(/\/+$/, "");
  }

  function showDialog(dialog) {
    if (dialog) dialog.removeAttribute("hidden");
  }
  function hideDialog(dialog) {
    if (dialog) dialog.setAttribute("hidden", "hidden");
  }

  function reload() {
    window.location.reload();
  }

  // --- Create ---
  if (createBtn && createDialog) {
    createBtn.addEventListener("click", function () {
      if (newThemeName) newThemeName.value = "";
      showDialog(createDialog);
      if (newThemeName) setTimeout(function () { newThemeName.focus(); }, 100);
    });
  }
  if (createCancel && createDialog) {
    createCancel.addEventListener("click", function () { hideDialog(createDialog); });
  }
  if (createConfirm && createDialog) {
    createConfirm.addEventListener("click", function () {
      var name = newThemeName ? newThemeName.value.trim() : "";
      if (!name) return;
      var xhr = new XMLHttpRequest();
      xhr.open("POST", getBaseUrl(), true);
      xhr.setRequestHeader("Content-Type", "application/x-www-form-urlencoded");
      xhr.onload = function () {
        if (xhr.status === 200) {
          try {
            var resp = JSON.parse(xhr.responseText);
            if (resp.success && resp.theme_id) {
              // Navigate to the theme editor; return so reload() below is skipped
              var editorUrl = getEditorBaseUrl() + "/@@theme-editor?theme_id=" + resp.theme_id;
              window.location.href = editorUrl;
              return;
            }
          } catch (e) {}
        }
        reload();
      };
      xhr.send("action=create&name=" + encodeURIComponent(name) +
        "&_authenticator=" + encodeURIComponent(csrfToken));
    });
  }

  function formatDateTime(value) {
    var date = new Date(value);
    if (isNaN(date.getTime())) return value || "";
    return date.toLocaleString(undefined, {
      dateStyle: "medium",
      timeStyle: "medium"
    });
  }

  function previewTheme(themeName, themeJson) {
    if (!previewDialog || !previewContainer || typeof Survey === "undefined") return;
    if (previewSurvey && typeof previewSurvey.dispose === "function") {
      previewSurvey.dispose();
    }
    previewDialog.removeAttribute("hidden");
    previewContainer.innerHTML = "";
    var renderTarget = document.createElement("div");
    previewContainer.appendChild(renderTarget);
    if (previewTitle) previewTitle.textContent = themeName + " — Preview";
    previewSurvey = new Survey.Model({
      title: "Customer feedback",
      description: "A preview of how this theme looks on a form.",
      pages: [{
        name: "page1",
        elements: [
          { type: "text", name: "name", title: "Your name", isRequired: true },
          { type: "radiogroup", name: "satisfaction", title: "How satisfied are you?",
            choices: ["Very satisfied", "Satisfied", "Neutral", "Dissatisfied"] },
          { type: "comment", name: "comments", title: "Additional comments" }
        ]
      }],
      showQuestionNumbers: "off"
    });
    if (themeJson && Object.keys(themeJson).length > 0) previewSurvey.applyTheme(themeJson);
    previewSurvey.render(renderTarget);
  }

  document.addEventListener("click", function (e) {
    var btn = e.target.closest(".preview-btn");
    if (!btn) return;
    try {
      previewTheme(btn.getAttribute("data-theme-name") || "Theme",
        JSON.parse(btn.getAttribute("data-theme-json") || "{}"));
    } catch (err) {
      console.error("ThemeManager: failed to preview theme", err);
    }
  });

  if (previewClose && previewDialog) {
    previewClose.addEventListener("click", function () { hideDialog(previewDialog); });
  }
  if (previewDialog) {
    previewDialog.addEventListener("click", function (e) {
      if (e.target === previewDialog) hideDialog(previewDialog);
    });
  }

  document.querySelectorAll("[data-theme-date]").forEach(function (cell) {
    cell.textContent = formatDateTime(cell.getAttribute("data-date"));
    cell.title = cell.getAttribute("data-date") || "";
  });

  // --- Delete ---
  document.addEventListener("click", function (e) {
    var btn = e.target.closest(".delete-btn");
    if (!btn) return;
    var themeId = btn.getAttribute("data-theme-id");
    var themeName = btn.getAttribute("data-theme-name");
    if (!themeId || !deleteDialog) return;
    pendingDeleteId = themeId;
    if (deleteThemeName) deleteThemeName.textContent = themeName;
    showDialog(deleteDialog);
  });
  if (deleteCancel && deleteDialog) {
    deleteCancel.addEventListener("click", function () {
      hideDialog(deleteDialog);
      pendingDeleteId = null;
    });
  }
  if (deleteConfirm && deleteDialog) {
    deleteConfirm.addEventListener("click", function () {
      if (!pendingDeleteId) return;
      var xhr = new XMLHttpRequest();
      xhr.open("POST", getBaseUrl(), true);
      xhr.setRequestHeader("Content-Type", "application/x-www-form-urlencoded");
      xhr.onload = function () { reload(); };
      xhr.send("action=delete&theme_id=" + encodeURIComponent(pendingDeleteId) +
        "&_authenticator=" + encodeURIComponent(csrfToken));
      hideDialog(deleteDialog);
      pendingDeleteId = null;
    });
  }

  // --- Make default ---
  document.addEventListener("click", function (e) {
    var btn = e.target.closest(".make-default-btn");
    if (!btn) return;
    var themeId = btn.getAttribute("data-theme-id");
    if (!themeId) return;
    var xhr = new XMLHttpRequest();
    xhr.open("POST", getBaseUrl(), true);
    xhr.setRequestHeader("Content-Type", "application/x-www-form-urlencoded");
    xhr.onload = function () { reload(); };
    xhr.send("action=set_default&theme_id=" + encodeURIComponent(themeId) +
      "&_authenticator=" + encodeURIComponent(csrfToken));
  });

  // --- Upload ---
  if (uploadBtn && uploadInput) {
    uploadBtn.addEventListener("click", function () {
      uploadInput.value = "";
      uploadInput.click();
    });
    uploadInput.addEventListener("change", function () {
      var file = uploadInput.files && uploadInput.files[0];
      if (!file) return;
      var reader = new FileReader();
      reader.onload = function (e) {
        var name = file.name.replace(/\.json$/i, "");
        var xhr = new XMLHttpRequest();
        xhr.open("POST", getBaseUrl(), true);
        xhr.setRequestHeader("Content-Type", "application/x-www-form-urlencoded");
        xhr.onload = function () {
          if (xhr.status === 200) {
            try {
              var resp = JSON.parse(xhr.responseText);
              if (resp.success && resp.theme_id) {
                window.location.href = getEditorBaseUrl() +
                  "/@@theme-editor?theme_id=" + resp.theme_id;
                return;
              }
            } catch (e) {}
          }
          alert("Upload failed: " + xhr.responseText);
          reload();
        };
        xhr.send("action=upload&name=" + encodeURIComponent(name) +
          "&theme_file=" + encodeURIComponent(e.target.result) +
          "&_authenticator=" + encodeURIComponent(csrfToken));
      };
      reader.readAsText(file);
    });
  }

  // Close dialogs on overlay click
  document.addEventListener("click", function (e) {
    if (e.target === createDialog) hideDialog(createDialog);
    if (e.target === deleteDialog) { hideDialog(deleteDialog); pendingDeleteId = null; }
  });
  document.addEventListener("keydown", function (e) {
    if (e.key === "Escape") {
      if (createDialog && !createDialog.hasAttribute("hidden")) hideDialog(createDialog);
      if (deleteDialog && !deleteDialog.hasAttribute("hidden")) { hideDialog(deleteDialog); pendingDeleteId = null; }
      if (previewDialog && !previewDialog.hasAttribute("hidden")) hideDialog(previewDialog);
    }
  });
})();