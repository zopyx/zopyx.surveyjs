document.addEventListener("DOMContentLoaded", function() {
  const t = window._t || function (msgid, mapping) {
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
  const locale = window.SURVEYJS_I18N_LOCALE || navigator.language || "en";
  const importerForm = document.getElementById("pdfImporterForm");
  const pdfInput = document.getElementById("pdfFile");
  const importBtn = document.getElementById("importBtn");
  const importSpinner = document.getElementById("importSpinner");
  const statusEl = document.getElementById("pdfImporterStatus");
  const previewFrame = document.getElementById("pdfPreviewFrame");
  const previewPlaceholder = document.getElementById("pdfPreviewPlaceholder");
  const surveyPreviewContainer = document.getElementById("surveyPreviewContainer");
  const surveyPreviewPlaceholder = document.getElementById("surveyPreviewPlaceholder");

  let surveyPreview = null;

  if (!importerForm) {
    return;
  }

  function setLoading(isLoading) {
    importBtn.disabled = isLoading;
    if (importSpinner) {
      importSpinner.style.display = isLoading ? "inline-flex" : "none";
    }
  }

  function showStatus(message, type) {
    statusEl.style.display = "block";
    statusEl.className = "alert " + (type === "success" ? "alert-success" : "alert-danger");
    statusEl.innerHTML = message;
  }

  function renderSurveyPreview(surveyJson) {
    if (!surveyPreviewContainer || typeof Survey === "undefined") {
      return;
    }

    if (surveyPreviewPlaceholder) {
      surveyPreviewPlaceholder.style.display = "none";
    }

    surveyPreviewContainer.innerHTML = "";
    const model = new Survey.Model(surveyJson);
    model.locale = locale;
    if (Survey && Survey.surveyLocalization) {
      Survey.surveyLocalization.currentLocale = locale;
    }
    model.render(surveyPreviewContainer);
    surveyPreview = model;
  }

  importerForm.addEventListener("submit", function(event) {
    event.preventDefault();

    const file = pdfInput.files[0];
    if (!file) {
      showStatus(t("Please select a PDF file to upload."), "error");
      return;
    }

    const formData = new FormData();
    formData.append("pdf_file", file);
    formData.append("_authenticator", CSRF_TOKEN);

    setLoading(true);
    statusEl.style.display = "none";

    fetch(ACTUAL_URL + "/@@import-pdf-form", {
      method: "POST",
      body: formData,
      credentials: "same-origin"
    })
    .then(response => {
      if (!response.ok) {
        return response.json().then(data => {
          throw new Error(data.message || t("Import failed"));
        });
      }
      return response.json();
    })
    .then(data => {
      if (data.success) {
        const versionsUrl = ACTUAL_URL + "/@@form-versions";
        showStatus(
          t(
            "Form imported and saved as a new version. <a href=\"${url}\">View versions</a>.",
            { url: versionsUrl }
          ),
          "success"
        );
        if (data.json) {
          renderSurveyPreview(data.json);
        }
        importerForm.reset();
      } else {
        throw new Error(data.message || t("Import failed"));
      }
    })
    .catch(error => {
      showStatus(error.message || t("Import failed. Please try again."), "error");
    })
    .finally(() => {
      setLoading(false);
    });
  });

  pdfInput.addEventListener("change", function() {
    const file = pdfInput.files[0];
    if (!file) {
      if (previewFrame) {
        previewFrame.style.display = "none";
        previewFrame.removeAttribute("src");
      }
      if (previewPlaceholder) {
        previewPlaceholder.style.display = "flex";
      }
      return;
    }

    if (previewFrame && file.type === "application/pdf") {
      const objectUrl = URL.createObjectURL(file);
      previewFrame.src = objectUrl;
      previewFrame.style.display = "block";
      if (previewPlaceholder) {
        previewPlaceholder.style.display = "none";
      }
    }
  });
});
