# -*- coding: utf-8 -*-
"""Installer for the zopyx.surveyjs package."""

from setuptools import find_packages
from setuptools import setup


long_description = "\n\n".join(
    [
        open("README.md").read(),
        open("CONTRIBUTORS.rst").read(),
        open("CHANGES.rst").read(),
    ]
)


setup(
    name="zopyx.surveyjs",
    version="1.0a7",
    description="SurveyJS integration with Plone",
    long_description=long_description,
    long_description_content_type="text/markdown",
    # Get more from https://pypi.org/classifiers/
    classifiers=[
        "Environment :: Web Environment",
        "Framework :: Plone",
        "Framework :: Plone :: Addon",
        # Only Plone 6.2 is covered by the CI test suite; do not advertise
        # versions that no automated run exercises.
        "Framework :: Plone :: 6.2",
        "Programming Language :: Python",
        "Programming Language :: Python :: 3.12",
        "Programming Language :: Python :: 3.13",
        "Programming Language :: Python :: 3.14",
        "Operating System :: OS Independent",
        "License :: OSI Approved :: GNU General Public License v2 or later (GPLv2+)",
    ],
    keywords="Python Plone CMS",
    author="Andreas Jung",
    author_email="info@zopyx.com",
    url="https://github.com/zopyx/zopyx.surveyjs",
    project_urls={
        "PyPI": "https://pypi.python.org/pypi/zopyx.surveyjs",
        "Source": "https://github.com/zopyx/zopyx.surveyjs",
        "Tracker": "https://github.com/zopyx/zopyx.surveyjs/issues",
        "Documentation": "https://docs.privacyforms.studio",
        "Changelog": (
            "https://github.com/zopyx/zopyx.surveyjs/blob/master/CHANGES.rst"
        ),
    },
    license="GPL version 2 or later",
    packages=find_packages("src", exclude=["ez_setup"]),
    namespace_packages=["zopyx"],
    package_dir={"": "src"},
    include_package_data=True,
    zip_safe=False,
    python_requires=">=3.12",
    install_requires=[
        "setuptools",
        # -*- Extra requirements: -*-
        "z3c.jbot",
        "orjson",
        "plone.api>=1.8.4",
        "plone.restapi ",
        "plone.app.dexterity",
        "httpx",
        "llm",
        "python-docx",
        "markdown2",
        "weasyprint",
        "openpyxl",
        "llm-ollama",
        "llm-anthropic",
        "llm-deepseek",
        "zopyx.llm-moonshot",
        "sqlmodel",
        "diskcache",
        "PyJWT>=2.8.0",
        "pypdf",
        "langcodes[data]",
        "zopyx.plone.persistentlogger",
        "cssselect",
        "cssselect2",
        # Hard runtime dependency of the browser layer (browser/ai.py and
        # browser/services/ai.py): without it the AI generator and the model
        # vocabulary cannot work. Published on PyPI; the buildout in this
        # repository overrides it with the sibling develop egg.
        "privacyforms.ai>=0.1.8",
        # Documented dependency of the fillable-PDF workflow. The add-on
        # ships an inline pypdf fallback for field detection, but the
        # supported path is this package.
        "privacyforms.pdf>=0.2.0",
    ],
    extras_require={
        "pdf": [
            # Filling and downloading a PDF template (@@fillable-pdf-fill)
            # needs PyMuPDF. It stays an extra instead of a hard requirement
            # because PyMuPDF is dual-licensed (AGPL-3.0 or Artifex
            # commercial) and must not be imposed on every deployment.
            "PyMuPDF",
        ],
        "test": [
            "plone.app.testing",
            # Plone KGS does not use this version, because it would break
            # Remove if your package shall be part of coredev.
            # plone_coredev tests as of 2016-04-01.
            "plone.testing>=5.0.0",
            "plone.app.contenttypes",
            "plone.app.robotframework[debug]",
#            "collective.z3cform.jsonwidget",
            "orjson",
            "diskcache",
            "polib",
            # KV facade portability suite (test-only engines)
            "duckdb",
            "duckdb-engine",
            "testcontainers",
            "psycopg2-binary",
            "pymysql",
        ],
    },
    entry_points="""
    [z3c.autoinclude.plugin]
    target = plone
    [console_scripts]
    update_locale = zopyx.surveyjs.locales.update:update_locale
    """,
)
