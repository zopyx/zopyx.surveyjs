document.addEventListener("DOMContentLoaded", function() {
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
    model.render(surveyPreviewContainer);
    surveyPreview = model;
  }

  importerForm.addEventListener("submit", function(event) {
    event.preventDefault();

    const file = pdfInput.files[0];
    if (!file) {
      showStatus("Please select a PDF file to upload.", "error");
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
          throw new Error(data.message || "Import failed");
        });
      }
      return response.json();
    })
    .then(data => {
      if (data.success) {
        const versionsUrl = ACTUAL_URL + "/@@form-versions";
        showStatus(
          "Form imported and saved as a new version. " +
            "<a href=\"" + versionsUrl + "\">View versions</a>.",
          "success"
        );
        if (data.json) {
          renderSurveyPreview(data.json);
        }
        importerForm.reset();
      } else {
        throw new Error(data.message || "Import failed");
      }
    })
    .catch(error => {
      showStatus(error.message || "Import failed. Please try again.", "error");
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
