document.addEventListener("DOMContentLoaded", function () {
  const url = ACTUAL_URL + "/get-form-json";

  // Load the survey JSON configuration
  fetch(url, {
    credentials: 'same-origin'
  })
    .then((response) => response.json())
    .then((result) => {
      // Create the survey from the loaded JSON
        console.log(result)
      const survey = new Survey.Model(result);
        survey.applyTheme(SurveyTheme.LayeredDarkPanelless);

      // Set up the onComplete handler to save results
      survey.onComplete.add(function (sender) {

        // Save the survey results
        const formData = new FormData();
        formData.append("pollResult", JSON.stringify(sender.data));
        formData.append("_authenticator", CSRF_TOKEN);

        fetch(ACTUAL_URL + "/save-poll", {
          method: "POST",
          body: formData,
          credentials: 'same-origin'
        })
          .then((response) => {
            if (!response.ok) {
              throw new Error("Save failed");
            }
          })
          .catch((error) => {
            alert("not saved");
            console.error(error);
          });
      });

      // Render the survey
      survey.render(document.getElementById("surveyContainer"));
    })
    .catch((error) => {
      console.error("Error loading survey:", error);
    });
});
