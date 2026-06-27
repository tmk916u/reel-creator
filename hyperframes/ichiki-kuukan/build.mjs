#!/usr/bin/env node
// brief.json の値を template.html に流し込んで index.html を生成する。
// 使い方: node build.mjs  (npm run build)
import { readFileSync, writeFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";

const here = dirname(fileURLToPath(import.meta.url));
const brief = JSON.parse(readFileSync(join(here, "brief.json"), "utf8"));
let html = readFileSync(join(here, "template.tmpl"), "utf8");

// brief を {{key}} のフラットな辞書に展開（colors / copy はキーをそのまま使う）
const vars = {
  footage: brief.footage,
  ...brief.colors,
  ...brief.copy,
};

const missing = [];
html = html.replace(/\{\{\s*([\w.]+)\s*\}\}/g, (_, key) => {
  if (key in vars) return String(vars[key]);
  missing.push(key);
  return "";
});

if (missing.length) {
  console.error(
    "⚠ brief.json に未定義のプレースホルダ:",
    [...new Set(missing)].join(", "),
  );
  process.exit(1);
}

writeFileSync(join(here, "index.html"), html);
console.log("✓ index.html を生成しました（brief.json から）");
