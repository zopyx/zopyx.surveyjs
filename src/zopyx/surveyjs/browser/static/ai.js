/**
 * AI generator view interactions.
 * Handles form submission, progress polling, and error display for @@ai.
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

  // DOM Elements
  const refinementForm = document.getElementById("refinementForm");
  const refinementInput = document.getElementById("refinementInput");
  const refineBtn = document.getElementById("refineBtn");
  const refineBtnText = document.getElementById("refineBtnText");
  const refineBtnSpinnerText = document.getElementById("refineBtnSpinnerText");
  const startOverBtn = document.getElementById("startOverBtn");

  const formPanelTitle = document.getElementById("formPanelTitle");
  const formInputLabel = document.getElementById("formInputLabel");
  const formInputHelp = document.getElementById("formInputHelp");
  const refineExistingCheckbox = document.getElementById("refineExisting");
  const versionIndicator = document.getElementById("versionIndicator");
  const currentVersionInfo = document.getElementById("currentVersionInfo");
  const formActionButtons = document.getElementById("formActionButtons");

  const errorContainer = document.getElementById("errorContainer");
  const errorMessage = document.getElementById("errorMessage");

  const historyTimeline = document.getElementById("historyTimeline");

  const previewJsonBtn = document.getElementById("previewJsonBtn");
  const previewFormBtn = document.getElementById("previewFormBtn");
  const saveBtn = document.getElementById("saveBtn");

  const previewFormModal = document.getElementById("previewFormModal");
  const previewJsonModal = document.getElementById("previewJsonModal");
  const closeFormPreview = document.querySelector(".close-form-preview");
  const closeJsonPreview = document.querySelector(".close-json-preview");
  const surveyContainer = document.getElementById("surveyContainer");
  const jsonModalDisplay = document.getElementById("jsonModalDisplay");

  // Store generated JSON
  let generatedJson = null;
  let survey = null;

  // Application State
  const AppState = {
    refinementHistory: [],
    currentHistoryIndex: -1,

/**
 * @function
 */
    addVersion: function(prompt, json, type) {
      this.refinementHistory.push({
        id: generateUUID(),
        timestamp: Date.now(),
        prompt: prompt,
        json: json,
        type: type  // "initial" or "refinement"
      });
      this.currentHistoryIndex = this.refinementHistory.length - 1;
    },

/**
 * @function
 */
    navigateToVersion: function(index) {
      if (index >= 0 && index < this.refinementHistory.length) {
        this.currentHistoryIndex = index;
        return this.refinementHistory[index].json;
      }
      return null;
    },

/**
 * @function
 */
    getCurrentVersion: function() {
      if (this.currentHistoryIndex >= 0) {
        return this.refinementHistory[this.currentHistoryIndex];
      }
      return null;
    },

/**
 * @function
 */
    hasHistory: function() {
      return this.refinementHistory.length > 0;
    },

/**
 * @function
 */
    reset: function() {
      this.refinementHistory = [];
      this.currentHistoryIndex = -1;
    }
  };

  // Utility functions
/**
 * @function
 */
  function generateUUID() {
/**
 * @function
 */
    return 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, function(c) {
      const r = Math.random() * 16 | 0;
      const v = c === 'x' ? r : (r & 0x3 | 0x8);
      return v.toString(16);
    });
  }

/**
 * @function
 */
  function formatTime(timestamp) {
    const date = new Date(timestamp);
    return date.toLocaleTimeString(locale, { hour: '2-digit', minute: '2-digit' });
  }

/**
 * @function
 */
  function truncate(str, maxLength) {
    if (str.length <= maxLength) return str;
    return str.substring(0, maxLength) + '...';
  }

/**
 * @function
 */
  function requestRefinement(prompt, currentJson) {
    const formData = new FormData();
    formData.append("current_json", JSON.stringify(currentJson));
    formData.append("refinement_prompt", prompt);
    formData.append("_authenticator", CSRF_TOKEN);

    return fetch(ACTUAL_URL + "/@@refine-ai-form", {
      method: "POST",
      body: formData,
      credentials: 'same-origin'
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
          throw new Error(data.message || t("Refinement failed"));
        });
      }
      return response.json();
    });
  }

  // Refinement form submission handler
