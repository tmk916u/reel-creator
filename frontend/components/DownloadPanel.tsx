// frontend/components/DownloadPanel.tsx
"use client";

import type { JobResult } from "@/lib/api";
import { getDownloadUrl } from "@/lib/api";

interface Props {
  jobId: string;
  result: JobResult;
  onReset: () => void;
}

export default function DownloadPanel({ jobId, result, onReset }: Props) {
  return (
    <div className="text-center space-y-6">
      <div className="text-6xl">✅</div>
      <h2 className="text-2xl font-bold">処理が完了しました！</h2>

      <div className="bg-gray-800 rounded-xl p-6 max-w-md mx-auto">
        <div className="grid grid-cols-2 gap-4 text-left">
          <div>
            <div className="text-gray-400 text-sm">元の長さ</div>
            <div className="text-lg">{result.original_duration.toFixed(1)}秒</div>
          </div>
          <div>
            <div className="text-gray-400 text-sm">処理後の長さ</div>
            <div className="text-lg">{result.processed_duration.toFixed(1)}秒</div>
          </div>
          <div className="col-span-2">
            <div className="text-gray-400 text-sm">削除された無音</div>
            <div className="text-lg text-blue-400">
              {result.silence_removed.toFixed(1)}秒
              ({((result.silence_removed / result.original_duration) * 100).toFixed(0)}% 短縮)
            </div>
          </div>
        </div>
      </div>

      <video
        src={getDownloadUrl(jobId)}
        controls
        className="rounded-xl max-h-[400px] mx-auto"
      />

      <div className="flex gap-4 justify-center">
        <a
          href={getDownloadUrl(jobId)}
          download
          className="px-8 py-3 bg-blue-600 hover:bg-blue-500 rounded-xl text-lg font-semibold transition-colors"
        >
          ダウンロード
        </a>
        <button
          onClick={onReset}
          className="px-8 py-3 bg-gray-700 hover:bg-gray-600 rounded-xl text-lg transition-colors"
        >
          もう1本作る
        </button>
      </div>
    </div>
  );
}
