# ============================================================================
# DEXTERITY ROBOT TESTS
# ============================================================================
#
# Run this robot test stand-alone:
#
#  $ bin/test -s zopyx.surveyjs -t test_survey.robot --all
#
# Run this robot test with robot server (which is faster):
#
# 1) Start robot server:
#
# $ bin/robot-server --reload-path src zopyx.surveyjs.testing.ZOPYX_SURVEYJS_ACCEPTANCE_TESTING
#
# 2) Run robot tests:
#
# $ bin/robot /src/zopyx/surveyjs/tests/robot/test_survey.robot
#
# See the http://docs.plone.org for further details (search for robot
# framework).
#
# ============================================================================

*** Settings *****************************************************************

Resource  plone/app/robotframework/selenium.robot
Resource  plone/app/robotframework/keywords.robot

Library  Remote  ${PLONE_URL}/RobotRemote

Test Setup  Open test browser
Test Teardown  Close all browsers


*** Test Cases ***************************************************************

Scenario: As a site administrator I can add a Survey
  Given a logged-in site administrator
    and an add Survey form
   When I type 'My Survey' into the title field
    and I submit the form
   Then a Survey with the title 'My Survey' has been created

Scenario: As a site administrator I can view a Survey
  Given a logged-in site administrator
    and a Survey 'My Survey'
   When I go to the Survey view
   Then I can see the Survey title 'My Survey'


*** Keywords *****************************************************************

# --- Given ------------------------------------------------------------------

a logged-in site administrator
  Enable autologin as  Site Administrator

an add Survey form
  Go To  ${PLONE_URL}/++add++Survey

a Survey 'My Survey'
  Create content  type=Survey  id=my-survey  title=My Survey

# --- WHEN -------------------------------------------------------------------

I type '${title}' into the title field
  Input Text  name=form.widgets.IBasic.title  ${title}

I submit the form
  Click Button  Save

I go to the Survey view
  Go To  ${PLONE_URL}/my-survey
  Wait until page contains  Site Map


# --- THEN -------------------------------------------------------------------

a Survey with the title '${title}' has been created
  Wait until page contains  Site Map
  Page should contain  ${title}
  Page should contain  Item created

I can see the Survey title '${title}'
  Wait until page contains  Site Map
  Page should contain  ${title}