/**
 * @function
 */
  refinementForm.addEventListener("submit", function(e) {
    e.preventDefault();

    const prompt = refinementInput.value.trim();
    const useExisting = refineExistingCheckbox && refineExistingCheckbox.checked;
    if (!prompt) {
      showError(t("Please enter a description"));
      return;
    }

    const isInitial = !AppState.hasHistory();
    const currentVersion = AppState.getCurrentVersion();

    // Show loading state
    setRefinementLoadingState(true);
    hideError();

    if (isInitial && useExisting) {
      fetch(ACTUAL_URL + "/get-form-json", {
        credentials: 'same-origin'
      })
/**
 * @function
 */
      .then(response => response.json())
/**
 * @function
 */
      .then(existingJson => {
        if (!existingJson || Object.keys(existingJson).length === 0) {
          throw new Error(t("No existing form found to refine."));
        }

        AppState.addVersion(t("Existing form"), existingJson, "initial");
        generatedJson = existingJson;
        updateUIAfterGeneration();
        renderHistoryTimeline();

        return requestRefinement(prompt, existingJson);
      })
/**
 * @function
 */
      .then(data => {
        if (data.success) {
          AppState.addVersion(prompt, data.json, "refinement");
          generatedJson = data.json;

          renderHistoryTimeline();
          updateVersionIndicator();

          refinementInput.value = "";
          if (historyTimeline) {
            historyTimeline.scrollTop = historyTimeline.scrollHeight;
          }
        } else {
          throw new Error(data.message || t("Refinement failed"));
        }
      })
/**
 * @function
 */
      .catch(error => {
        console.error(t("Error refining existing form:"), error);
        showError(
          error.message || t("Failed to refine existing form. Please try again.")
        );
      })
/**
 * @function
 */
      .finally(() => {
        setRefinementLoadingState(false);
      });
      return;
    }

    if (isInitial) {
      // Initial generation
      const formData = new FormData();
      formData.append("prompt", prompt);
      formData.append("_authenticator", CSRF_TOKEN);

      fetch(ACTUAL_URL + "/@@generate-ai-form", {
        method: "POST",
        body: formData,
        credentials: 'same-origin'
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
            throw new Error(data.message || t("Generation failed"));
          });
        }
        return response.json();
      })
/**
 * @function
 */
      .then(data => {
        if (data.success) {
          // Add to history
          AppState.addVersion(prompt, data.json, "initial");
          generatedJson = data.json;

          // Update UI
          updateUIAfterGeneration();
          renderHistoryTimeline();

          // Clear input
          refinementInput.value = "";
        } else {
          throw new Error(data.message || t("Generation failed"));
        }
      })
/**
 * @function
 */
      .catch(error => {
        console.error(t("Error generating form:"), error);
        showError(error.message || t("Failed to generate form. Please try again."));
      })
/**
 * @function
 */
      .finally(() => {
        setRefinementLoadingState(false);
      });
    } else {
      // Refinement
      requestRefinement(prompt, currentVersion.json)
/**
 * @function
 */
      .then(data => {
        if (data.success) {
          // Add to history
          AppState.addVersion(prompt, data.json, "refinement");
          generatedJson = data.json;

          // Update UI
          renderHistoryTimeline();
          updateVersionIndicator();

          // Clear input
          refinementInput.value = "";

          // Scroll history to bottom
          if (historyTimeline) {
            historyTimeline.scrollTop = historyTimeline.scrollHeight;
          }
        } else {
          throw new Error(data.message || t("Refinement failed"));
        }
      })
/**
 * @function
 */
      .catch(error => {
        console.error(t("Error refining form:"), error);
        showError(
          error.message ||
            t(
              "Failed to refine form. Your current version is preserved. Please try again."
            )
        );
      })
/**
 * @function
 */
      .finally(() => {
        setRefinementLoadingState(false);
      });
    }
  });

  // Preview JSON button handler
/**
 * @function
 */
  previewJsonBtn.addEventListener("click", function() {
    const currentVersion = AppState.getCurrentVersion();
    if (!currentVersion) {
      showError(t("No form to preview"));
      return;
    }

    // Display JSON in modal
    jsonModalDisplay.textContent = JSON.stringify(currentVersion.json, null, 2);
    previewJsonModal.style.display = "block";
  });

  // Preview Form button handler
/**
 * @function
 */
  previewFormBtn.addEventListener("click", function() {
    const currentVersion = AppState.getCurrentVersion();
    if (!currentVersion) {
      showError(t("No form to preview"));
      return;
    }

    // Clear previous survey if exists
    if (survey) {
/**
 * @function
 */
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
      survey = new Survey.Model(currentVersion.json);
      survey.locale = locale;
      if (Survey && Survey.surveyLocalization) {
        Survey.surveyLocalization.currentLocale = locale;
      }

      // Disable completion (preview only)
      survey.showCompleteButton = false;
      survey.showPreviewBeforeComplete = "showAnsweredQuestions";

      // Render survey to the fresh container
      survey.render(renderTarget);

      // Show modal
      previewFormModal.style.display = "block";
    } catch (error) {
      console.error(t("Error rendering preview:"), error);
      showError(
        t("Failed to render preview: ${error}", { error: error.message })
      );
    }
  });

  // Save button handler
