// SurveyJSON validator for Bun and Deno

const VERSION = "0.1.0";

const denoGlobal = (globalThis as { Deno?: any }).Deno;
const bunGlobal = (globalThis as { Bun?: any }).Bun;
const nodeProcess = (globalThis as { process?: { argv?: string[]; exit?: (code?: number) => void; stdin?: any } })
  .process;

const isDeno = typeof denoGlobal !== "undefined" && typeof denoGlobal?.version?.deno === "string";
const isBun = typeof bunGlobal !== "undefined";

function getArgs(): string[] {
  if (isDeno) return denoGlobal.args;
  if (nodeProcess?.argv) return nodeProcess.argv.slice(2);
  return [];
}

function usage(): string {
  return `SurveyJSON validator (${VERSION})\n\n` +
    `Usage:\n` +
    `  validate-survey.ts [options] <survey.json | ->\n\n` +
    `Options:\n` +
    `  --schema-version, -v   SurveyJS version (default: latest)\n` +
    `  --schema-url           Override schema URL\n` +
    `  --quiet, -q             Only print errors\n` +
    `  --help, -h              Show help\n`;
}

function parseArgs(argv: string[]) {
  let schemaVersion = "latest";
  let schemaUrl: string | null = null;
  let quiet = false;
  const positional: string[] = [];

  for (let i = 0; i < argv.length; i++) {
    const arg = argv[i];
    if (arg === "--schema-version" || arg === "-v") {
      schemaVersion = argv[++i] ?? "latest";
    } else if (arg === "--schema-url") {
      schemaUrl = argv[++i] ?? null;
    } else if (arg === "--quiet" || arg === "-q") {
      quiet = true;
    } else if (arg === "--help" || arg === "-h") {
      return { help: true } as const;
    } else if (arg === "-") {
      positional.push(arg);
    } else if (arg.startsWith("-")) {
      throw new Error(`Unknown option: ${arg}`);
    } else {
      positional.push(arg);
    }
  }

  return { help: false, schemaVersion, schemaUrl, quiet, positional } as const;
}

async function readStdin(): Promise<string> {
  if (isDeno) {
    const data = await new Response(denoGlobal.stdin.readable).arrayBuffer();
    return new TextDecoder().decode(data);
  }

  const chunks: Uint8Array[] = [];
  const stdin = nodeProcess?.stdin;
  if (!stdin) return "";

  return await new Promise((resolve, reject) => {
    stdin.on("data", (chunk: Uint8Array) => chunks.push(chunk));
    stdin.on("end", () => {
      const total = chunks.reduce((sum, chunk) => sum + chunk.length, 0);
      const merged = new Uint8Array(total);
      let offset = 0;
      for (const chunk of chunks) {
        merged.set(chunk, offset);
        offset += chunk.length;
      }
      resolve(new TextDecoder().decode(merged));
    });
    stdin.on("error", reject);
  });
}

async function readText(path: string): Promise<string> {
  if (path === "-") return await readStdin();

  if (isDeno) {
    return await denoGlobal.readTextFile(path);
  }

  if (isBun) {
    return await bunGlobal.file(path).text();
  }

  throw new Error("Unsupported runtime");
}

async function writeText(path: string, content: string): Promise<void> {
  if (isDeno) {
    await denoGlobal.writeTextFile(path, content);
    return;
  }
  if (isBun) {
    await bunGlobal.write(path, content);
    return;
  }
  throw new Error("Unsupported runtime");
}

import AjvImport from "ajv";

async function loadAjv(): Promise<any> {
  return (AjvImport as any).default ?? AjvImport;
}

function schemaUrlForVersion(version: string): string {
  if (!version || version === "latest") {
    return "https://unpkg.com/survey-core/surveyjs_definition.json";
  }
  return `https://unpkg.com/survey-core@${version}/surveyjs_definition.json`;
}

type AjvError = {
  instancePath?: string;
  message?: string;
  keyword?: string;
  params?: Record<string, unknown>;
  schemaPath?: string;
};

function pointerToPath(pointer: string | undefined): string {
  if (!pointer || pointer === "") return "<root>";
  const parts = pointer
    .split("/")
    .slice(1)
    .map((p) => p.replace(/~1/g, "/").replace(/~0/g, "~"));
  if (parts.length === 0) return "<root>";
  return parts
    .map((part) => {
      if (/^\d+$/.test(part)) return `[${part}]`;
      return `.${part}`;
    })
    .join("")
    .replace(/^\./, "");
}

function formatAjvErrors(errors: AjvError[]): string {
  return errors
    .map((err) => {
      const path = pointerToPath(err.instancePath);
      const message = err.message ?? "Invalid value";
      const keyword = err.keyword ? ` (${err.keyword})` : "";
      let extra = "";
      if (err.params && "missingProperty" in err.params) {
        extra = `: missing ${(err.params as { missingProperty: string }).missingProperty}`;
      }
      return `- ${path}: ${message}${keyword}${extra}`;
    })
    .join("\n");
}

async function main() {
  const argv = getArgs();
  let parsed;
  try {
    parsed = parseArgs(argv);
  } catch (err) {
    console.error(String(err));
    console.error(usage());
    return 2;
  }

  if (parsed.help) {
    console.log(usage());
    return 0;
  }

  const inputPath = parsed.positional[0];
  if (!inputPath) {
    console.error("Missing survey JSON file path.");
    console.error(usage());
    return 2;
  }

  const url = parsed.schemaUrl ?? schemaUrlForVersion(parsed.schemaVersion);

  const [surveyText, schemaText] = await Promise.all([
    readText(inputPath),
    fetch(url).then(async (res) => {
      if (!res.ok) throw new Error(`Failed to fetch schema (${res.status} ${res.statusText})`);
      return await res.text();
    }),
  ]);

  await writeText("surveyjs_form_schema.json", schemaText);

  let surveyJson: unknown;
  let schemaJson: unknown;

  try {
    surveyJson = JSON.parse(surveyText);
  } catch (err) {
    console.error(`Invalid JSON in survey file: ${String(err)}`);
    return 1;
  }

  try {
    schemaJson = JSON.parse(schemaText);
  } catch (err) {
    console.error(`Invalid JSON schema from ${url}: ${String(err)}`);
    return 1;
  }

  const Ajv = await loadAjv();
  const ajv = new (Ajv as any)({ allErrors: true, strict: false });
  const validate = ajv.compile(schemaJson as object);
  const valid = validate(surveyJson);

  if (valid) {
    if (!parsed.quiet) {
      console.log(`Survey is valid against schema: ${url}`);
    }
    return 0;
  }

  console.error(`Survey is invalid against schema: ${url}`);
  if (validate.errors?.length) {
    console.error(formatAjvErrors(validate.errors as Array<{ instancePath?: string; message?: string }>));
  }
  return 1;
}

const exitCode = await main();
if (isDeno) {
  denoGlobal.exit(exitCode);
} else if (nodeProcess?.exit) {
  nodeProcess.exit(exitCode);
}
