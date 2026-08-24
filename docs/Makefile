# Build the docs in an ephemeral uv environment: no persistent .venv is
# created, and the repo-root workspace (buildout venv) is never touched.
SPHINXBUILD ?= sphinx-build
SOURCEDIR = .
BUILDDIR = _build

.PHONY: html pdf docs clean

html:
	LANG=C.UTF-8 LC_ALL=C.UTF-8 uv run --no-project --with-requirements requirements.txt $(SPHINXBUILD) -W -b html $(SOURCEDIR) html

pdf:
	LANG=C.UTF-8 LC_ALL=C.UTF-8 uv run --no-project --with-requirements requirements.txt $(SPHINXBUILD) -b latexpdf $(SOURCEDIR) $(BUILDDIR)/latex

docs: html

clean:
	rm -rf $(BUILDDIR) html
