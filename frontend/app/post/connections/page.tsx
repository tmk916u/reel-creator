// frontend/app/post/connections/page.tsx
"use client";

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import {
  listConnections,
  youtubeConnectUrl,
  instagramConnectUrl,
  disconnect,
  type ConnectionItem,
} from "@/lib/api";

export default function ConnectionsPage() {
  const [connections, setConnections] = useState<ConnectionItem[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      setConnections(await listConnections());
      setError(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : "読み込みに失敗しました");
    }
  }, []);

  useEffect(() => {
    void (async () => {
      await load(); // 先に読み込み（成功時 setError(null) するため）
      const q = new URLSearchParams(window.location.search);
      const connected = q.get("connected");
      if (connected === "youtube") setNotice("YouTube を連携しました");
      else if (connected === "instagram") setNotice("Instagram を連携しました");

      const ytErr = q.get("youtube_error");
      const igErr = q.get("instagram_error");
      if (ytErr === "not_configured")
        setError(
          "Google OAuth が未設定です（GOOGLE_CLIENT_ID 等を .env に設定してください）",
        );
      else if (ytErr) setError(`YouTube 連携に失敗しました（${ytErr}）`);
      else if (igErr === "not_configured")
        setError(
          "Meta OAuth が未設定です（META_APP_ID 等を .env に設定してください）",
        );
      else if (igErr) setError(`Instagram 連携に失敗しました（${igErr}）`);
    })();
  }, [load]);

  const yt = connections?.find((c) => c.platform === "youtube" && c.is_active);
  const ig = connections?.find(
    (c) => c.platform === "instagram" && c.is_active,
  );

  const handleDisconnect = async (id: string) => {
    if (!confirm("連携を解除しますか？")) return;
    try {
      await disconnect(id);
      await load();
    } catch (e) {
      alert(e instanceof Error ? e.message : "解除に失敗しました");
    }
  };

  return (
    <main className="mx-auto max-w-2xl px-6 py-10">
      <Link href="/post" className="text-sm text-gray-400 hover:text-white">
        ← 投稿一覧
      </Link>
      <h1 className="mb-6 mt-1 text-2xl font-bold">SNS 連携</h1>

      {notice && (
        <div className="mb-4 rounded-lg border border-green-500/40 bg-green-600/20 p-3 text-sm text-green-200">
          {notice}
        </div>
      )}
      {error && (
        <div className="mb-4 rounded-lg border border-red-500/40 bg-red-600/20 p-3 text-sm text-red-200">
          {error}
        </div>
      )}

      <div className="space-y-4">
        {/* YouTube */}
        <div className="flex items-center justify-between rounded-xl border border-gray-800 bg-gray-900 p-5">
          <div>
            <div className="font-semibold">YouTube</div>
            <div className="text-sm text-gray-400">
              {yt
                ? `連携済み: ${yt.account_name || "(チャンネル名不明)"}`
                : "未連携"}
            </div>
          </div>
          {yt ? (
            <button
              onClick={() => handleDisconnect(yt.id)}
              className="rounded border border-red-800/60 px-4 py-2 text-sm text-red-300 hover:bg-red-900/30"
            >
              連携解除
            </button>
          ) : (
            <a
              href={youtubeConnectUrl()}
              className="rounded-lg bg-red-600 px-4 py-2 text-sm font-semibold hover:bg-red-500"
            >
              YouTube を接続
            </a>
          )}
        </div>

        {/* Instagram */}
        <div className="flex items-center justify-between rounded-xl border border-gray-800 bg-gray-900 p-5">
          <div>
            <div className="font-semibold">Instagram</div>
            <div className="text-sm text-gray-400">
              {ig
                ? `連携済み: ${ig.account_name || "(アカウント名不明)"}`
                : "未連携"}
            </div>
            {!ig && (
              <div className="mt-1 text-xs text-gray-500">
                ※ 接続には Meta App + HTTPS redirect URI（ngrok）が必要
              </div>
            )}
          </div>
          {ig ? (
            <button
              onClick={() => handleDisconnect(ig.id)}
              className="rounded border border-red-800/60 px-4 py-2 text-sm text-red-300 hover:bg-red-900/30"
            >
              連携解除
            </button>
          ) : (
            <a
              href={instagramConnectUrl()}
              className="rounded-lg bg-pink-600 px-4 py-2 text-sm font-semibold hover:bg-pink-500"
            >
              Instagram を接続
            </a>
          )}
        </div>
      </div>
    </main>
  );
}
