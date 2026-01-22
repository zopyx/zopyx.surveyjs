SPHINXBUILD ?= sphinx-build
SOURCEDIR = .
BUILDDIR = _build

.PHONY: html pdf clean

html:
	uv pip install -r requirements.txt
	uv venv 
	$(SPHINXBUILD) -b html $(SOURCEDIR) html

pdf:
	uv pip install -r requirements.txt
	uv venv 
	$(SPHINXBUILD) -b latexpdf $(SOURCEDIR) $(BUILDDIR)/latex

clean:
	rm -rf $(BUILDDIR)
