// frontend/app/page.tsx
import Link from "next/link";

export default function Home() {
  return (
    <main className="mx-auto flex min-h-screen max-w-3xl flex-col items-center justify-center px-6 py-12">
      <h1 className="mb-2 text-3xl font-bold">Reel Creator</h1>
      <p className="mb-10 text-sm text-gray-400">
        TikTok/IG リール用動画の編集と投稿予約
      </p>

      <div className="grid w-full grid-cols-1 gap-5 sm:grid-cols-2">
        <Link
          href="/edit"
          className="group rounded-2xl border border-gray-800 bg-gray-900 p-8 transition hover:border-blue-500/60 hover:bg-gray-800"
        >
          <div className="mb-3 text-4xl">✂️</div>
          <div className="mb-1 text-xl font-semibold">編集する</div>
          <p className="text-sm text-gray-400">
            無音削除・AI 字幕付与で動画を仕上げる
          </p>
        </Link>

        <Link
          href="/post"
          className="group rounded-2xl border border-gray-800 bg-gray-900 p-8 transition hover:border-pink-500/60 hover:bg-gray-800"
        >
          <div className="mb-3 text-4xl">📤</div>
          <div className="mb-1 text-xl font-semibold">投稿する</div>
          <p className="text-sm text-gray-400">
            完成動画を Instagram / YouTube に予約投稿
          </p>
        </Link>

        <Link
          href="/post/profile"
          className="group rounded-2xl border border-gray-800 bg-gray-900 p-8 transition hover:border-purple-500/60 hover:bg-gray-800 sm:col-span-2"
        >
          <div className="mb-3 text-4xl">🎯</div>
          <div className="mb-1 text-xl font-semibold">アカウント設定</div>
          <p className="text-sm text-gray-400">
            アカウントの性質・ターゲットを登録し AI 生成を最適化
          </p>
        </Link>
      </div>
    </main>
  );
}
