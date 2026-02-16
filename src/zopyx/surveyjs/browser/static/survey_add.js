(function () {
  const container = document.getElementById("survey-add-widget");
  if (!container || typeof Survey === "undefined") {
    return;
  }

  const schemaUrl = container.dataset.schemaUrl;
  const theme = container.dataset.theme || "index";
  const initialDataScript = document.getElementById("survey-add-initial-data");
  const hiddenForm = document.getElementById("survey-add-hidden-form");
  const submitButton = document.getElementById("survey-add-submit");
  let currentSurvey = null;

  let initialData = {};
  if (initialDataScript) {
    try {
      initialData = JSON.parse(initialDataScript.textContent || "{}");
    } catch (error) {
      console.warn("Survey add form: unable to parse initial data", error);
    }
  }

  function submitData(data) {
    if (!hiddenForm) {
      return;
    }
    const payload = data || {};
    const titleField = hiddenForm.querySelector('input[name="title"]');
    const descriptionField = hiddenForm.querySelector('input[name="description"]');
    if (titleField) {
      titleField.value = payload.title || "";
    }
    if (descriptionField) {
      descriptionField.value = payload.description || "";
    }
    const payloadField = hiddenForm.querySelector('input[name="payload"]');
    if (payloadField) {
      try {
        payloadField.value = JSON.stringify(payload);
      } catch (error) {
        console.warn("Survey add form: unable to serialize payload", error);
        payloadField.value = "";
      }
    }
    hiddenForm.submit();
  }

  function renderSurvey(schema) {
    if (Survey.StylesManager && typeof Survey.StylesManager.applyTheme === "function") {
      Survey.StylesManager.applyTheme(theme);
    }
    const survey = new Survey.Model(schema);
    currentSurvey = survey;
    if (initialData && Object.keys(initialData).length > 0) {
      survey.data = initialData;
    }
    survey.onComplete.add(function (sender) {
      submitData(sender.data || {});
    });
    survey.onCurrentPageChanging.add(function (sender, options) {
      if (options && options.allow === false) {
        options.allow = true;
      }
      if (options) {
        options.allowChanging = true;
        options.cancel = false;
      }
    });
    survey.onCurrentPageChanging.add(function (sender, options) {
      if (options) {
        options.allow = true;
        options.allowChanging = true;
        options.cancel = false;
      }
    });
    survey.onAfterRenderSurvey.add(function () {
      container.classList.add("is-ready");
    });
    survey.render(container);
  }

  function showError(message) {
    container.classList.remove("is-ready");
    container.innerHTML =
      '<div class="survey-add-error-message">' +
      (message || "We cannot load the form right now. Please reload the page.") +
      "</div>";
  }

  if (!schemaUrl) {
    showError("Missing form definition.");
    return;
  }

  fetch(schemaUrl, { cache: "no-store" })
    .then(function (response) {
      if (!response.ok) {
        throw new Error("Schema fetch failed");
      }
      return response.json();
    })
    .then(renderSurvey)
    .catch(function (error) {
      console.error("Survey add form failed", error);
      showError();
    });

  if (submitButton) {
    submitButton.addEventListener("click", function (event) {
      event.preventDefault();
      if (currentSurvey) {
        currentSurvey.completeLastPage();
      }
    });
  }
})();
