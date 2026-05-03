#!/usr/bin/env node
// Frontend syntax gate: parse every .jsx in frontend/ with @babel/parser.
//
// Why this exists: app.jsx is shipped raw to the browser and compiled by
// Babel Standalone at runtime. There is no build step, so a syntax error
// gets discovered only when a human opens the page — server logs all
// look fine. PR for this gate landed after a botched merge left a JSX
// arrow function unterminated, hanging the SPA at "Loading…" with no
// server-side signal.
//
// Mirror Babel Standalone's parse posture: sourceType=script + jsx plugin.
// Exits non-zero on any parse failure.
import { readFileSync, readdirSync, statSync } from "node:fs";
import { join } from "node:path";
import { fileURLToPath } from "node:url";
import { parse } from "@babel/parser";

const ROOT = join(fileURLToPath(import.meta.url), "..", "..", "frontend");

function* walk(dir) {
  for (const name of readdirSync(dir)) {
    const p = join(dir, name);
    const s = statSync(p);
    if (s.isDirectory()) yield* walk(p);
    else if (name.endsWith(".jsx")) yield p;
  }
}

let failed = 0;
for (const file of walk(ROOT)) {
  const src = readFileSync(file, "utf8");
  try {
    parse(src, { sourceType: "script", plugins: ["jsx"] });
    console.log(`OK  ${file}`);
  } catch (e) {
    failed++;
    const loc = e.loc ? ` at ${e.loc.line}:${e.loc.column}` : "";
    console.error(`FAIL ${file}${loc}: ${e.message}`);
  }
}

if (failed > 0) {
  console.error(`\n${failed} file(s) failed to parse.`);
  process.exit(1);
}
