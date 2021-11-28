$(document).ready(function() {

    SurveyCreator
        .StylesManager
        .applyTheme("orange");

    var creatorOptions = {
        showLogicTab: true
    };
    var creator = new SurveyCreator.SurveyCreator("creatorElement", creatorOptions);
    creator.showToolbox = "right";
    creator.showPropertyGrid = "right";
    creator.rightContainerActiveItem("toolbox");

    var url = ACTUAL_URL + "/get-form-json";

    $.getJSON(url, function(result) {
        creator.JSON = result;
    });

});
