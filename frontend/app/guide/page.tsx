// frontend/app/guide/page.tsx
import Link from "next/link";

const FEATURES: {
  icon: string;
  title: string;
  href: string;
  desc: string;
}[] = [
  {
    icon: "✂️",
    title: "編集する",
    href: "/edit",
    desc: "無音やフィラーを自動カット。AI字幕・色味も自動で。",
  },
  {
    icon: "🎯",
    title: "アカウント設定",
    href: "/post/profile",
    desc: "ブランド名やターゲットを登録。AIがそれに合わせて生成。",
  },
  {
    icon: "🎞️",
    title: "リール仕上げ",
    href: "/reel-finish",
    desc: "4テイストのブランド文字を乗せて世界観を統一。",
  },
  {
    icon: "📤",
    title: "投稿する",
    href: "/post",
    desc: "完成動画を Instagram / YouTube へ予約投稿。",
  },
];

const STEPS: { t: string; d: string; href: string; cta: string }[] = [
  {
    t: "アカウント設定を登録",
    d: "ブランド名・ターゲット・トーンを入れておくと、この後が全部ブランドに沿います。",
    href: "/post/profile",
    cta: "アカウント設定へ",
  },
  {
    t: "動画を編集する",
    d: "アップロードして「おまかせで自動作成」を押すだけ。無音削除・字幕・色味まで自動。",
    href: "/edit",
    cta: "編集をはじめる",
  },
  {
    t: "（任意）リール仕上げ",
    d: "ブランド文字を乗せて雑誌・CM級に。4テイストから選べます。",
    href: "/reel-finish",
    cta: "リール仕上げを見る",
  },
  {
    t: "投稿予約する",
    d: "完成した動画を Instagram / YouTube へ。",
    href: "/post",
    cta: "投稿へ",
  },
];

export default function GuidePage() {
  return (
    <main className="mx-auto max-w-3xl px-6 py-10">
      <Link href="/" className="text-sm text-gray-400 hover:text-white">
        ← トップ
      </Link>

      {/* Hero: 何ができるかを Before→After で一目で */}
      <div className="mt-3 mb-6">
        <h1 className="text-3xl font-bold">Reel Creator の使い方</h1>
        <p className="mt-3 text-base text-gray-300">
          撮った動画を入れるだけで、
          <span className="text-white">
            無音削除・AI字幕・色味・ブランド仕上げ・投稿
          </span>
          まで。スマホで撮ったままの動画が、そのまま“出せる”リールになります。
        </p>
      </div>

      <div className="mb-10 rounded-2xl border border-gray-800 bg-gray-900/60 p-5">
        <div className="flex items-center justify-center gap-4">
          <figure className="text-center">
            {/* eslint-disable-next-line @next/next/no-img-element */}
            <img
              src="/guide/before.jpg"
              alt="撮ったままの動画"
              className="aspect-[9/16] w-32 rounded-lg object-cover sm:w-40"
            />
            <figcaption className="mt-2 text-xs text-gray-400">
              撮ったまま
            </figcaption>
          </figure>

          <div className="text-center">
            <div className="text-3xl text-emerald-400">→</div>
            <div className="mt-1 text-[11px] text-gray-500">自動で仕上げ</div>
          </div>

          <figure className="text-center">
            {/* eslint-disable-next-line @next/next/no-img-element */}
            <img
              src="/guide/after.jpg"
              alt="仕上がったリール"
              className="aspect-[9/16] w-32 rounded-lg object-cover ring-2 ring-emerald-500/50 sm:w-40"
            />
            <figcaption className="mt-2 text-xs text-emerald-300">
              仕上がり
            </figcaption>
          </figure>
        </div>
      </div>

      {/* はじめ方 — 最初の導線を主役に */}
      <section className="mb-10">
        <h2 className="mb-4 text-lg font-semibold">はじめ方（4ステップ）</h2>
        <div className="space-y-3">
          {STEPS.map((s, i) => (
            <div
              key={s.t}
              className="flex flex-col gap-3 rounded-xl border border-gray-800 bg-gray-900 p-4 sm:flex-row sm:items-center"
            >
              <div className="flex h-8 w-8 flex-shrink-0 items-center justify-center rounded-full bg-emerald-600 text-sm font-bold">
                {i + 1}
              </div>
              <div className="flex-1 text-sm">
                <div className="font-semibold text-white">{s.t}</div>
                <div className="mt-0.5 text-gray-400">{s.d}</div>
              </div>
              <Link
                href={s.href}
                className="flex-shrink-0 rounded-lg border border-gray-700 px-4 py-2 text-center text-sm text-gray-200 transition hover:border-emerald-500/50 hover:text-white"
              >
                {s.cta} →
              </Link>
            </div>
          ))}
        </div>
      </section>

      {/* 機能の早見 */}
      <section className="mb-10">
        <h2 className="mb-1 text-lg font-semibold">できること（早見）</h2>
        <p className="mb-4 text-sm text-gray-400">
          各カードからそのページへ移動できます。
        </p>
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
          {FEATURES.map((f) => (
            <Link
              key={f.href}
              href={f.href}
              className="rounded-xl border border-gray-800 bg-gray-900 p-4 transition hover:border-emerald-500/50 hover:bg-gray-800"
            >
              <div className="flex items-center gap-2">
                <span className="text-xl">{f.icon}</span>
                <span className="font-semibold">{f.title}</span>
                <span className="ml-auto text-gray-500">→</span>
              </div>
              <p className="mt-2 text-sm text-gray-400">{f.desc}</p>
            </Link>
          ))}
        </div>
      </section>

      {/* Notes */}
      <div className="space-y-3">
        <div className="rounded-xl border border-amber-500/40 bg-amber-500/10 p-4 text-sm text-amber-100">
          <span className="font-semibold">ⓘ AI機能について</span>
          <div className="mt-1 text-amber-100/80">
            AIキャプション生成などは Anthropic
            のAPIキーが必要です。無音削除・色味・字幕の文字起こし・自動チェックはキー不要で動きます。
          </div>
        </div>
        <div className="rounded-xl border border-gray-700/60 bg-gray-800/40 p-4 text-sm text-gray-300">
          <span className="font-semibold text-white">
            リール仕上げ（HyperFrames）の補足
          </span>
          <div className="mt-1 text-gray-400">
            最終レンダーはホスト（mac）側で実行します。詳しい手順は{" "}
            <Link href="/reel-finish" className="text-emerald-300 underline">
              リール仕上げページ
            </Link>
            。
          </div>
        </div>
      </div>
    </main>
  );
}
