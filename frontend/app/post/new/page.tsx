// frontend/app/post/new/page.tsx
"use client";

import { useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import {
  uploadPostVideo,
  createPost,
  postMediaUrl,
  type UploadVideoResult,
  type PrivacyStatus,
} from "@/lib/api";
import { localInputToIso } from "@/lib/datetime";

export default function NewPostPage() {
  const router = useRouter();

  const [uploaded, setUploaded] = useState<UploadVideoResult | null>(null);
  const [uploading, setUploading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const [theme, setTheme] = useState("");
  const [memo, setMemo] = useState("");
  const [hashtags, setHashtags] = useState("");

  const [igOn, setIgOn] = useState(true);
  const [igCaption, setIgCaption] = useState("");
  const [igAt, setIgAt] = useState("");

  const [ytOn, setYtOn] = useState(true);
  const [ytTitle, setYtTitle] = useState("");
  const [ytDesc, setYtDesc] = useState("");
  const [ytAt, setYtAt] = useState("");
  const [privacy, setPrivacy] = useState<PrivacyStatus>("public");

  const handleUpload = async (file: File) => {
    setUploading(true);
    setError(null);
    try {
      setUploaded(await uploadPostVideo(file));
    } catch (e) {
      setError(e instanceof Error ? e.message : "アップロードに失敗しました");
    } finally {
      setUploading(false);
    }
  };

  const handleSave = async () => {
    if (!uploaded) return;
    setSaving(true);
    setError(null);
    try {
      const result = await createPost({
        video_id: uploaded.video_id,
        theme: theme || undefined,
        memo: memo || undefined,
        hashtags: hashtags || undefined,
        post_to_instagram: igOn,
        post_to_youtube: ytOn,
        instagram_caption: igOn ? igCaption : undefined,
        instagram_scheduled_at: igOn ? localInputToIso(igAt) : undefined,
        youtube_title: ytOn ? ytTitle : undefined,
        youtube_description: ytOn ? ytDesc : undefined,
        youtube_scheduled_at: ytOn ? localInputToIso(ytAt) : undefined,
        privacy_status: privacy,
      });
      router.push(`/post/${result.id}`);
    } catch (e) {
      setError(e instanceof Error ? e.message : "保存に失敗しました");
      setSaving(false);
    }
  };

  const inputCls =
    "w-full rounded-lg border border-gray-700 bg-gray-900 px-3 py-2 text-sm focus:border-blue-500 focus:outline-none";

  return (
    <main className="mx-auto max-w-2xl px-6 py-10">
      <Link href="/post" className="text-sm text-gray-400 hover:text-white">
        ← 投稿一覧
      </Link>
      <h1 className="mb-6 mt-1 text-2xl font-bold">投稿を作成</h1>

      {error && (
        <div className="mb-4 rounded-lg border border-red-500/40 bg-red-600/20 p-3 text-sm text-red-200">
          {error}
        </div>
      )}

      {/* 1. 動画アップロード */}
      <section className="mb-6 rounded-xl border border-gray-800 bg-gray-900/50 p-5">
        <h2 className="mb-3 text-sm font-semibold text-gray-300">
          1. 動画（MP4）
        </h2>
        {uploaded ? (
          <div className="space-y-2">
            <video
              src={postMediaUrl(uploaded.video_id)}
              controls
              className="max-h-80 w-full rounded-lg bg-black"
            />
            <p className="text-xs text-gray-500">
              {uploaded.original_filename}
              {uploaded.duration_seconds != null &&
                ` ・ ${uploaded.duration_seconds}秒`}
            </p>
            <button
              onClick={() => setUploaded(null)}
              className="text-xs text-gray-400 underline"
            >
              別の動画に変更
            </button>
          </div>
        ) : (
          <label className="flex cursor-pointer flex-col items-center justify-center rounded-lg border border-dashed border-gray-700 p-8 text-sm text-gray-400 hover:border-gray-500">
            <input
              type="file"
              accept="video/mp4"
              className="hidden"
              onChange={(e) => {
                const f = e.target.files?.[0];
                if (f) handleUpload(f);
              }}
            />
            {uploading ? "アップロード中…" : "クリックして MP4 を選択"}
          </label>
        )}
      </section>

      {uploaded && (
        <>
          {/* 2. テーマ・メモ */}
          <section className="mb-6 rounded-xl border border-gray-800 bg-gray-900/50 p-5">
            <h2 className="mb-3 text-sm font-semibold text-gray-300">
              2. テーマ・共通
            </h2>
            <div className="space-y-3">
              <input
                className={inputCls}
                placeholder="テーマ（例: ダイエットの食事）"
                value={theme}
                onChange={(e) => setTheme(e.target.value)}
              />
              <input
                className={inputCls}
                placeholder="ハッシュタグ（スペース区切り・最大5個）"
                value={hashtags}
                onChange={(e) => setHashtags(e.target.value)}
              />
              <textarea
                className={inputCls}
                placeholder="メモ（任意）"
                rows={2}
                value={memo}
                onChange={(e) => setMemo(e.target.value)}
              />
            </div>
          </section>

          {/* 3. Instagram */}
          <section className="mb-6 rounded-xl border border-gray-800 bg-gray-900/50 p-5">
            <label className="mb-3 flex items-center gap-2 text-sm font-semibold text-gray-300">
              <input
                type="checkbox"
                checked={igOn}
                onChange={(e) => setIgOn(e.target.checked)}
              />
              3. Instagram Reels に投稿
            </label>
            {igOn && (
              <div className="space-y-3">
                <textarea
                  className={inputCls}
                  placeholder="Instagram キャプション（必須）"
                  rows={3}
                  value={igCaption}
                  onChange={(e) => setIgCaption(e.target.value)}
                />
                <label className="block text-xs text-gray-400">
                  投稿予定日時（JST）
                  <input
                    type="datetime-local"
                    className={`${inputCls} mt-1`}
                    value={igAt}
                    onChange={(e) => setIgAt(e.target.value)}
                  />
                </label>
              </div>
            )}
          </section>

          {/* 4. YouTube */}
          <section className="mb-6 rounded-xl border border-gray-800 bg-gray-900/50 p-5">
            <label className="mb-3 flex items-center gap-2 text-sm font-semibold text-gray-300">
              <input
                type="checkbox"
                checked={ytOn}
                onChange={(e) => setYtOn(e.target.checked)}
              />
              4. YouTube Shorts に投稿
            </label>
            {ytOn && (
              <div className="space-y-3">
                <input
                  className={inputCls}
                  placeholder="YouTube タイトル（必須）"
                  value={ytTitle}
                  onChange={(e) => setYtTitle(e.target.value)}
                />
                <textarea
                  className={inputCls}
                  placeholder="YouTube 説明文（必須）"
                  rows={3}
                  value={ytDesc}
                  onChange={(e) => setYtDesc(e.target.value)}
                />
                <div className="flex gap-3">
                  <label className="flex-1 text-xs text-gray-400">
                    投稿予定日時（JST）
                    <input
                      type="datetime-local"
                      className={`${inputCls} mt-1`}
                      value={ytAt}
                      onChange={(e) => setYtAt(e.target.value)}
                    />
                  </label>
                  <label className="text-xs text-gray-400">
                    公開設定
                    <select
                      className={`${inputCls} mt-1`}
                      value={privacy}
                      onChange={(e) =>
                        setPrivacy(e.target.value as PrivacyStatus)
                      }
                    >
                      <option value="public">公開</option>
                      <option value="unlisted">限定公開</option>
                      <option value="private">非公開</option>
                    </select>
                  </label>
                </div>
              </div>
            )}
          </section>

          <button
            onClick={handleSave}
            disabled={saving}
            className="w-full rounded-lg bg-pink-600 py-3 font-semibold hover:bg-pink-500 disabled:opacity-50"
          >
            {saving ? "保存中…" : "予約を保存"}
          </button>
        </>
      )}
    </main>
  );
}
