
var json = {
    "completedHtml": "<p style='font-size:24px;'>Thank you for completing the survey! (please wait for analytics to load ...)<p>",
    "pages": [
        {
            "name": "page_info",
            "elements": [
                {
                    "type": "radiogroup",
                    "name": "organization_type",
                    "title": "Which of the following best describes you or your organization?",
                    "hasOther": true,
                    "choices": [
                        {
                            "value": "ISV",
                            "text": "ISV (building commercial/shrink wrapped software)"
                        }, {
                            "value": "Consulting",
                            "text": "Software consulting firm (provide development services to other organizations)"
                        }, {
                            "value": "Custom",
                            "text": "Custom software development (as a freelancer/contractor)"
                        }, {
                            "value": "In-house",
                            "text": "In-house software development"
                        }, {
                            "value": "Hobbyist",
                            "text": "Hobbyist (develop apps for personal use)"
                        }
                    ],
                    "colCount": 2
                }, {
                    "type": "radiogroup",
                    "name": "developer_count",
                    "visibleIf": "{organization_type} != 'Hobbyist'",
                    "title": "How many software developers are in your organization?",
                    "choices": ["1", "2", "3-5", "6-10", "> 10"]
                }, {
                    "type": "radiogroup",
                    "name": "VerticalMarket",
                    "visibleIf": "{organization_type} != 'Hobbyist'",
                    "title": "What vertical market does your product serve?",
                    "hasOther": true,
                    "choices": [
                        "Automotive",
                        "Banking",
                        "Consumer",
                        "Education",
                        "Engineering",
                        "Energy",
                        "Fast-moving consumer goods",
                        "Financial",
                        "FinTech",
                        "Food and beverage",
                        "Government (federal, state, local)",
                        "Healthcare",
                        "Insurance",
                        "Legal",
                        "Manufacturing",
                        "Media",
                        "Online",
                        "Raw materials",
                        "Real estate",
                        "Religion",
                        "Retail",
                        "Jewelry",
                        "Technology",
                        "Telecommunications",
                        "Transportation (Travel)",
                        "Electronics",
                        "Not-for-profit"
                    ],
                    "colCount": 4
                }, {
                    "type": "radiogroup",
                    "name": "product_discovering",
                    "title": "How did you first discover the product? ",
                    "hasOther": true,
                    "choices": [
                        "Search engine",
                        "GitHub",
                        "Friend or colleague",
                        "Redit",
                        "Medium",
                        "Twitter",
                        "Facebook"
                    ],
                    "otherText": "Other",
                    "colCount": 3
                }
            ]
        }, {
            "name": "page_libraries_usage",
            "elements": [
                {
                    "type": "checkbox",
                    "name": "javascript_frameworks",
                    "title": "What JavaScript framework do you use?",
                    "hasOther": true,
                    "choices": [
                        "React",
                        "Angular",
                        "jQuery",
                        "Vue",
                        "Meteor",
                        "Ember",
                        "Backbone",
                        "Knockout",
                        "Aurelia",
                        "Polymer",
                        "Mithril"
                    ],
                    "choicesOrder": "asc",
                    "otherText": "Other (Please name it)",
                    "colCount": 3
                }, {
                    "type": "checkbox",
                    "name": "backend_language",
                    "title": "What Web Backend programming language do you use?",
                    "hasOther": true,
                    "choices": [
                        "Java",
                        "Python",
                        "Node.js",
                        "Go",
                        "Django",
                        "Asp.net",
                        "Ruby"
                    ],
                    "choicesOrder": "asc",
                    "otherText": "Other (Please name it)",
                    "colCount": 3
                }
            ]
        }, {
            "name": "page_product_usage",
            "elements": [
                {
                    "type": "radiogroup",
                    "name": "useproduct",
                    "title": "Do you currently use our libraries? ",
                    "isRequired": true,
                    "choices": ["Yes", "No"]
                }, {
                    "type": "checkbox",
                    "name": "uselibraries",
                    "visibleIf": "{useproduct} = \"Yes\"",
                    "title": "What libraries do you use?",
                    "isRequired": true,
                    "choices": ["Survey Library (Runner)", "Survey Creator (Designer)"]
                }, {
                    "type": "checkbox",
                    "name": "product_new",
                    "title": "We are going to release new libraries shortly. Please check a product(s), if you are interesting to use them",
                    "choices": ["Export to PDF (survey and its result)", "Analytics (Create Analytics based on JSON results)"]
                }, {
                    "type": "checkbox",
                    "name": "supported_devices",
                    "title": "What device types do you need to support?",
                    "isRequired": true,
                    "choices": [
                        "Desktop", {
                            "value": "Tablete",
                            "text": "Tablet"
                        },
                        "Mobile"
                    ]
                }, {
                    "type": "radiogroup",
                    "name": "native_mobile_support",
                    "visibleIf": "{supported_devices} contains \"Mobile\"",
                    "title": "How is important for you a native mobile support?",
                    "isRequired": true,
                    "choices": [
                        {
                            "value": "1",
                            "text": "I am happy with adaptive html rendering"
                        }, {
                            "value": "2",
                            "text": "Something important, but adaptive html rendering is fine"
                        }, {
                            "value": "3",
                            "text": "Very important"
                        }, {
                            "value": "4",
                            "text": "Can not use the library without it"
                        }
                    ]
                }, {
                    "type": "radiogroup",
                    "name": "native_framework",
                    "visibleIf": "{native_mobile_support} >= 3",
                    "title": "Please name the framework that you are using or going to use in your native mobile developlment",
                    "hasOther": true,
                    "choices": [
                        "react native", "nativescript", "ionic", "xamarin", "native iOS and Android apps"
                    ],
                    "otherText": "Other (Please name it)",
                    "colCount": 2
                }
            ]
        }, {
            "name": "page_alternative",
            "elements": [
                {
                    "type": "radiogroup",
                    "name": "product_alternative",
                    "title": "What would you use as an alternative if SurveyJS does not exist?",
                    "isRequired": true,
                    "hasOther": true,
                    "choices": [
                        "Use popular Survey cloud platforms", "Develop ourselves"
                    ],
                    "otherText": "Other (please name)"
                }, {
                    "type": "text",
                    "name": "survey_cloud_platform",
                    "visibleIf": "{product_alternative} = \"Use popular Survey cloud platforms\"",
                    "title": "What Survey cloud platform would be your choice?"
                }, {
                    "type": "radiogroup",
                    "name": "product_recommend",
                    "title": "Have you recommended the product to anyone?",
                    "choices": ["Yes", "No"]
                }
            ]
        }, {
            "name": "page_recommend",
            "elements": [
                {
                    "type": "rating",
                    "name": "nps_score",
                    "title": "How likely are you to recommend SurveyJS to a friend or colleague?",
                    "isRequired": true,
                    "rateMin": 0,
                    "rateMax": 10,
                    "minRateDescription": "Most unlikely",
                    "maxRateDescription": "Most likely"
                }, {
                    "type": "comment",
                    "name": "favorite_functionality",
                    "title": "What's your favorite functionality / add-on?"
                }, {
                    "type": "comment",
                    "name": "product_improvement",
                    "title": "How could our products be improved to better meet your needs?"
                }
            ]
        }
    ]
};

var survey = new Survey.Model(json);
var allQuestions = survey.getAllQuestions();

var panel1Node = document.getElementById("vizPanel1");
panel1Node.innerHTML = "";

$.get("https://surveyjs.io/api/MySurveys/getSurveyNPCResults/", function (data) {
    var surveyAnalyticsTabulator = new SurveyAnalyticsTabulator.Tabulator(survey, data.Data);

    surveyAnalyticsTabulator.render(panel1Node);
    $("#loadingIndicator1").hide();
});
