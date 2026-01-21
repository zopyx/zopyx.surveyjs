# SurveyJS schema validation (Bun + Deno)

Validates a SurveyJSON file against the SurveyJS JSON schema, using either the latest schema or a specific SurveyJS version.

## Usage

### Deno

```bash
deno run --allow-read --allow-net validate-survey.ts --schema-version latest ./survey.json
```

### Bun

```bash
bun install
bun validate-survey.ts --schema-version latest ./survey.json
```

### Use a specific SurveyJS version

```bash
# example version
bun validate-survey.ts --schema-version 2.3.8 ./survey.json
```

### Read from stdin

```bash
cat ./survey.json | deno run --allow-read --allow-net validate-survey.ts -
```

## Examples

```bash
# Valid example
bun validate-survey.ts --schema-version latest examples/valid-survey.json

# Invalid example
bun validate-survey.ts --schema-version latest examples/invalid-survey.json
```

## Tests

```bash
# Bun
bun install
bun test

# Deno
deno test --allow-run --allow-read --allow-net tests/validate-survey.test.ts
```

## How schema versions map

SurveyJS publishes the JSON schema in `survey-core`:

- Latest: `https://unpkg.com/survey-core/surveyjs_definition.json`
- Specific version: `https://unpkg.com/survey-core@VERSION/surveyjs_definition.json`

## Build native executables

### Deno (Linux/macOS)

```bash
# Linux x64
deno compile --allow-read --allow-net --target x86_64-unknown-linux-gnu -o survey-validate validate-survey.ts

# macOS x64
deno compile --allow-read --allow-net --target x86_64-apple-darwin -o survey-validate validate-survey.ts

# macOS Apple Silicon
deno compile --allow-read --allow-net --target aarch64-apple-darwin -o survey-validate validate-survey.ts
```

### Bun (Linux/macOS)

```bash
# Linux x64
bun build --compile --target=bun-linux-x64 validate-survey.ts --outfile survey-validate

# macOS x64
bun build --compile --target=bun-darwin-x64 validate-survey.ts --outfile survey-validate

# macOS Apple Silicon
bun build --compile --target=bun-darwin-arm64 validate-survey.ts --outfile survey-validate
```
