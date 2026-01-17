SPHINXBUILD ?= sphinx-build
SOURCEDIR = .
BUILDDIR = _build

.PHONY: html pdf clean

html:
	uv pip install sphinx sphinx-rtd-theme
	$(SPHINXBUILD) -b html $(SOURCEDIR) $(BUILDDIR)/html

pdf:
	uv pip install sphinx sphinx-rtd-theme
	$(SPHINXBUILD) -b latexpdf $(SOURCEDIR) $(BUILDDIR)/latex

clean:
	rm -rf $(BUILDDIR)
