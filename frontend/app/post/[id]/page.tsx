// frontend/app/post/[id]/page.tsx
"use client";

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import {
  getPost,
  updatePost,
  deletePost,
  publishNow,
  retryPost,
  postMediaUrl,
  type PostItem,
  type ScheduledPost,
  type PrivacyStatus,
} from "@/lib/api";
import { formatJst, isoToLocalInput, localInputToIso } from "@/lib/datetime";
import PostStatusBadge from "@/components/PostStatusBadge";

const inputCls =
  "w-full rounded-lg border border-gray-700 bg-gray-900 px-3 py-2 text-sm focus:border-blue-500 focus:outline-none";

function PlatformCard({
  post,
  busy,
  onPublishNow,
  onRetry,
}: {
  post: ScheduledPost;
  busy: boolean;
  onPublishNow: () => void;
  onRetry: () => void;
}) {
  const isIg = post.platform === "instagram";
  const canPublish = post.status === "scheduled" || post.status === "failed";
  return (
    <div className="rounded-xl border border-gray-800 bg-gray-900/50 p-5">
      <div className="mb-3 flex items-center gap-2">
        <h3 className="font-semibold">
          {isIg ? "Instagram Reels" : "YouTube Shorts"}
        </h3>
        <PostStatusBadge status={post.status} />
        <div className="ml-auto flex gap-2">
          {post.status === "failed" && (
            <button
              onClick={onRetry}
              disabled={busy}
              className="rounded border border-gray-700 px-3 py-1 text-xs hover:bg-gray-800 disabled:opacity-50"
            >
              リトライ
            </button>
          )}
          {canPublish && (
            <button
              onClick={onPublishNow}
              disabled={busy}
              className="rounded bg-pink-600 px-3 py-1 text-xs font-semibold hover:bg-pink-500 disabled:opacity-50"
            >
              {busy ? "投稿中…" : "今すぐ投稿"}
            </button>
          )}
        </div>
      </div>
      <dl className="space-y-1.5 text-sm">
        {isIg ? (
          <Field label="キャプション" value={post.caption} />
        ) : (
          <>
            <Field label="タイトル" value={post.title} />
            <Field label="説明文" value={post.description} />
            <Field label="公開設定" value={post.privacy_status} />
          </>
        )}
        <Field label="ハッシュタグ" value={post.hashtags} />
        <Field label="予定日時" value={formatJst(post.scheduled_at)} />
        <Field
          label="投稿日時"
          value={post.posted_at ? formatJst(post.posted_at) : null}
        />
        <Field label="リトライ回数" value={String(post.retry_count)} />
        {post.posted_url && (
          <div className="flex gap-2">
            <dt className="w-24 shrink-0 text-gray-500">投稿URL</dt>
            <dd>
              <a
                href={post.posted_url}
                target="_blank"
                rel="noreferrer"
                className="text-blue-400 underline"
              >
                {post.posted_url}
              </a>
            </dd>
          </div>
        )}
        {post.error_message && (
          <div className="mt-2 rounded border border-red-500/40 bg-red-600/15 p-2 text-xs text-red-200">
            {post.error_message}
          </div>
        )}
      </dl>
    </div>
  );
}

function Field({ label, value }: { label: string; value: string | null }) {
  return (
    <div className="flex gap-2">
      <dt className="w-24 shrink-0 text-gray-500">{label}</dt>
      <dd className="min-w-0 whitespace-pre-wrap break-words text-gray-200">
        {value || "—"}
      </dd>
    </div>
  );
}