/**
 * @function
 */
  saveBtn.addEventListener("click", function() {
    const currentVersion = AppState.getCurrentVersion();
    if (!currentVersion) {
      showError(t("No form to save"));
      return;
    }

    // Check if user is saving an older version
    if (AppState.currentHistoryIndex < AppState.refinementHistory.length - 1) {
      const versionInfo = t("version ${current} of ${total}", {
        current: AppState.currentHistoryIndex + 1,
        total: AppState.refinementHistory.length
      });
      if (!confirm(
        t("You're saving ${version}. The latest version is not selected. Continue?", {
          version: versionInfo
        })
      )) {
        return;
      }
    }

    // Disable button during save
    saveBtn.disabled = true;
    const originalText = saveBtn.innerHTML;
    const versionInfo = t(" (Version ${version})", {
      version: AppState.currentHistoryIndex + 1
    });
    saveBtn.innerHTML =
      '<span class="spinner"></span> ' +
      t("Saving") +
      versionInfo +
      '...';

    // Prepare form data
    const formData = new FormData();
    formData.append("form_json", JSON.stringify(currentVersion.json));
    formData.append("_authenticator", CSRF_TOKEN);

    // Send AJAX request
    fetch(ACTUAL_URL + "/@@save-ai-form", {
      method: "POST",
      body: formData,
      credentials: 'same-origin'
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
          throw new Error(data.message || t("Save failed"));
        });
      }
      return response.json();
    })
/**
 * @function
 */
    .then(data => {
      if (data.success) {
        // Show success message
        alert(
          t(
            "Form saved successfully! You can now view it in the Visual Editor or Versions."
          )
        );
      } else {
        throw new Error(data.message || t("Save failed"));
      }
    })
/**
 * @function
 */
    .catch(error => {
      console.error(t("Error saving form:"), error);
      showError(
        t("Failed to save form: ${error}", {
          error: error.message || t("Unknown error")
        })
      );
    })
/**
 * @function
 */
    .finally(() => {
      saveBtn.disabled = false;
      saveBtn.innerHTML = originalText;
    });
  });

  // Start Over button handler
/**
 * @function
 */
  startOverBtn.addEventListener("click", function() {
    if (confirm(
      t(
        "Start over? This will clear your refinement history and return to the initial prompt."
      )
    )) {
      // Reset state
      AppState.reset();
      generatedJson = null;

      // Reset UI to initial state
      resetUIToInitial();

      // Clear displays
      if (historyTimeline) {
        historyTimeline.innerHTML = "";
      }
      refinementInput.value = "";
      hideError();
    }
  });

  // Modal close handlers
/**
 * @function
 */
  closeFormPreview.addEventListener("click", function() {
    previewFormModal.style.display = "none";
/**
 * @function
 */
    if (survey && typeof survey.destroy === 'function') {
        survey.destroy();
        survey = null;
    }
    surveyContainer.innerHTML = "";
  });

/**
 * @function
 */
  closeJsonPreview.addEventListener("click", function() {
    previewJsonModal.style.display = "none";
  });

/**
 * @function
 */
  window.addEventListener("click", function(event) {
    if (event.target === previewFormModal) {
      previewFormModal.style.display = "none";
/**
 * @function
 */
      if (survey && typeof survey.destroy === 'function') {
          survey.destroy();
          survey = null;
      }
      surveyContainer.innerHTML = "";
    }
    if (event.target === previewJsonModal) {
      previewJsonModal.style.display = "none";
    }
  });

  // Close modals with ESC key
/**
 * @function
 */
  document.addEventListener("keydown", function(event) {
    if (event.key === "Escape") {
      if (previewFormModal.style.display === "block") {
        previewFormModal.style.display = "none";
/**
 * @function
 */
        if (survey && typeof survey.destroy === 'function') {
          survey.destroy();
          survey = null;
        }
        surveyContainer.innerHTML = "";
      }
      if (previewJsonModal.style.display === "block") {
        previewJsonModal.style.display = "none";
      }
    }
  });

  // UI Helper Functions
/**
 * @function
 */
  function updateUIAfterGeneration() {
    // Change panel title
    if (formPanelTitle) {
      formPanelTitle.textContent = t("Refine Your Form");
    }

    // Change input label
    if (formInputLabel) {
      formInputLabel.textContent = t("What would you like to change?");
    }

    // Change help text
    if (formInputHelp) {
      formInputHelp.textContent = t(
        "Describe the changes you want to make to the current form."
      );
    }

    // Change button text
    if (refineBtnText) {
      refineBtnText.textContent = t("Refine Form");
    }
    if (refineBtnSpinnerText) {
      refineBtnSpinnerText.textContent = t("Refining...");
    }

    // Change placeholder
    if (refinementInput) {
      refinementInput.placeholder = t(
        "Example: Add rating scales for each question, Include a comments section at the end, Change the first question to a dropdown"
      );
    }

    // Show version indicator
    if (versionIndicator) {
      versionIndicator.style.display = "block";
      updateVersionIndicator();
    }

    // Show action buttons
    if (formActionButtons) {
      formActionButtons.style.display = "flex";
    }

    // Show start over button
    if (startOverBtn) {
      startOverBtn.style.display = "inline-block";
    }

    if (refineExistingCheckbox) {
      refineExistingCheckbox.disabled = true;
    }
  }

