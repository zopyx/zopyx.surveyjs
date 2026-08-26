SHELL := /bin/sh

ENTRY := validate.mjs
DIST := dist
JSON_FILES := survey.json data-valid.json data-invalid.json
BUN_CMD :=  bun
DENO_CMD := deno
DENO_VERSION := 2.9.5
DENO_FLAGS := --allow-read --allow-write --no-check --node-modules-dir=auto
DENO_TARGET_MAC := x86_64-apple-darwin
DENO_TARGET_LINUX := x86_64-unknown-linux-gnu
DENO_TARGET_MAC_ARM64 := aarch64-apple-darwin
DENO_TARGET_LINUX_ARM64 := aarch64-unknown-linux-gnu

.PHONY: all baseline mac linux deno-mac deno-linux deno-mac-arm64 deno-linux-arm64 assets clean bun-install \
	docker docker-linux docker-mac docker-mac-extract

all: install mac linux

deno: deno-mac deno-linux deno-mac-arm64 deno-linux-arm64
bun: linux mac


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

deno-install:
	@command -v $(DENO_CMD) >/dev/null || (echo "Deno $(DENO_VERSION) is required"; exit 1)
	@test "$$( $(DENO_CMD) --version | grep '^deno ' | cut -d' ' -f2 )" = "$(DENO_VERSION)" || (echo "Deno $(DENO_VERSION) is required"; $(DENO_CMD) --version; exit 1)
	$(DENO_CMD) install

deno-mac: deno-install assets
	mkdir -p $(DIST)
	$(DENO_CMD) compile $(DENO_FLAGS) --target=$(DENO_TARGET_MAC) --output $(DIST)/survey-validate-macos-deno $(ENTRY)

deno-linux: deno-install assets
	mkdir -p $(DIST)
	$(DENO_CMD) compile $(DENO_FLAGS) --target=$(DENO_TARGET_LINUX) --output $(DIST)/survey-validate-linux-deno $(ENTRY)

deno-mac-arm64: deno-install assets
	mkdir -p $(DIST)
	$(DENO_CMD) compile $(DENO_FLAGS) --target=$(DENO_TARGET_MAC_ARM64) --output $(DIST)/survey-validate-macos-arm64-deno $(ENTRY)

deno-linux-arm64: deno-install assets
	mkdir -p $(DIST)
	$(DENO_CMD) compile $(DENO_FLAGS) --target=$(DENO_TARGET_LINUX_ARM64) --output $(DIST)/survey-validate-linux-arm64-deno $(ENTRY)

clean:
	rm -rf $(DIST)

docker: docker-linux docker-mac

docker-linux:
	docker build -f Dockerfile.deno.linux -t survey-validate-deno:linux .

docker-mac:
	docker build -f Dockerfile.deno.macos -t survey-validate-deno:macos .

docker-mac-extract: docker-mac
	mkdir -p $(DIST)
	@cid=$$(docker create survey-validate-deno:macos /dist/survey-validate-macos-deno); \
	docker cp $$cid:/dist/survey-validate-macos-deno $(DIST)/survey-validate-macos-deno; \
	docker cp $$cid:/dist/survey.json $(DIST)/survey.json; \
	docker cp $$cid:/dist/data-valid.json $(DIST)/data-valid.json; \
	docker cp $$cid:/dist/data-invalid.json $(DIST)/data-invalid.json; \
	docker rm $$cid
