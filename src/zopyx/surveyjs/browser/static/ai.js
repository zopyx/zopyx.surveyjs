document.addEventListener("DOMContentLoaded", function() {

  // DOM Elements
  const form = document.getElementById("aiGeneratorForm");
  const promptInput = document.getElementById("promptInput");
  const generateBtn = document.getElementById("generateBtn");
  const btnText = generateBtn.querySelector(".btn-text");
  const btnSpinner = generateBtn.querySelector(".btn-spinner");

  const errorContainer = document.getElementById("errorContainer");
  const errorMessage = document.getElementById("errorMessage");

  const jsonContainer = document.getElementById("jsonContainer");
  const jsonDisplay = document.getElementById("jsonDisplay");
  const previewBtn = document.getElementById("previewBtn");
  const saveBtn = document.getElementById("saveBtn");

  const modal = document.getElementById("previewModal");
  const closeButton = document.querySelector(".close-button");
  const surveyContainer = document.getElementById("surveyContainer");

  // Store generated JSON
  let generatedJson = null;
  let survey = null;

  // Form submission handler
  form.addEventListener("submit", function(e) {
    e.preventDefault();

    const prompt = promptInput.value.trim();
    if (!prompt) {
      showError("Please enter a description for your survey");
      return;
    }

    // Show loading state
    setLoadingState(true);
    hideError();
    hideJson();

    // Prepare form data
    const formData = new FormData();
    formData.append("prompt", prompt);
    formData.append("_authenticator", CSRF_TOKEN);

    // Send AJAX request
    fetch(ACTUAL_URL + "/@@generate-ai-form", {
      method: "POST",
      body: formData,
      credentials: 'same-origin'
    })
    .then(response => {
      if (!response.ok) {
        return response.json().then(data => {
          throw new Error(data.message || "Generation failed");
        });
      }
      return response.json();
    })
    .then(data => {
      if (data.success) {
        generatedJson = data.json;
        displayJson(data.json);
        showJson();
      } else {
        throw new Error(data.message || "Generation failed");
      }
    })
    .catch(error => {
      console.error("Error generating form:", error);
      showError(error.message || "Failed to generate form. Please try again.");
    })
    .finally(() => {
      setLoadingState(false);
    });
  });

  // Preview button handler
  previewBtn.addEventListener("click", function() {
    if (!generatedJson) {
      showError("No form to preview");
      return;
    }

    // Clear previous survey if exists
    if (survey) {
        if (typeof survey.clear === 'function') {
            survey.clear();
        }
        survey = null;
    }

    // Completely clear and recreate the container with a unique ID
    surveyContainer.innerHTML = "";
    const renderTarget = document.createElement("div");
    renderTarget.id = "surveyRenderTarget_" + Date.now();
    surveyContainer.appendChild(renderTarget);

    try {
      // Create fresh survey instance
      survey = new Survey.Model(generatedJson);

      // Disable completion (preview only)
      survey.showCompleteButton = false;
      survey.showPreviewBeforeComplete = "showAnsweredQuestions";

      // Render survey to the fresh container
      survey.render(renderTarget);

      // Show modal
      modal.style.display = "block";
    } catch (error) {
      console.error("Error rendering preview:", error);
      showError("Failed to render preview: " + error.message);
    }
  });

  // Save button handler
  saveBtn.addEventListener("click", function() {
    if (!generatedJson) {
      showError("No form to save");
      return;
    }

    // Disable button during save
    saveBtn.disabled = true;
    const originalText = saveBtn.innerHTML;
    saveBtn.innerHTML = '<span class="spinner"></span> Saving...';

    // Prepare form data
    const formData = new FormData();
    formData.append("form_json", JSON.stringify(generatedJson));
    formData.append("_authenticator", CSRF_TOKEN);

    // Send AJAX request
    fetch(ACTUAL_URL + "/@@save-ai-form", {
      method: "POST",
      body: formData,
      credentials: 'same-origin'
    })
    .then(response => {
      if (!response.ok) {
        return response.json().then(data => {
          throw new Error(data.message || "Save failed");
        });
      }
      return response.json();
    })
    .then(data => {
      if (data.success) {
        // Show success message
        alert("Form saved successfully! You can now view it in the Form Creator or Form Versions.");

        // Optionally redirect to form versions
        // window.location.href = ACTUAL_URL + "/@@form-versions";
      } else {
        throw new Error(data.message || "Save failed");
      }
    })
    .catch(error => {
      console.error("Error saving form:", error);
      showError("Failed to save form: " + (error.message || "Unknown error"));
    })
    .finally(() => {
      saveBtn.disabled = false;
      saveBtn.innerHTML = originalText;
    });
  });

  // Close modal handlers
  closeButton.addEventListener("click", function() {
    modal.style.display = "none";
    if (survey && typeof survey.destroy === 'function') {
        survey.destroy();
        survey = null;
    }
    surveyContainer.innerHTML = "";
  });

  window.addEventListener("click", function(event) {
    if (event.target === modal) {
      modal.style.display = "none";
      if (survey && typeof survey.destroy === 'function') {
          survey.destroy();
          survey = null;
      }
      surveyContainer.innerHTML = "";
    }
  });

  // Helper functions
  function setLoadingState(loading) {
    generateBtn.disabled = loading;
    if (loading) {
      btnText.style.display = "none";
      btnSpinner.style.display = "inline";
    } else {
      btnText.style.display = "inline";
      btnSpinner.style.display = "none";
    }
  }

  function showError(message) {
    errorMessage.textContent = message;
    errorContainer.style.display = "block";
  }

  function hideError() {
    errorContainer.style.display = "none";
  }

  function displayJson(json) {
    jsonDisplay.textContent = JSON.stringify(json, null, 2);
  }

  function showJson() {
    jsonContainer.style.display = "block";
  }

  function hideJson() {
    jsonContainer.style.display = "none";
  }

});
