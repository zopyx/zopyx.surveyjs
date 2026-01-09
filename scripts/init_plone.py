"""Initialize a demo Plone site with zopyx.surveyjs installed."""
from plone.app.theming.browser.controlpanel import ThemingControlpanel
from AccessControl.SecurityManagement import newSecurityManager
from Products.CMFPlone.factory import addPloneSite
from Testing.makerequest import makerequest
from plone import api
import transaction
from zope.component.hooks import setSite


SITE_ID = "demo"
ADMIN = "admin"

class MyThemingControlpanel(ThemingControlpanel):
    """
    A subclass of the standard ThemingControlpanel to override authorization.
    This allows the script to programmatically change theme settings without
    requiring the usual browser-based authentication and permissions.
    """

    def authorize(self):
        # Always return True to allow theme modifications.
        return True



acl = app.acl_users
admin_user = acl.getUser(ADMIN)
newSecurityManager(None, admin_user.__of__(acl))

if SITE_ID in app.objectIds():
    app.manage_delObjects([SITE_ID])
    transaction.commit()

addPloneSite(
    app,
    SITE_ID,
    distribution="classic",
    extension_ids=["plone.app.contenttypes:default"],
)
site = makerequest(app[SITE_ID])

print("Enabling Barceloneta theme...")
site.REQUEST.form["form.button.Enable"] = "DONE"
site.REQUEST.form["themeName"] = "barceloneta"
view = MyThemingControlpanel(site, site.REQUEST)
view.update()


setSite(site)

api.addon.install("zopyx.surveyjs")

transaction.commit()
