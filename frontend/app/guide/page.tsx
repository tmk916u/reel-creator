// frontend/app/guide/page.tsx
import Link from "next/link";

const FEATURES: {
  icon: string;
  title: string;
  href: string;
  desc: string;
  points: string[];
}[] = [
  {
    icon: "✂️",
    title: "編集する",
    href: "/edit",
    desc: "動画をアップロードして自動で仕上げる",
    points: [
      "無音・フィラー（「えーっと」等）・言い直しを自動カット",
      "AI字幕の自動生成＆プレビュー編集",
      "色味（カラーグレード）を自分の動画で見比べて選択",
      "「おまかせ」で中身を判定し最適設定を自動適用",
      "出力の自動QC（尺崩れ・誤字幕などを投稿前に警告）",
    ],
  },
  {
    icon: "🎯",
    title: "アカウント設定",
    href: "/post/profile",
    desc: "アカウントの性質を登録してAI生成を最適化",
    points: [
      "ブランド名・ハンドル・ターゲット・トーン・NG語を登録",
      "AIキャプション生成がこの文脈に沿った内容に",
      "リール仕上げのワードマーク・ハンドルにも自動利用",
    ],
  },
  {
    icon: "🎞️",
    title: "リール仕上げ",
    href: "/reel-finish",
    desc: "ブランドタイポを乗せて雑誌・CM級のリールに",
    points: [
      "4テイスト（明朝・ゴシック・明るめ・縦書き和）から選択",
      "アカウント情報から自動でセットアップ",
      "ホスト（mac）で1コマンド実行",
    ],
  },
  {
    icon: "📤",
    title: "投稿する",
    href: "/post",
    desc: "完成動画をSNSへ予約投稿",
    points: [
      "Instagram Reels / YouTube へ予約投稿",
      "SNS連携（OAuth）で接続",
      "キャプション・ハッシュタグを付けて管理",
    ],
  },
];

export default function GuidePage() {
  return (
    <main className="mx-auto max-w-3xl px-6 py-10">
      <Link href="/" className="text-sm text-gray-400 hover:text-white">
        ← トップ
      </Link>

      {/* Hero */}
      <div className="mt-3 mb-8">
        <h1 className="text-3xl font-bold">Reel Creator の使い方</h1>
        <p className="mt-3 text-base text-gray-300">
          撮った動画を入れるだけで、<span className="text-white">無音削除・AI字幕・色味・ブランド仕上げ・投稿予約</span>
          まで。TikTok / Instagram リール向けの動画を一気に作れます。
        </p>
      </div>

      {/* Flow */}
      <section className="mb-10">
        <h2 className="mb-3 text-lg font-semibold">全体の流れ</h2>
        <div className="flex flex-wrap items-center gap-2 text-sm">
          {[
            "📤 アップロード",
            "✂️ 編集（無音削除・字幕・色味）",
            "🎞️ リール仕上げ（任意）",
            "📅 投稿予約",
          ].map((s, i, arr) => (
            <span key={s} className="flex items-center gap-2">
              <span className="rounded-lg bg-gray-800 px-3 py-2 text-gray-200">
                {s}
              </span>
              {i < arr.length - 1 && <span className="text-gray-500">→</span>}
            </span>
          ))}
        </div>
        <p className="mt-3 text-sm text-gray-400">
          ※「アカウント設定」を先に登録しておくと、AI生成とリール仕上げがブランドに沿った内容になります。
        </p>
      </section>

      {/* Features */}
      <section className="mb-10">
        <h2 className="mb-4 text-lg font-semibold">主な機能</h2>
        <div className="space-y-4">
          {FEATURES.map((f) => (
            <Link
              key={f.href}
              href={f.href}
              className="block rounded-2xl border border-gray-800 bg-gray-900 p-5 transition hover:border-emerald-500/50 hover:bg-gray-800"
            >
              <div className="flex items-center gap-3">
                <span className="text-2xl">{f.icon}</span>
                <div>
                  <div className="text-lg font-semibold">{f.title}</div>
                  <div className="text-sm text-gray-400">{f.desc}</div>
                </div>
                <span className="ml-auto text-gray-500">→</span>
              </div>
              <ul className="mt-3 space-y-1 pl-1 text-sm text-gray-300">
                {f.points.map((p) => (
                  <li key={p} className="flex gap-2">
                    <span className="text-emerald-400">・</span>
                    <span>{p}</span>
                  </li>
                ))}
              </ul>
            </Link>
          ))}
        </div>
      </section>

      {/* Quick start */}
      <section className="mb-10">
        <h2 className="mb-4 text-lg font-semibold">はじめ方（おすすめ手順）</h2>
        <ol className="space-y-3">
          {[
            ["アカウント設定を登録", "ブランド名・ターゲット・トーンを入れておく"],
            ["動画を編集", "「編集する」でアップロード →「おまかせで自動作成」が手軽"],
            ["（任意）リール仕上げ", "ブランドタイポを乗せて世界観を統一"],
            ["投稿予約", "完成動画をInstagram / YouTubeへ"],
          ].map(([t, d], i) => (
            <li
              key={t}
              className="flex gap-4 rounded-xl border border-gray-800 bg-gray-900 p-4"
            >
              <div className="flex h-8 w-8 flex-shrink-0 items-center justify-center rounded-full bg-emerald-600 text-sm font-bold">
                {i + 1}
              </div>
              <div className="text-sm">
                <div className="font-semibold text-white">{t}</div>
                <div className="mt-0.5 text-gray-400">{d}</div>
              </div>
            </li>
          ))}
        </ol>
      </section>

      {/* Notes */}
      <div className="space-y-3">
        <div className="rounded-xl border border-amber-500/40 bg-amber-500/10 p-4 text-sm text-amber-100">
          <span className="font-semibold">ⓘ AI生成について</span>
          <div className="mt-1 text-amber-100/80">
            AIキャプション生成・AI監督モード等は Anthropic
            のAPIキーが必要です。無音削除・色味・字幕の文字起こし・QCはキー不要で動きます。
          </div>
        </div>
        <div className="rounded-xl border border-gray-700/60 bg-gray-800/40 p-4 text-sm text-gray-300">
          <span className="font-semibold text-white">
            リール仕上げ（HyperFrames）について
          </span>
          <div className="mt-1 text-gray-400">
            レンダーはホスト（mac）側で実行します。詳しい使い方は{" "}
            <Link href="/reel-finish" className="text-emerald-300 underline">
              リール仕上げページ
            </Link>{" "}
            と <code className="text-gray-300">hyperframes/README.md</code> を参照。
          </div>
        </div>
      </div>
    </main>
  );
}
