// frontend/app/reel-finish/page.tsx
import Link from "next/link";

const TASTES: { name: string; mood: string; type: string }[] = [
  { name: "cinematic-serif", mood: "静か・上質・暗", type: "明朝・中央" },
  { name: "bold-gothic", mood: "力強い・SNS映え・暗", type: "ゴシック・左寄せ・バー" },
  { name: "minimal-light", mood: "明るい・エディトリアル", type: "明朝・クリーム帯" },
  { name: "tategaki-wa", mood: "和・凛とした余白", type: "縦書き明朝" },
];

function Code({ children }: { children: string }) {
  return (
    <pre className="overflow-x-auto rounded-xl border border-gray-800 bg-gray-950 p-4 text-sm text-emerald-200">
      <code>{children}</code>
    </pre>
  );
}

export default function ReelFinishGuide() {
  return (
    <main className="mx-auto max-w-2xl px-6 py-10">
      <div className="mb-6">
        <Link href="/" className="text-sm text-gray-400 hover:text-white">
          ← トップ
        </Link>
        <h1 className="mt-1 flex items-center gap-2 text-2xl font-bold">
          🎞️ リール仕上げ（HyperFrames）
        </h1>
        <p className="mt-2 text-sm text-gray-400">
          編集した映像にブランドタイポを乗せて、Instagram
          リール級の縦型動画（1080×1920）を作る工程です。アカウント設定（ブランド名・ハンドル）に沿って自動でセットアップします。
        </p>
      </div>

      <section className="mb-8">
        <h2 className="mb-2 text-lg font-semibold">使い方（3ステップ）</h2>
        <ol className="space-y-3 text-sm text-gray-300">
          <li className="rounded-xl border border-gray-800 bg-gray-900 p-4">
            <span className="font-semibold text-white">
              1. アカウント設定を登録
            </span>
            <div className="mt-1 text-gray-400">
              ブランド名・ハンドル・トーン等を{" "}
              <Link
                href="/post/profile"
                className="text-emerald-300 underline"
              >
                アカウント設定
              </Link>{" "}
              で登録（ワードマークやハンドルに使われます）。
            </div>
          </li>
          <li className="rounded-xl border border-gray-800 bg-gray-900 p-4">
            <span className="font-semibold text-white">
              2. 動画を編集して job_id を得る
            </span>
            <div className="mt-1 text-gray-400">
              <Link href="/edit" className="text-emerald-300 underline">
                編集する
              </Link>{" "}
              からアップロード・処理（無音削除・色味など）。URL や結果に出る
              job_id を控えます。
            </div>
          </li>
          <li className="rounded-xl border border-gray-800 bg-gray-900 p-4">
            <span className="font-semibold text-white">
              3. ホスト（mac）でワンコマンド
            </span>
            <div className="mt-2">
              <Code>{`node hyperframes/new-from-job.mjs <job_id> \\
  --template tategaki-wa --grade cinematic \\
  --start 40 --duration 12 --render --open`}</Code>
            </div>
            <div className="mt-1 text-gray-400">
              生成 → レンダー → 再生まで一気に。出力は{" "}
              <code className="text-gray-300">
                hyperframes/jobs/&lt;job_id&gt;/renders/
              </code>
              。
            </div>
          </li>
        </ol>
      </section>

      <section className="mb-8">
        <h2 className="mb-2 text-lg font-semibold">テイスト（仕上げの世界観）</h2>
        <p className="mb-3 text-sm text-gray-400">
          <code className="text-gray-300">--template</code> または{" "}
          <code className="text-gray-300">brief.json</code> の{" "}
          <code className="text-gray-300">template</code>{" "}
          で選択。どれも同じ文言・配色で動きます。
        </p>
        <div className="grid grid-cols-1 gap-2 sm:grid-cols-2">
          {TASTES.map((t) => (
            <div
              key={t.name}
              className="rounded-xl border border-gray-800 bg-gray-900 p-4"
            >
              <div className="font-mono text-sm text-emerald-300">{t.name}</div>
              <div className="mt-1 text-sm text-white">{t.mood}</div>
              <div className="text-xs text-gray-500">{t.type}</div>
            </div>
          ))}
        </div>
      </section>

      <section className="mb-8">
        <h2 className="mb-2 text-lg font-semibold">文言・配色を編集する</h2>
        <p className="mb-3 text-sm text-gray-400">
          生成された{" "}
          <code className="text-gray-300">
            hyperframes/jobs/&lt;job_id&gt;/brief.json
          </code>{" "}
          を編集して再レンダー。
          <code className="text-gray-300">&lt;em&gt;…&lt;/em&gt;</code>{" "}
          でアクセント色、
          <code className="text-gray-300">&lt;br /&gt;</code> で改行。
        </p>
        <Code>{`cd hyperframes/jobs/<job_id>
npm run snapshot   # 5枚で即確認
npm run dev        # ブラウザでライブプレビュー
npm run render     # MP4 を書き出し`}</Code>
      </section>

      <div className="rounded-xl border border-amber-500/40 bg-amber-500/10 p-4 text-sm text-amber-100">
        <span className="font-semibold">ⓘ レンダーはホスト（mac）側で実行</span>
        <div className="mt-1 text-amber-100/80">
          HyperFrames はヘッドレス Chromium
          を使うため、レンダーはアプリ内ではなくホストで行います。詳細は{" "}
          <code className="text-amber-200">hyperframes/README.md</code>。
        </div>
      </div>
    </main>
  );
}
