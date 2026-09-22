# -*- coding: utf-8 -*-
from plone.app.contenttypes.testing import PLONE_APP_CONTENTTYPES_FIXTURE
from plone.app.testing import (
    applyProfile,
    FunctionalTesting,
    IntegrationTesting,
    PloneSandboxLayer,
)

import zopyx.surveyjs


class ZopyxSurveyjsLayer(PloneSandboxLayer):
    defaultBases = (PLONE_APP_CONTENTTYPES_FIXTURE,)

    def setUpZope(self, app, configurationContext):
        # Load any other ZCML that is required for your tests.
        # The z3c.autoinclude feature is disabled in the Plone fixture base
        # layer.
        import plone.restapi

        self.loadZCML(package=plone.restapi)
        self.loadZCML(package=zopyx.surveyjs)

    def setUpPloneSite(self, portal):
        applyProfile(portal, "zopyx.surveyjs:default")


ZOPYX_SURVEYJS_FIXTURE = ZopyxSurveyjsLayer()


class ZopyxSurveyjsDemoLayer(PloneSandboxLayer):
    """Test layer of the regular add-on plus the optional demo profile."""

    defaultBases = (ZOPYX_SURVEYJS_FIXTURE,)

    def setUpPloneSite(self, portal):
        applyProfile(portal, "zopyx.surveyjs:demo")


ZOPYX_SURVEYJS_DEMO_FIXTURE = ZopyxSurveyjsDemoLayer()


ZOPYX_SURVEYJS_DEMO_INTEGRATION_TESTING = IntegrationTesting(
    bases=(ZOPYX_SURVEYJS_DEMO_FIXTURE,),
    name="ZopyxSurveyjsDemoLayer:IntegrationTesting",
)


ZOPYX_SURVEYJS_INTEGRATION_TESTING = IntegrationTesting(
    bases=(ZOPYX_SURVEYJS_FIXTURE,),
    name="ZopyxSurveyjsLayer:IntegrationTesting",
)


ZOPYX_SURVEYJS_FUNCTIONAL_TESTING = FunctionalTesting(
    bases=(ZOPYX_SURVEYJS_FIXTURE,),
    name="ZopyxSurveyjsLayer:FunctionalTesting",
)
