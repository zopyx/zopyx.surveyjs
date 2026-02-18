/**
 * PDF importer view logic for @@pdf-importer.
 * Handles file upload, import lifecycle, and status feedback.
 */
document.addEventListener("DOMContentLoaded", function() {
/**
 * @function
 */
  const t = window._t || function (msgid, mapping) {
    if (!mapping) {
      return msgid;
    }
/**
 * @function
 */
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
  const storeBtn = document.getElementById("storeConvertedBtn");
  const storeSpinner = document.getElementById("storeConvertedSpinner");
  const statusEl = document.getElementById("pdfImporterStatus");
  const previewFrame = document.getElementById("pdfPreviewFrame");
  const previewPlaceholder = document.getElementById("pdfPreviewPlaceholder");
  const surveyPreviewContainer = document.getElementById("surveyPreviewContainer");
  const surveyPreviewPlaceholder = document.getElementById("surveyPreviewPlaceholder");
  const additionalPromptInput = document.getElementById("pdfAdditionalPrompt");
  const pdfcpuValidationCheckbox = document.getElementById("pdfcpuValidationEnabled");

  let surveyPreview = null;
  let convertedJson = null;

  if (!importerForm) {
    return;
  }

/**
 * @function
 */
  function setLoading(isLoading) {
    importBtn.disabled = isLoading;
    if (importSpinner) {
      importSpinner.style.display = isLoading ? "inline-flex" : "none";
    }
    const label = importBtn.querySelector(".btn-text");
    if (label) {
      label.style.display = isLoading ? "none" : "inline";
    }
  }

/**
 * @function
 */
  function setStoreLoading(isLoading) {
    if (storeBtn) {
      storeBtn.disabled = isLoading;
      const label = storeBtn.querySelector(".btn-text");
      if (label) {
        label.style.display = isLoading ? "none" : "inline";
      }
    }
    if (storeSpinner) {
      storeSpinner.style.display = isLoading ? "inline-flex" : "none";
    }
  }

/**
 * @function
 */
  function setStoreEnabled(enabled) {
    if (storeBtn) {
      storeBtn.disabled = !enabled;
      storeBtn.style.display = enabled ? "inline-flex" : "none";
    }
  }

/**
 * @function
 */
  function showStatus(message, type) {
    statusEl.style.display = "block";
    statusEl.className = "alert " + (type === "success" ? "alert-success" : "alert-danger");
    statusEl.innerHTML = message;
  }

/**
 * @function
 */
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

/**
 * @function
 */
  importerForm.addEventListener("submit", function(event) {
    event.preventDefault();

    const file = pdfInput.files[0];
    if (!file) {
      showStatus(t("Please select a PDF file to upload."), "error");
      return;
    }

    const formData = new FormData();
    formData.append("pdf_file", file);
    if (additionalPromptInput && additionalPromptInput.value.trim()) {
      formData.append("additional_prompt", additionalPromptInput.value.trim());
    }
    if (pdfcpuValidationCheckbox) {
      formData.append(
        "pdfcpu_validation",
        pdfcpuValidationCheckbox.checked ? "1" : "0"
      );
    }
    formData.append("_authenticator", CSRF_TOKEN);

    setLoading(true);
    setStoreEnabled(false);
    statusEl.style.display = "none";

    fetch(ACTUAL_URL + "/@@import-pdf-form", {
      method: "POST",
      body: formData,
      credentials: "same-origin"
    })
/**
 * @function
 */
    .then(response => {
      if (!response.ok) {
/**
 * @function
 */
        return response.json().then(data => {
          throw new Error(data.message || t("Import failed"));
        });
      }
      return response.json();
    })
/**
 * @function
 */
    .then(data => {
      if (data.success) {
        showStatus(
          t(
            "Conversion complete. Review the preview and click “Store converted form as new version”."
          ),
          "success"
        );
        if (data.json) {
          convertedJson = data.json;
          setStoreEnabled(true);
          renderSurveyPreview(data.json);
        }
      } else {
        throw new Error(data.message || t("Import failed"));
      }
    })
/**
 * @function
 */
    .catch(error => {
      showStatus(error.message || t("Import failed. Please try again."), "error");
    })
/**
 * @function
 */
    .finally(() => {
      setLoading(false);
    });
  });

  if (storeBtn) {
/**
 * @function
 */
    storeBtn.addEventListener("click", function() {
      if (!convertedJson) {
        showStatus(t("No converted form available to store."), "error");
        return;
      }

      setStoreLoading(true);
      statusEl.style.display = "none";

      const formData = new FormData();
      formData.append("survey_json", JSON.stringify(convertedJson));
      formData.append("_authenticator", CSRF_TOKEN);

      fetch(ACTUAL_URL + "/@@store-pdf-form", {
        method: "POST",
        body: formData,
        credentials: "same-origin"
      })
/**
 * @function
 */
      .then(response => {
        if (!response.ok) {
/**
 * @function
 */
          return response.json().then(data => {
            throw new Error(data.message || t("Store failed"));
          });
        }
        return response.json();
      })
/**
 * @function
 */
      .then(data => {
        if (data.success) {
          const versionsUrl = ACTUAL_URL + "/@@form-versions";
          showStatus(
            t(
              "Converted form stored. <a href=\"${url}\">View versions</a>.",
              { url: versionsUrl }
            ),
            "success"
          );
          setStoreEnabled(false);
        } else {
          throw new Error(data.message || t("Store failed"));
        }
      })
/**
 * @function
 */
      .catch(error => {
        showStatus(error.message || t("Store failed. Please try again."), "error");
      })
/**
 * @function
 */
      .finally(() => {
        setStoreLoading(false);
      });
    });
  }

/**
 * @function
 */
  pdfInput.addEventListener("change", function() {
    const file = pdfInput.files[0];
    convertedJson = null;
    setStoreEnabled(false);
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
