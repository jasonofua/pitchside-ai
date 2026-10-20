// Generate lib/contracts.ts from the JSON Schemas in /schemas, so the browser and the
// Python services share one contract. Run with `pnpm gen:types`; CI checks for drift.
import { readFile, writeFile } from "node:fs/promises";
import { compile } from "json-schema-to-typescript";

const SCHEMAS = ["event", "tracking", "overlay", "world", "match", "trigger", "stats", "profile", "agents"];
const root = new URL("../../schemas/", import.meta.url);
let out = "// Generated from /schemas by web/scripts/gen-types.mjs. Do not edit.\n/* eslint-disable */\n";
const seen = new Set();
for (const name of SCHEMAS) {
  const schema = JSON.parse(await readFile(new URL(`${name}.schema.json`, root), "utf8"));
  let ts = await compile(schema, schema.title, {
    bannerComment: "",
    additionalProperties: false,
    unreachableDefinitions: true,
    strictIndexSignatures: true,
    format: true,
  });
  // Several schemas repeat small shared definitions (Lang, StatItem, MatchStatus); keep the first.
  ts = ts
    .split(/\n(?=export )/)
    .filter((block) => {
      const m = block.match(/^export (?:interface|type) (\w+)/m);
      if (!m) return true;
      if (seen.has(m[1])) return false;
      seen.add(m[1]);
      return true;
    })
    .join("\n");
  out += `\n// ---- ${name}.schema.json\n${ts}`;
}
await writeFile(new URL("../lib/contracts.ts", import.meta.url), out);
console.log("wrote lib/contracts.ts");
