SPHINXBUILD ?= sphinx-build
SOURCEDIR = .
BUILDDIR = _build

.PHONY: html pdf clean

html:
	python -m pip install -r requirements.txt
	$(SPHINXBUILD) -b html $(SOURCEDIR) html

pdf:
	python -m pip install -r requirements.txt
	$(SPHINXBUILD) -b latexpdf $(SOURCEDIR) $(BUILDDIR)/latex

clean:
	rm -rf $(BUILDDIR)