export default function PostDetailPage() {
  const params = useParams<{ id: string }>();
  const id = params.id;
  const router = useRouter();

  const [post, setPost] = useState<PostItem | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [editing, setEditing] = useState(false);
  const [saving, setSaving] = useState(false);
  const [busyPostId, setBusyPostId] = useState<string | null>(null);

  // 編集フォーム state
  const [form, setForm] = useState({
    theme: "",
    memo: "",
    hashtags: "",
    igCaption: "",
    igAt: "",
    ytTitle: "",
    ytDesc: "",
    ytAt: "",
    privacy: "public" as PrivacyStatus,
  });

  const load = useCallback(async () => {
    try {
      const data = await getPost(id);
      setPost(data);
      setError(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : "読み込みに失敗しました");
    }
  }, [id]);

  useEffect(() => {
    void (async () => {
      await load();
    })();
  }, [load]);

  const startEdit = () => {
    if (!post) return;
    const ig = post.posts.find((p) => p.platform === "instagram");
    const yt = post.posts.find((p) => p.platform === "youtube");
    setForm({
      theme: post.theme || "",
      memo: post.memo || "",
      hashtags: ig?.hashtags || yt?.hashtags || "",
      igCaption: ig?.caption || "",
      igAt: isoToLocalInput(ig?.scheduled_at),
      ytTitle: yt?.title || "",
      ytDesc: yt?.description || "",
      ytAt: isoToLocalInput(yt?.scheduled_at),
      privacy: (yt?.privacy_status as PrivacyStatus) || "public",
    });
    setEditing(true);
  };

  const save = async () => {
    setSaving(true);
    setError(null);
    try {
      await updatePost(id, {
        theme: form.theme,
        memo: form.memo,
        hashtags: form.hashtags,
        instagram_caption: form.igCaption,
        instagram_scheduled_at: localInputToIso(form.igAt),
        youtube_title: form.ytTitle,
        youtube_description: form.ytDesc,
        youtube_scheduled_at: localInputToIso(form.ytAt),
        privacy_status: form.privacy,
      });
      setEditing(false);
      await load();
    } catch (e) {
      setError(e instanceof Error ? e.message : "更新に失敗しました");
    } finally {
      setSaving(false);
    }
  };

  const doPublishNow = async (postId: string) => {
    setBusyPostId(postId);
    setError(null);
    try {
      await publishNow(postId);
      await load();
    } catch (e) {
      setError(e instanceof Error ? e.message : "投稿に失敗しました");
    } finally {
      setBusyPostId(null);
    }
  };

  const doRetry = async (postId: string) => {
    setBusyPostId(postId);
    setError(null);
    try {
      await retryPost(postId);
      await load();
    } catch (e) {
      setError(e instanceof Error ? e.message : "リトライに失敗しました");
    } finally {
      setBusyPostId(null);
    }
  };

  const handleDelete = async () => {
    if (!confirm("この投稿を削除しますか？")) return;
    try {
      await deletePost(id);
      router.push("/post");
    } catch (e) {
      alert(e instanceof Error ? e.message : "削除に失敗しました");
    }
  };

  if (error && !post) {
    return (
      <main className="mx-auto max-w-2xl px-6 py-10">
        <Link href="/post" className="text-sm text-gray-400 hover:text-white">
          ← 投稿一覧
        </Link>
        <p className="mt-4 text-red-300">{error}</p>
      </main>
    );
  }

  if (!post) {
    return (
      <main className="mx-auto max-w-2xl px-6 py-10 text-gray-500">
        読み込み中…
      </main>
    );
  }

  const hasPosted = post.posts.some((p) => p.status === "posted");
  const ig = post.posts.find((p) => p.platform === "instagram");
  const yt = post.posts.find((p) => p.platform === "youtube");

  return (
    <main className="mx-auto max-w-2xl px-6 py-10">
      <Link href="/post" className="text-sm text-gray-400 hover:text-white">
        ← 投稿一覧
      </Link>
      <div className="mb-5 mt-1 flex items-center justify-between">
        <h1 className="text-2xl font-bold">{post.theme || "（無題）"}</h1>
        <div className="flex gap-2">
          {!editing && !hasPosted && (
            <button
              onClick={startEdit}
              className="rounded border border-gray-700 px-3 py-1 text-sm hover:bg-gray-800"
            >
              編集
            </button>
          )}
          <button
            onClick={handleDelete}
            className="rounded border border-red-800/60 px-3 py-1 text-sm text-red-300 hover:bg-red-900/30"
          >
            削除
          </button>
        </div>
      </div>

      {error && (
        <div className="mb-4 rounded-lg border border-red-500/40 bg-red-600/20 p-3 text-sm text-red-200">
          {error}
        </div>
      )}

      <video
        src={postMediaUrl(post.id)}
        controls
        className="mb-6 max-h-96 w-full rounded-lg bg-black"
      />

      {editing ? (
        <div className="space-y-4">
          <input
            className={inputCls}
            placeholder="テーマ"
            value={form.theme}
            onChange={(e) => setForm({ ...form, theme: e.target.value })}
          />
          <input
            className={inputCls}
            placeholder="ハッシュタグ（最大5個）"
            value={form.hashtags}
            onChange={(e) => setForm({ ...form, hashtags: e.target.value })}
          />
          <textarea
            className={inputCls}
            placeholder="メモ"
            rows={2}
            value={form.memo}
            onChange={(e) => setForm({ ...form, memo: e.target.value })}
          />

          {ig && (
            <div className="rounded-xl border border-gray-800 p-4">
              <p className="mb-2 text-sm font-semibold text-gray-300">
                Instagram
              </p>
              <textarea
                className={inputCls}
                placeholder="キャプション"
                rows={3}
                value={form.igCaption}
                onChange={(e) =>
                  setForm({ ...form, igCaption: e.target.value })
                }
              />
              <input
                type="datetime-local"
                className={`${inputCls} mt-2`}
                value={form.igAt}
                onChange={(e) => setForm({ ...form, igAt: e.target.value })}
              />
            </div>
          )}
          {yt && (
            <div className="rounded-xl border border-gray-800 p-4">
              <p className="mb-2 text-sm font-semibold text-gray-300">
                YouTube
              </p>
              <input
                className={inputCls}
                placeholder="タイトル"
                value={form.ytTitle}
                onChange={(e) => setForm({ ...form, ytTitle: e.target.value })}
              />
              <textarea
                className={`${inputCls} mt-2`}
                placeholder="説明文"
                rows={3}
                value={form.ytDesc}
                onChange={(e) => setForm({ ...form, ytDesc: e.target.value })}
              />
              <input
                type="datetime-local"
                className={`${inputCls} mt-2`}
                value={form.ytAt}
                onChange={(e) => setForm({ ...form, ytAt: e.target.value })}
              />
              <select
                className={`${inputCls} mt-2`}
                value={form.privacy}
                onChange={(e) =>
                  setForm({ ...form, privacy: e.target.value as PrivacyStatus })
                }
              >
                <option value="public">公開</option>
                <option value="unlisted">限定公開</option>
                <option value="private">非公開</option>
              </select>
            </div>
          )}

          <div className="flex gap-3">
            <button
              onClick={save}
              disabled={saving}
              className="rounded-lg bg-pink-600 px-5 py-2 text-sm font-semibold hover:bg-pink-500 disabled:opacity-50"
            >
              {saving ? "保存中…" : "保存"}
            </button>
            <button
              onClick={() => setEditing(false)}
              className="rounded-lg border border-gray-700 px-5 py-2 text-sm hover:bg-gray-800"
            >
              キャンセル
            </button>
          </div>
        </div>
      ) : (
        <div className="space-y-4">
          {post.posts.map((sp) => (
            <PlatformCard
              key={sp.id}
              post={sp}
              busy={busyPostId === sp.id}
              onPublishNow={() => doPublishNow(sp.id)}
              onRetry={() => doRetry(sp.id)}
            />
          ))}
          {post.memo && (
            <div className="rounded-xl border border-gray-800 bg-gray-900/50 p-5 text-sm">
              <p className="mb-1 text-gray-500">メモ</p>
              <p className="whitespace-pre-wrap text-gray-200">{post.memo}</p>
            </div>
          )}
          <p className="text-xs text-gray-600">
            ※ Instagram 投稿には HTTPS で公開した動画 URL が必要です（ngrok 等で
            PUBLIC_BASE_URL を公開してください）。
          </p>
        </div>
      )}
    </main>
  );
}