/**
 * @function
 */
  function resetUIToInitial() {
    // Reset panel title
    if (formPanelTitle) {
      formPanelTitle.textContent = t("Describe Your Form");
    }

    // Reset input label
    if (formInputLabel) {
      formInputLabel.textContent = t("Describe the form you want to create:");
    }

    // Reset help text
    if (formInputHelp) {
      formInputHelp.textContent = t(
        "Be specific about the types of questions, response formats, and any particular fields you need."
      );
    }

    // Reset button text
    if (refineBtnText) {
      refineBtnText.textContent = t("Generate Form");
    }
    if (refineBtnSpinnerText) {
      refineBtnSpinnerText.textContent = t("Generating...");
    }

    // Reset placeholder
    if (refinementInput) {
      refinementInput.placeholder = t(
        "Example: Create a customer satisfaction survey with questions about product quality, delivery experience, and overall satisfaction. Include rating scales and a comments section."
      );
    }

    // Hide version indicator
    if (versionIndicator) {
      versionIndicator.style.display = "none";
    }

    // Hide action buttons
    if (formActionButtons) {
      formActionButtons.style.display = "none";
    }

    // Hide start over button
    if (startOverBtn) {
      startOverBtn.style.display = "none";
    }

    if (refineExistingCheckbox) {
      refineExistingCheckbox.checked = false;
      refineExistingCheckbox.disabled = false;
    }
  }

/**
 * @function
 */
  function updateVersionIndicator() {
    if (currentVersionInfo && AppState.hasHistory()) {
      currentVersionInfo.textContent = t("Version ${current} of ${total}", {
        current: AppState.currentHistoryIndex + 1,
        total: AppState.refinementHistory.length
      });
    }
  }

/**
 * @function
 */
  function renderHistoryTimeline() {
    const timeline = document.getElementById("historyTimeline");
    if (!timeline) return;

    timeline.innerHTML = "";

/**
 * @function
 */
    AppState.refinementHistory.forEach((version, index) => {
      const item = document.createElement("div");
      item.className = "history-item";
      if (index === AppState.currentHistoryIndex) {
        item.classList.add("active");
      }

      const icon = version.type === "initial" ? "🎯" : "🔄";
      const title = version.type === "initial"
        ? t("Initial Generation")
        : t("Refinement ${index}", { index: index });

      item.innerHTML = `
        <div class="history-icon">${icon}</div>
        <div class="history-content">
          <div class="history-title">${title}</div>
          <div class="history-prompt">${truncate(version.prompt, 60)}</div>
          <div class="history-time">${formatTime(version.timestamp)}</div>
        </div>
      `;

/**
 * @function
 */
      item.addEventListener("click", () => navigateToVersion(index));
      timeline.appendChild(item);
    });
  }

/**
 * @function
 */
  function navigateToVersion(index) {
    const json = AppState.navigateToVersion(index);
    if (json) {
      generatedJson = json;
      updateVersionIndicator();
      renderHistoryTimeline();
    }
  }

/**
 * @function
 */
  function setRefinementLoadingState(loading) {
    if (!refineBtn) return;

    refineBtn.disabled = loading;
    const btnText = refineBtn.querySelector(".btn-text");
    const btnSpinner = refineBtn.querySelector(".btn-spinner");
    const historyItems = document.querySelectorAll(".history-item");

    if (btnText && btnSpinner) {
      if (loading) {
        btnText.style.display = "none";
        btnSpinner.style.display = "inline";

        // Disable history navigation
/**
 * @function
 */
        historyItems.forEach(item => {
          item.style.pointerEvents = "none";
          item.style.opacity = "0.6";
        });
      } else {
        btnText.style.display = "inline";
        btnSpinner.style.display = "none";

        // Re-enable history navigation
/**
 * @function
 */
        historyItems.forEach(item => {
          item.style.pointerEvents = "auto";
          item.style.opacity = "1";
        });
      }
    }
  }

  // Error handling functions
/**
 * @function
 */
  function showError(message) {
    if (errorMessage && errorContainer) {
      errorMessage.textContent = message;
      errorContainer.style.display = "block";
    }
  }

/**
 * @function
 */
  function hideError() {
    if (errorContainer) {
      errorContainer.style.display = "none";
    }
  }

});
