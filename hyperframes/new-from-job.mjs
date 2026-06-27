#!/usr/bin/env node
// reel-creator のジョブ + アカウントプロファイルから HyperFrames プロジェクトを組み立てる。
//
// 使い方:
//   node hyperframes/new-from-job.mjs <job_id> [--grade cinematic] [--start 40] [--duration 12] [--render]
//
// やること:
//   1. GET /api/account-profile  → ブランド名/ハンドル等
//   2. プロファイルから brief.json を生成（build_brief）
//   3. GET /api/hyperframes/footage/<job>  → 色味済み縦型 footage.mp4 を取得
//   4. テンプレ(ichiki-kuukan)を雛形に hyperframes/jobs/<job>/ を生成
//   5. --render 指定時はそのままレンダー
//
// レンダーはホスト(mac)側で実行する想定（HyperFrames はヘッドレス Chromium を使うため）。
import { readFileSync, writeFileSync, mkdirSync, copyFileSync, cpSync, existsSync, readdirSync, statSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";
import { execSync } from "node:child_process";

const HERE = dirname(fileURLToPath(import.meta.url));
const TEMPLATE_DIR = join(HERE, "ichiki-kuukan"); // 雛形（template.tmpl / build.mjs / fonts / package.json …）
const API = process.env.REEL_API || "http://localhost:8000";

// ---- args ----
const args = process.argv.slice(2);
const jobId = args.find((a) => !a.startsWith("--"));
const opt = (name, def) => {
  const i = args.indexOf(`--${name}`);
  return i >= 0 && args[i + 1] && !args[i + 1].startsWith("--") ? args[i + 1] : def;
};
const flag = (name) => args.includes(`--${name}`);
if (!jobId) {
  console.error("usage: node new-from-job.mjs <job_id> [--grade cinematic] [--start 40] [--duration 12] [--render]");
  process.exit(1);
}
const grade = opt("grade", "cinematic");
const start = opt("start", "0");
const duration = opt("duration", "12");
const template = opt("template", "cinematic-serif"); // テイスト: cinematic-serif | bold-gothic

// ---- brief 生成（プロファイル → ブランドリールのコピー）----
function romajiFromHandle(handle) {
  if (!handle) return "";
  return handle.replace(/^@/, "").replace(/[_-]+/g, " ").trim().toUpperCase();
}
function buildBrief(profile) {
  const handleRaw = (profile.handle || "").replace(/^@/, "").trim();
  const wordmark = (profile.brand_name || profile.niche || "BRAND").trim();
  return {
    _comment: "自動生成。コピー(copy)は仮置きなので編集して `npm run render`。phrase は <em>…</em> でアクセント。",
    template, // テイスト(templates/<name>.tmpl)
    footage: "footage.mp4",
    colors: {
      ivory: "#f4ede0",
      accent: "#e9d9b6",
      rule: "#cbb88f",
      romaji_color: "#d9cfbf",
      bg: "#0a0a0a",
    },
    copy: {
      wordmark,
      romaji: romajiFromHandle(handleRaw) || wordmark,
      // ↓ 仮置き。アカウントの実コピーに差し替える。
      phrase1: "ととのう、<br />という<em>時間</em>。",
      phrase2: "日々に、<br />ひとつの<em>余白</em>を。",
      kicker: "STUDIO",
      handle: handleRaw ? `@${handleRaw}` : "",
    },
  };
}

async function main() {
  // 1. profile
  const pr = await fetch(`${API}/api/account-profile`);
  if (!pr.ok) throw new Error(`account-profile 取得失敗: ${pr.status}`);
  const profile = await pr.json();

  // 2. brief
  const brief = buildBrief(profile);

  // 3. footage
  const fUrl = `${API}/api/hyperframes/footage/${jobId}?grade=${encodeURIComponent(grade)}&start=${start}&duration=${duration}`;
  const fr = await fetch(fUrl);
  if (!fr.ok) throw new Error(`footage 取得失敗: ${fr.status} (${await fr.text().catch(() => "")})`);
  const footage = Buffer.from(await fr.arrayBuffer());

  // 4. scaffold
  const dest = join(HERE, "jobs", jobId);
  mkdirSync(dest, { recursive: true });
  for (const f of ["build.mjs", "package.json", "hyperframes.json"]) {
    copyFileSync(join(TEMPLATE_DIR, f), join(dest, f));
  }
  cpSync(join(TEMPLATE_DIR, "templates"), join(dest, "templates"), { recursive: true });
  cpSync(join(TEMPLATE_DIR, "fonts"), join(dest, "fonts"), { recursive: true });
  writeFileSync(join(dest, "footage.mp4"), footage);
  writeFileSync(join(dest, "brief.json"), JSON.stringify(brief, null, 2) + "\n");
  // ローカル成果物は追跡しない
  writeFileSync(join(dest, ".gitignore"), "node_modules/\nrenders/\nsnapshots/\nindex.html\nfootage.mp4\n");

  console.log(`✓ プロジェクトを生成: hyperframes/jobs/${jobId}/`);
  console.log(`  テイスト: ${brief.template}`);
  console.log(`  ブランド: ${brief.copy.wordmark}  ハンドル: ${brief.copy.handle || "(未設定)"}`);
  console.log(`  footage: ${(footage.length / 1e6).toFixed(1)}MB (${grade}, ${start}s〜+${duration}s)`);

  // 5. render (任意)
  if (flag("render")) {
    console.log("→ レンダー中…");
    execSync("npm run render", { cwd: dest, stdio: "inherit" });
    if (flag("open")) {
      // 最新の MP4 を開く（macOS）
      try {
        const rdir = join(dest, "renders");
        const mp4 = readdirSync(rdir)
          .filter((f) => f.endsWith(".mp4"))
          .map((f) => ({ f, t: statSync(join(rdir, f)).mtimeMs }))
          .sort((a, b) => b.t - a.t)[0];
        if (mp4) execSync(`open ${JSON.stringify(join(rdir, mp4.f))}`);
      } catch (e) {
        console.warn("(open に失敗:", e.message, ")");
      }
    }
  } else {
    console.log("\n次の手順:");
    console.log(`  1) hyperframes/jobs/${jobId}/brief.json のコピーを編集`);
    console.log(`  2) cd hyperframes/jobs/${jobId} && npm run snapshot   # 確認`);
    console.log(`     npm run render   # MP4 書き出し`);
  }
}

main().catch((e) => {
  console.error("✗", e.message);
  process.exit(1);
});
