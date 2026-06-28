// frontend/app/reel-finish/page.tsx
import Link from "next/link";

const TASTES: { name: string; jp: string; mood: string }[] = [
  { name: "cinematic-serif", jp: "シネマ明朝", mood: "静か・上質・落ち着いた" },
  { name: "bold-gothic", jp: "ボールドゴシック", mood: "力強い・SNS映え" },
  { name: "minimal-light", jp: "ミニマル明るめ", mood: "明るい・エディトリアル" },
  { name: "tategaki-wa", jp: "縦書き和", mood: "和・凛とした余白" },
];

function Code({ children }: { children: string }) {
  return (
    <pre className="overflow-x-auto rounded-xl border border-gray-800 bg-gray-950 p-4 text-xs leading-relaxed text-emerald-200">
      <code>{children}</code>
    </pre>
  );
}

export default function ReelFinishGuide() {
  return (
    <main className="mx-auto max-w-3xl px-6 py-10">
      <Link href="/" className="text-sm text-gray-400 hover:text-white">
        ← トップ
      </Link>

      {/* Hero */}
      <div className="mt-3 mb-8">
        <h1 className="flex items-center gap-2 text-3xl font-bold">
          🎞️ リール仕上げ
        </h1>
        <p className="mt-3 text-base text-gray-300">
          編集した動画に<span className="text-white">ブランドの世界観</span>
          を乗せて、雑誌・CM のような縦型リールに仕上げます。
        </p>
        {/* flow */}
        <div className="mt-5 flex items-center gap-2 text-sm">
          <span className="rounded-lg bg-gray-800 px-3 py-2 text-gray-200">
            🎬 編集した動画
          </span>
          <span className="text-gray-500">+</span>
          <span className="rounded-lg bg-gray-800 px-3 py-2 text-gray-200">
            🎯 アカウント情報
          </span>
          <span className="text-gray-500">→</span>
          <span className="rounded-lg bg-emerald-600/20 px-3 py-2 font-semibold text-emerald-200 ring-1 ring-emerald-500/40">
            ✨ ブランドリール
          </span>
        </div>
      </div>

      {/* Taste gallery — 一番わかりやすい：実物を見る */}
      <section className="mb-10">
        <h2 className="mb-1 text-lg font-semibold">
          4つのテイストから選ぶ
        </h2>
        <p className="mb-4 text-sm text-gray-400">
          同じ動画・同じ文言から、まったく違う世界観に。下は同じ場面「ととのう、という時間。」の比較です。
        </p>
        <div className="grid grid-cols-2 gap-4 sm:grid-cols-4">
          {TASTES.map((t) => (
            <div key={t.name}>
              <div className="overflow-hidden rounded-xl border border-gray-800 bg-gray-900">
                {/* eslint-disable-next-line @next/next/no-img-element */}
                <img
                  src={`/tastes/${t.name}.jpg`}
                  alt={`${t.jp} のプレビュー`}
                  className="aspect-[9/16] w-full object-cover"
                />
              </div>
              <div className="mt-2 text-sm font-semibold text-white">
                {t.jp}
              </div>
              <div className="text-xs text-gray-400">{t.mood}</div>
              <div className="mt-0.5 font-mono text-[11px] text-emerald-300/80">
                {t.name}
              </div>
            </div>
          ))}
        </div>
      </section>

      {/* How to — 3 steps */}
      <section className="mb-8">
        <h2 className="mb-4 text-lg font-semibold">作り方（3ステップ）</h2>
        <div className="space-y-3">
          <div className="flex gap-4 rounded-xl border border-gray-800 bg-gray-900 p-4">
            <div className="flex h-8 w-8 flex-shrink-0 items-center justify-center rounded-full bg-emerald-600 text-sm font-bold">
              1
            </div>
            <div className="text-sm">
              <div className="font-semibold text-white">
                アカウント設定を登録する
              </div>
              <div className="mt-1 text-gray-400">
                ブランド名・ハンドル・トーンを{" "}
                <Link
                  href="/post/profile"
                  className="text-emerald-300 underline"
                >
                  アカウント設定
                </Link>{" "}
                で登録（ワードマークやハンドルに自動で使われます）。
              </div>
            </div>
          </div>

          <div className="flex gap-4 rounded-xl border border-gray-800 bg-gray-900 p-4">
            <div className="flex h-8 w-8 flex-shrink-0 items-center justify-center rounded-full bg-emerald-600 text-sm font-bold">
              2
            </div>
            <div className="text-sm">
              <div className="font-semibold text-white">
                動画を編集する
              </div>
              <div className="mt-1 text-gray-400">
                <Link href="/edit" className="text-emerald-300 underline">
                  編集する
                </Link>{" "}
                からアップロード・処理。完了画面やURLの{" "}
                <code className="text-gray-300">job_id</code> を控えます。
              </div>
            </div>
          </div>

          <div className="flex gap-4 rounded-xl border border-gray-800 bg-gray-900 p-4">
            <div className="flex h-8 w-8 flex-shrink-0 items-center justify-center rounded-full bg-emerald-600 text-sm font-bold">
              3
            </div>
            <div className="w-full text-sm">
              <div className="font-semibold text-white">
                ホスト（mac）で1コマンド
              </div>
              <div className="mt-1 mb-3 text-gray-400">
                テイストを選んで実行すると、生成 → レンダー → 再生まで自動です。
              </div>
              <Code>{`node hyperframes/new-from-job.mjs <job_id> \\
  --template tategaki-wa --render --open`}</Code>
              <div className="mt-2 text-xs text-gray-500">
                <code className="text-gray-400">--template</code>{" "}
                に上の4つのいずれかを指定。出力は{" "}
                <code className="text-gray-400">hyperframes/jobs/&lt;job_id&gt;/renders/</code>。
              </div>
            </div>
          </div>
        </div>
      </section>

      {/* Edit */}
      <section className="mb-8">
        <h2 className="mb-2 text-lg font-semibold">文言を変えたいとき</h2>
        <p className="text-sm text-gray-400">
          生成された{" "}
          <code className="text-gray-300">brief.json</code>{" "}
          のコピーを書き換えて作り直すだけ。
          <code className="text-gray-300">&lt;em&gt;…&lt;/em&gt;</code>{" "}
          でアクセント色、<code className="text-gray-300">&lt;br /&gt;</code>{" "}
          で改行。ブラウザの{" "}
          <code className="text-gray-300">npm run dev</code>{" "}
          でライブプレビューもできます。
        </p>
      </section>

      <div className="rounded-xl border border-amber-500/40 bg-amber-500/10 p-4 text-sm text-amber-100">
        <span className="font-semibold">ⓘ レンダーはホスト（mac）側で実行</span>
        <div className="mt-1 text-amber-100/80">
          HyperFrames はヘッドレス Chromium
          を使うため、レンダーはアプリ内ではなくホストで行います。詳しい手順は{" "}
          <code className="text-amber-200">hyperframes/README.md</code>。
        </div>
      </div>
    </main>
  );
}
