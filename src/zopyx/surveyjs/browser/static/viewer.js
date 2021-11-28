
Survey
    .StylesManager
    .applyTheme("modern");



$(document).ready(function() {

    var url = ACTUAL_URL + "/get-form-json";

    $.getJSON(url, function(result) {
        window.survey = new Survey.Model(result);

        survey
            .onComplete
            .add(function (sender) {
                console.log(sender.data);

                $.ajax({
                    url: ACTUAL_URL + "/save-poll",
                    type: "POST",
                    data: {
                        pollResult: sender.data
                    },
                    success: function (data) {
                        alert("saved");
                    },
                    error: function (xhr, ajaxOptions, thrownError) {
                        alert("not saved");
                    }
                });

            });

        survey.render("surveyElement");
    });
});
