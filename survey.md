# SurveyJS Demo Survey Implementation

## Completed Tasks

### Added to the @@demo-content view:

1. **Created a SurveyJS-based sample survey** (`surveyjs-demo-survey`) with 6 questions demonstrating various question types:
   - **Page 1 - Work Environment:**
     - `radiogroup`: Department selection (6 choices)
     - `checkbox`: Benefits selection (multiple choice, max 3)
   
   - **Page 2 - Job Satisfaction:**
     - `rating`: Job satisfaction (1-5 scale with labels)
     - `rating`: Work-life balance (5-star rating)
     - `boolean`: Recommendation (Yes/No toggle)
   
   - **Page 3 - Feedback:**
     - `text`: Years of service (numeric input)
     - `comment`: Improvement suggestions (multi-line text, optional)

2. **Created demo result data**: 100 random survey responses with:
   - Randomized answers for all question types
   - Random submission dates within the last 90 days
   - Varied comment text from a pool of realistic feedback

3. **New Survey object**: The implementation creates a separate `surveyjs-demo-survey` object without touching the existing `multilingual-demo-survey`.

### Integration with Site Setup (scripts/init_plone.py)

The `@@demo-content` view is now automatically called as part of the site initialization process. This means:

- When running `bin/instance run scripts/init_plone.py`, the demo surveys are created automatically
- The call is wrapped in a try/except block to ensure the script continues even if demo creation fails
- A message is printed to indicate success or failure

## Implementation Details

- New method `_generate_surveyjs_demo_survey()`: Generates the SurveyJS JSON structure
- New method `_generate_demo_results()`: Generates random results using the storage backend
- Integration in `demo_content()`: Creates the new survey and populates it with demo data
- Site setup integration: Calls the view automatically during Plone site initialization
