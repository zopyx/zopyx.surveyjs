SPHINXBUILD ?= .venv/bin/sphinx-build
SOURCEDIR = .
BUILDDIR = _build

.PHONY: html pdf clean

html:
	uv venv -p312 --clear
	uv pip install sphinx sphinx-rtd-theme pydata-sphinx-theme
	$(SPHINXBUILD) -b html $(SOURCEDIR) html

pdf:
	uv venv -p312 --clear
	uv pip install sphinx sphinx-rtd-theme pydata-sphinx-theme
	$(SPHINXBUILD) -b latexpdf $(SOURCEDIR) $(BUILDDIR)/latex

clean:
	rm -rf $(BUILDDIR)
