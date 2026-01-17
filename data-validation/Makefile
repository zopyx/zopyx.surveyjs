SHELL := /bin/sh

ENTRY := validate.mjs
DIST := dist
JSON_FILES := survey.json data-valid.json data-invalid.json
BUN_CMD :=  bun

.PHONY: all baseline mac linux assets clean bun-install

all: install mac linux


install:
	bun install

assets:
	mkdir -p $(DIST)
	cp -f $(JSON_FILES) $(DIST)/

mac: bun-install assets
	mkdir -p $(DIST)
	$(BUN_CMD) build --compile --target=bun-darwin-x64 --outfile $(DIST)/survey-validate-macos $(ENTRY)

linux: bun-install assets
	mkdir -p $(DIST)
	$(BUN_CMD) build --compile --target=bun-linux-x64 --outfile $(DIST)/survey-validate-linux $(ENTRY)

clean:
	rm -rf $(DIST)
