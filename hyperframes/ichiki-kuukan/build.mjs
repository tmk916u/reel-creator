#!/usr/bin/env node
// brief.json の値を templates/<template>.tmpl に流し込んで index.html を生成する。
// 使い方: node build.mjs  (npm run build)
import { readFileSync, writeFileSync, existsSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";

const here = dirname(fileURLToPath(import.meta.url));
const brief = JSON.parse(readFileSync(join(here, "brief.json"), "utf8"));

// テイスト(テンプレ)選択。brief.template 省略時は cinematic-serif。
const templateName = brief.template || "cinematic-serif";
const tmplPath = join(here, "templates", `${templateName}.tmpl`);
if (!existsSync(tmplPath)) {
  console.error(
    `✗ テンプレートが見つかりません: templates/${templateName}.tmpl`,
  );
  process.exit(1);
}
let html = readFileSync(tmplPath, "utf8");

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
