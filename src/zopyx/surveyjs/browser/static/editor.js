

document.addEventListener("DOMContentLoaded", function() {

    const creatorOptions = {
        autoSaveEnabled: true,
        collapseOnDrag: true
    };

    const creator = new SurveyCreator.SurveyCreator(creatorOptions);
    creator.render("surveyCreator");
    creator.showToolbox = "right";
    creator.showState = true;
    creator.showPropertyGrid = "right";
    creator.rightContainerActiveItem("toolbox");
    creator.autoSaveEnabled = false;



    var url = ACTUAL_URL + "/get-form-json";

    $.getJSON(url, function(result) {
        creator.JSON = result;
    });


    creator.saveSurveyFunc = function (saveNo, callback) {
    $.ajax({
        url: ACTUAL_URL + "/save-form-json",
        type: "POST",
        data: {
            surveyId: "42",
            surveyText : creator.text
        },
        success: function (data) {
            callback(saveNo, data.isSuccess);
        },
        error: function (xhr, ajaxOptions, thrownError) {
            callback(saveNo, false);
            alert(thrownError);
        }
      });
    }

});

