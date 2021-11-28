
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
                document
                    .querySelector('#surveyResult')
                    .textContent = "Result JSON:\n" + JSON.stringify(sender.data, null, 3);
            });

        survey.render("surveyElement");
    });
});
