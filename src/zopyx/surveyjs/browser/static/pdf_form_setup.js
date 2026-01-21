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
  const setupForm = document.getElementById("pdfFormSetupForm");
  const pdfInput = document.getElementById("pdfFormFile");
  const extractionModeSelect = document.getElementById("pdfExtractionMode");
  const uploadBtn = document.getElementById("pdfFormUploadBtn");
  const uploadSpinner = document.getElementById("pdfFormUploadSpinner");
  const statusEl = document.getElementById("pdfFormSetupStatus");
  const previewFrame = document.getElementById("pdfFormPreviewFrame");
  const previewPlaceholder = document.getElementById("pdfFormPreviewPlaceholder");
  const surveyContainer = document.getElementById("pdfFormSurveyContainer");
  const surveyPlaceholder = document.getElementById("pdfFormSurveyPlaceholder");
  const fieldsList = document.getElementById("pdfFormFieldsList");
  const openFormBtn = document.getElementById("openPdfFormBtn");

  if (!setupForm) {
    return;
  }

  let surveyPreview = null;

  function setLoading(isLoading) {
    uploadBtn.disabled = isLoading;
    if (uploadSpinner) {
      uploadSpinner.style.display = isLoading ? "inline-flex" : "none";
    }
    const label = uploadBtn.querySelector(".btn-text");
    if (label) {
      label.style.display = isLoading ? "none" : "inline";
    }
  }

  function showStatus(message, type) {
    statusEl.style.display = "block";
    statusEl.className = "alert " + (type === "success" ? "alert-success" : "alert-danger");
    statusEl.innerHTML = message;
  }

  function renderSurveyPreview(surveyJson) {
    if (!surveyContainer || typeof Survey === "undefined") {
      return;
    }
    if (surveyPlaceholder) {
      surveyPlaceholder.style.display = "none";
    }
    surveyContainer.innerHTML = "";
    const model = new Survey.Model(surveyJson);
    model.locale = locale;
    if (Survey && Survey.surveyLocalization) {
      Survey.surveyLocalization.currentLocale = locale;
    }
    model.render(surveyContainer);
    surveyPreview = model;
  }

  function renderFieldList(fields) {
    if (!fieldsList) {
      return;
    }
    fieldsList.innerHTML = "";
    if (!fields || !fields.length) {
      fieldsList.innerHTML = '<span class="pdf-form-fields-empty">' + t("No fields detected yet.") + "</span>";
      return;
    }
    fields.forEach((field) => {
      const item = document.createElement("div");
      item.className = "pdf-form-field-item";
      const name = document.createElement("span");
      name.className = "pdf-form-field-name";
      name.textContent = field.pdf_name || field.survey_name || t("Field");
      const kind = document.createElement("span");
      kind.className = "pdf-form-field-kind";
      kind.textContent = field.kind ? ("(" + field.kind + ")") : "";
      item.appendChild(name);
      item.appendChild(kind);
      fieldsList.appendChild(item);
    });
  }

  setupForm.addEventListener("submit", function(event) {
    event.preventDefault();
    const file = pdfInput.files[0];
    if (!file) {
      showStatus(t("Please select a PDF file to upload."), "error");
      return;
    }

    const formData = new FormData();
    formData.append("pdf_file", file);
    if (extractionModeSelect) {
      formData.append("extract_mode", extractionModeSelect.value || "pdfcpu");
    }
    formData.append("_authenticator", CSRF_TOKEN);

    setLoading(true);
    statusEl.style.display = "none";
    if (openFormBtn) {
      openFormBtn.style.display = "none";
    }

    fetch(ACTUAL_URL + "/@@upload-pdf-form", {
      method: "POST",
      body: formData,
      credentials: "same-origin"
    })
      .then((response) => {
        if (!response.ok) {
          return response.json().then((data) => {
            throw new Error(data.message || t("Upload failed"));
          });
        }
        return response.json();
      })
      .then((data) => {
        if (!data.success) {
          throw new Error(data.message || t("Upload failed"));
        }
        renderSurveyPreview(data.json || {});
        renderFieldList(data.fields || []);
        const warning = data.warning ? ("<br/><strong>" + data.warning + "</strong>") : "";
        showStatus(
          t(
            "PDF analyzed successfully. The generated form is now available for submissions."
          ) + warning,
          "success"
        );
        if (openFormBtn) {
          if ((data.field_count || 0) > 0) {
            openFormBtn.href = ACTUAL_URL + "/@@pdf-form";
            openFormBtn.style.display = "inline-flex";
          } else {
            openFormBtn.style.display = "none";
          }
        }
      })
      .catch((error) => {
        showStatus(error.message || t("Upload failed. Please try again."), "error");
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
      renderFieldList([]);
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
