import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import surveyCore from "survey-core";

const { Model } = surveyCore;

const executionDirectory = path.dirname(process.execPath);
const moduleDirectory = path.dirname(fileURLToPath(import.meta.url));

function fail(message) {
  console.error(message);
  process.exit(1);
}

function resolveInputPath(inputPath) {
  if (path.isAbsolute(inputPath)) {
    return inputPath;
  }

  const candidates = [
    path.resolve(process.cwd(), inputPath),
    path.resolve(executionDirectory, inputPath),
    path.resolve(moduleDirectory, inputPath),
  ];

  return candidates.find((candidate) => fs.existsSync(candidate)) ?? candidates[0];
}

function readJsonFile(inputPath) {
  const resolvedPath = resolveInputPath(inputPath);
  if (!fs.existsSync(resolvedPath)) {
    const realExecDir = fs.realpathSync.native(executionDirectory);
    fail(
      [
        `Missing file: ${inputPath}`,
        `Tried path: ${resolvedPath}`,
        `Exec dir: ${realExecDir}`,
      ].join("\n")
    );
  }

  return JSON.parse(fs.readFileSync(resolvedPath, "utf8"));
}

function resolveOutputPath(outputPath) {
  return path.isAbsolute(outputPath)
    ? outputPath
    : path.resolve(process.cwd(), outputPath);
}

function parseArgs(argv) {
  const options = {
    schemaJson: "./survey.json",
    formJson: "./data-valid.json",
    resultJson: "output.json",
  };

  const requireValue = (flag, value) => {
    if (!value || value.startsWith("--")) {
      fail(`Missing value for ${flag}`);
    }
    return value;
  };

  for (let i = 0; i < argv.length; i += 1) {
    const arg = argv[i];

    if (arg === "--schema-json") {
      options.schemaJson = requireValue(arg, argv[i + 1]);
      i += 1;
    } else if (arg === "--form-json") {
      options.formJson = requireValue(arg, argv[i + 1]);
      i += 1;
    } else if (arg === "--result-json") {
      options.resultJson = requireValue(arg, argv[i + 1]);
      i += 1;
    } else if (arg === "--help" || arg === "-h") {
      console.log(
        [
          "Usage: validate.mjs [options]",
          "",
          "Options:",
          "  --schema-json <path>   Path to the survey schema JSON file",
          "  --form-json <path>     Path to the form response JSON file",
          "  --result-json <path>   Path to write validation results (default: output.json)",
        ].join("\n")
      );
      process.exit(0);
    } else {
      fail(`Unknown argument: ${arg}`);
    }
  }

  if (!options.schemaJson) {
    fail("Missing --schema-json value.");
  }
  if (!options.formJson) {
    fail("Missing --form-json value.");
  }
  if (!options.resultJson) {
    fail("Missing --result-json value.");
  }

  return options;
}

function collectErrors(survey) {
  const errors = [];

  for (const question of survey.getAllQuestions()) {
    if (question.errors?.length) {
      errors.push({
        name: question.name,
        title: question.title,
        messages: question.errors.map((error) => error.text),
      });
    }
  }

  return errors;
}

function runValidation() {
  const options = parseArgs(process.argv.slice(2));
  const surveyJson = readJsonFile(options.schemaJson);
  const formData = readJsonFile(options.formJson);

  const survey = new Model(surveyJson);
  survey.data = formData;

  const isValid = survey.validate();
  const errors = collectErrors(survey);

  const result = {
    valid: isValid,
    errors,
  };

  const outputPath = resolveOutputPath(options.resultJson);
  fs.writeFileSync(outputPath, JSON.stringify(result, null, 2) + "\n", "utf8");

  if (!isValid) {
    console.error("Validation failed.");
  }

  process.exitCode = isValid ? 0 : 1;
}

try {
  runValidation();
} catch (error) {
  const message = error instanceof Error ? error.message : String(error);
  fail(message);
}
