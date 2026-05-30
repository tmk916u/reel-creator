// frontend/app/post/page.tsx
"use client";

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import {
  listPosts,
  deletePost,
  postThumbnailUrl,
  type PostItem,
  type ScheduledPost,
} from "@/lib/api";
import { formatJst } from "@/lib/datetime";
import PostStatusBadge from "@/components/PostStatusBadge";

function PlatformRow({ post }: { post: ScheduledPost }) {
  const label = post.platform === "instagram" ? "IG" : "YT";
  return (
    <div className="flex items-center gap-2 text-xs">
      <span className="w-7 shrink-0 font-mono text-gray-500">{label}</span>
      <PostStatusBadge status={post.status} />
      <span className="text-gray-400">{formatJst(post.scheduled_at)}</span>
      {post.posted_url && (
        <a
          href={post.posted_url}
          target="_blank"
          rel="noreferrer"
          className="text-blue-400 underline"
        >
          開く
        </a>
      )}
    </div>
  );
}

export default function PostListPage() {
  const [posts, setPosts] = useState<PostItem[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      setPosts(await listPosts());
      setError(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : "読み込みに失敗しました");
    }
  }, []);

  useEffect(() => {
    void (async () => {
      await load();
    })();
  }, [load]);

  const handleDelete = async (id: string) => {
    if (!confirm("この投稿を削除しますか？")) return;
    try {
      await deletePost(id);
      await load();
    } catch (e) {
      alert(e instanceof Error ? e.message : "削除に失敗しました");
    }
  };

  return (
    <main className="mx-auto max-w-4xl px-6 py-10">
      <div className="mb-6 flex items-center justify-between">
        <div>
          <Link href="/" className="text-sm text-gray-400 hover:text-white">
            ← トップ
          </Link>
          <h1 className="mt-1 text-2xl font-bold">投稿一覧</h1>
        </div>
        <div className="flex gap-2">
          <Link
            href="/post/connections"
            className="rounded-lg border border-gray-700 px-4 py-2 text-sm hover:bg-gray-800"
          >
            SNS 連携
          </Link>
          <Link
            href="/post/new"
            className="rounded-lg bg-pink-600 px-4 py-2 text-sm font-semibold hover:bg-pink-500"
          >
            + 新規作成
          </Link>
        </div>
      </div>

      {error && (
        <div className="mb-4 rounded-lg border border-red-500/40 bg-red-600/20 p-3 text-sm text-red-200">
          {error}
        </div>
      )}

      {posts === null ? (
        <p className="text-gray-500">読み込み中…</p>
      ) : posts.length === 0 ? (
        <div className="rounded-xl border border-dashed border-gray-700 p-12 text-center text-gray-500">
          まだ投稿がありません。「新規作成」から始めましょう。
        </div>
      ) : (
        <ul className="space-y-3">
          {posts.map((p) => (
            <li
              key={p.id}
              className="flex gap-4 rounded-xl border border-gray-800 bg-gray-900 p-4"
            >
              {/* eslint-disable-next-line @next/next/no-img-element */}
              <img
                src={postThumbnailUrl(p.id)}
                alt=""
                className="h-28 w-16 shrink-0 rounded bg-gray-800 object-cover"
                onError={(e) => {
                  (e.currentTarget as HTMLImageElement).style.visibility =
                    "hidden";
                }}
              />
              <div className="min-w-0 flex-1">
                <div className="mb-1 truncate font-semibold">
                  {p.theme || p.original_filename || "（無題）"}
                </div>
                <div className="mb-2 space-y-1">
                  {p.posts.map((sp) => (
                    <PlatformRow key={sp.id} post={sp} />
                  ))}
                </div>
                <div className="text-xs text-gray-500">
                  作成: {formatJst(p.created_at)}
                </div>
              </div>
              <div className="flex shrink-0 flex-col gap-2">
                <Link
                  href={`/post/${p.id}`}
                  className="rounded border border-gray-700 px-3 py-1 text-center text-xs hover:bg-gray-800"
                >
                  詳細
                </Link>
                <button
                  onClick={() => handleDelete(p.id)}
                  className="rounded border border-red-800/60 px-3 py-1 text-xs text-red-300 hover:bg-red-900/30"
                >
                  削除
                </button>
              </div>
            </li>
          ))}
        </ul>
      )}
    </main>
  );
}
