

document.addEventListener("DOMContentLoaded", function() {

    const url = ACTUAL_URL + "/get-form-json";

    // Load the survey JSON configuration
    fetch(url)
        .then(response => response.json())
        .then(result => {
            console.log(result.data)
            // Create the survey from the loaded JSON
            const survey = new Survey.Model(result);

            // Set up the onComplete handler to save results
            survey
                .onComplete
                .add(function (sender) {
                    console.log(sender.data);

                    // Save the survey results
                    const formData = new FormData();
                    formData.append("pollResult", JSON.stringify(sender.data));

                    fetch(ACTUAL_URL + "/save-poll", {
                        method: "POST",
                        body: formData
                    })
                    .then(response => {
                        if (!response.ok) {
                            throw new Error("Save failed");
                        }
                    })
                    .catch(error => {
                        alert("not saved");
                        console.error(error);
                    });

                });

            // Render the survey
            survey.render("surveyElement");
        })
        .catch(error => {
            console.error("Error loading survey:", error);
        });
});
