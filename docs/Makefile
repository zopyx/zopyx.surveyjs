SPHINXBUILD ?= sphinx-build
SOURCEDIR = .
BUILDDIR = _build

.PHONY: html pdf clean

html:
	uv venv  --clear
	uv pip install -r requirements.txt
	LANG=C.UTF-8 LC_ALL=C.UTF-8 $(SPHINXBUILD) -b html $(SOURCEDIR) html

pdf:
	uv venv 
	uv pip install -r requirements.txt
	LANG=C.UTF-8 LC_ALL=C.UTF-8 $(SPHINXBUILD) -b latexpdf $(SOURCEDIR) $(BUILDDIR)/latex

clean:
	rm -rf $(BUILDDIR)
