"""Invalidate survey access tokens that were exported to a CSV file.

The token-store view (``@@token-store`` on a survey) can export the unused
tokens of that survey as CSV. If such an export leaks — for example because it
was committed to a repository or attached to a ticket — every token in it has
to be invalidated, otherwise valid submissions can still be made with it.

Usage (dry run by default, nothing is written):

    bin/instance run scripts/invalidate_tokens.py tokens.csv
    bin/instance run scripts/invalidate_tokens.py tokens.csv --apply

The script walks every Plone site in the instance, every survey found through
the catalog and every token from the CSV's first column. With ``--apply`` the
matching, still unused tokens are invalidated with the reason
``leaked_export`` and the transaction is committed; without it, the script only
reports what it would do.
"""

from __future__ import annotations

import csv
import sys
from pathlib import Path

from AccessControl.SecurityManagement import newSecurityManager
from Products.CMFPlone.interfaces import IPloneSiteRoot
from zope.component.hooks import setSite
from zopyx.surveyjs.content.survey import ISurvey
from zopyx.surveyjs.interfaces import ITokenStore
import transaction


REASON = "leaked_export"


def read_tokens(path: Path) -> set[str]:
    """Return the tokens of the CSV's first column, ignoring its header."""
    tokens: set[str] = set()
    with open(path, newline="", encoding="utf-8-sig") as handle:
        for row in csv.reader(handle):
            if not row:
                continue
            value = row[0].strip()
            if not value or value.lower() == "token":
                continue
            tokens.add(value)
    return tokens


def iter_sites(app):
    """Yield the Plone sites of the instance."""
    for obj in app.objectValues():
        if IPloneSiteRoot.providedBy(obj):
            yield obj


def iter_surveys(site) -> list:
    """Return all Survey objects of a site."""
    catalog = site.portal_catalog
    search = getattr(catalog, "unrestrictedSearchResults", catalog.searchResults)
    surveys = []
    for brain in search(object_provides=ISurvey.__identifier__):
        try:
            obj = brain.getObject()
        except Exception:  # pragma: no cover - broken catalog entry
            continue
        if ISurvey.providedBy(obj):
            surveys.append(obj)
    return surveys


def main(app, argv: list[str]) -> int:
    # `bin/instance run` keeps the whole command line in ``sys.argv``, so the
    # CSV file is identified by its suffix instead of by position.
    positional = [value for value in argv if value.lower().endswith(".csv")]
    apply_changes = "--apply" in argv
    if not positional:
        print(__doc__)
        return 2

    csv_path = Path(positional[0]).expanduser()
    if not csv_path.is_file():
        print(f"ERROR: {csv_path} does not exist")
        return 2

    tokens = read_tokens(csv_path)
    print(f"tokens in {csv_path}: {len(tokens)}")
    if not tokens:
        print("nothing to do")
        return 0

    acl = app.acl_users
    admin = acl.getUserById("admin") or acl.getUserById("admin2")
    if admin is not None:
        newSecurityManager(None, admin.__of__(acl))

    surveys_scanned = 0
    matches = 0
    already_used = 0
    affected = 0
    for site in iter_sites(app):
        setSite(site)
        try:
            for survey in iter_surveys(site):
                surveys_scanned += 1
                store = ITokenStore(survey)
                for token in sorted(tokens):
                    info = store.get_token_info(token)
                    if not info:
                        continue
                    matches += 1
                    if info.get("used"):
                        already_used += 1
                        continue
                    if apply_changes:
                        if store.invalidate(token, REASON):
                            affected += 1
                    else:
                        affected += 1
                    print(
                        f"  {survey.absolute_url()}: token {token[:8]}… "
                        f"{'invalidated' if apply_changes else 'to invalidate'}"
                    )
        finally:
            setSite()

    print(f"surveys scanned:            {surveys_scanned}")
    print(f"tokens found in any survey: {matches}")
    print(f"already used (skipped):     {already_used}")
    print(f"{'invalidated' if apply_changes else 'to invalidate (dry run)'}: {affected}")

    if apply_changes:
        transaction.commit()
        print("transaction committed")
    else:
        print("no changes written — re-run with --apply to invalidate")
    return 0


if __name__ == "__main__":
    # `app` is injected by `bin/instance run`.
    sys.exit(main(app, sys.argv[1:]))  # noqa: F821
