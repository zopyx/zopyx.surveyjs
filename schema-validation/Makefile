SHELL := /bin/sh

.DEFAULT_GOAL := help

help:
	@echo "Targets:"
	@echo "  install        Install bun dependencies"
	@echo "  example-bun    Validate examples/valid-survey.json with bun"
	@echo "  example-deno   Validate examples/valid-survey.json with deno"
	@echo "  test-bun       Run bun tests"
	@echo "  test-deno      Run deno tests (requires --allow-run/--allow-read/--allow-net)"
	@echo "  compile-bun    Build native binary with bun"
	@echo "  compile-deno   Build native binary with deno (linux target)"

install:
	bun install

example-bun:
	bun validate-survey.ts --schema-version latest examples/valid-survey.json

example-deno:
	deno run --allow-read --allow-net validate-survey.ts --schema-version latest examples/valid-survey.json

# deno test requires permissions to spawn deno for the CLI under test

test-bun: install
	bun test

test-deno:
	deno test --allow-run --allow-read --allow-net tests/validate-survey.test.ts

compile-bun:
	bun build --compile --target=bun-linux-x64 validate-survey.ts --outfile survey-validate

compile-deno:
	deno compile --allow-read --allow-net --target x86_64-unknown-linux-gnu -o survey-validate validate-survey.ts
