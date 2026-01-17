# SurveyJS Data Validation (Bun/Deno)

This folder contains a small CLI tool that validates SurveyJS form data using
SurveyJS' own `survey-core` validator. It can be executed directly with Bun or
compiled into native binaries via Bun or Deno.

## What the validator does

`validate.mjs` loads:
- a SurveyJS schema JSON (the form definition),
- a form response JSON (the answers),

then runs SurveyJS' validation against the data. The result is written to a
JSON file and the process exits with a status code that indicates success or
failure.

## Files

- `validate.mjs`      Main validator script.
- `survey.json`       Example schema JSON.
- `data-valid.json`   Example valid response JSON.
- `data-invalid.json` Example invalid response JSON.
- `Makefile`          Build/run helpers for Bun and Deno.
- `dist/`             Compiled binaries and copied JSON assets.

## Validator flow (validate.mjs)

1. Parse CLI arguments
   - Supported flags: `--schema-json`, `--form-json`, `--result-json`.
   - `--help` prints usage.
   - Missing values for known flags stop execution.
   - Unknown arguments stop execution.

2. Resolve input paths
   - If a path is absolute, it is used as-is.
   - If a path is relative, the script tries three locations in order:
     - `process.cwd()` (current working directory),
     - the directory of the executable (`process.execPath`),
     - the directory of `validate.mjs` itself.
   - This makes the compiled binaries usable when run from any directory.

3. Read JSON inputs
   - The script reads the schema JSON and response JSON as UTF-8.
   - Missing files cause an error with a list of attempted paths.

4. Create a SurveyJS Model and validate
   - `new Model(schema)` is created from `survey-core`.
   - `survey.data = formData` assigns the response values.
   - `survey.validate()` performs SurveyJS' built-in validation rules.

5. Collect field-level errors
   - The script iterates `survey.getAllQuestions()`.
   - For each question, it collects `question.errors` with the error text.
   - The output includes question `name`, `title`, and `messages`.

6. Write the result JSON
   - Output JSON structure:

     ```json
     {
       "valid": true,
       "errors": [
         {
           "name": "questionName",
           "title": "Question Title",
           "messages": ["Error message"]
         }
       ]
     }
     ```

7. Exit status
   - `0` when validation passes.
   - `1` when validation fails.

## CLI usage (direct)

Run with Bun (no compile):

```sh
bun validate.mjs --schema-json ./survey.json --form-json ./data-valid.json --result-json ./output.json
```

Run with Node (if your environment supports `survey-core` resolution):

```sh
node validate.mjs --schema-json ./survey.json --form-json ./data-valid.json --result-json ./output.json
```

## Bun usage

Install dependencies:

```sh
bun install
```

Compile binaries:

```sh
make mac
make linux
```

The binaries are placed in `dist/`:
- `survey-validate-macos`
- `survey-validate-linux`

## Deno usage

Install Deno (if not present):

```sh
deno --version
```

Compile binaries:

```sh
make deno-mac
make deno-linux
```

The binaries are placed in `dist/`:
- `survey-validate-macos-deno`
- `survey-validate-linux-deno`

Notes:
- The Deno compile uses these flags:
  - `--allow-read --allow-write` (file IO)
  - `--no-check` (skip type checking)
  - `--node-modules-dir=auto` (resolve `survey-core` from `node_modules`)

## Using the compiled binaries

The binaries accept the same flags as the JS script:

```sh
./dist/survey-validate-macos-deno \
  --schema-json ./survey.json \
  --form-json ./data-valid.json \
  --result-json ./output.json
```

When used from other directories, the tool will still locate the default JSON
files in the binary's directory if needed.

## Makefile targets

- `make bun`        Build both Bun binaries.
- `make mac`        Build Bun macOS binary.
- `make linux`      Build Bun Linux binary.
- `make deno`       Build both Deno binaries.
- `make deno-mac`   Build Deno macOS binary.
- `make deno-linux` Build Deno Linux binary.
- `make assets`     Copy sample JSON files into `dist/`.
- `make clean`      Remove `dist/`.

## Exit codes and integration

- Use the exit code to decide whether submissions pass validation.
- Read the output JSON for per-field error details.

