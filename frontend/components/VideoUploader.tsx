// frontend/components/VideoUploader.tsx
"use client";

import { useCallback, useState } from "react";

interface Props {
  onUploaded: (jobId: string, duration: number, previewUrl: string) => void;
}

const ACCEPTED_TYPES = ["video/mp4", "video/quicktime", "video/webm"];
const MAX_SIZE = 1024 * 1024 * 1024;

export default function VideoUploader({ onUploaded }: Props) {
  const [dragOver, setDragOver] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [progress, setProgress] = useState(0);

  const handleFile = useCallback(
    async (file: File) => {
      setError(null);

      if (!ACCEPTED_TYPES.includes(file.type)) {
        setError("対応形式: MP4, MOV, WebM");
        return;
      }
      if (file.size > MAX_SIZE) {
        setError("ファイルサイズは1GB以下にしてください");
        return;
      }

      setUploading(true);
      setProgress(0);

      try {
        const { uploadVideo } = await import("@/lib/api");
        const result = await uploadVideo(file);
        const previewUrl = URL.createObjectURL(file);
        onUploaded(result.job_id, result.duration, previewUrl);
      } catch (e) {
        setError(e instanceof Error ? e.message : "アップロードに失敗しました");
      } finally {
        setUploading(false);
      }
    },
    [onUploaded]
  );

  return (
    <div className="space-y-4">
      <div
        onDragOver={(e) => {
          e.preventDefault();
          setDragOver(true);
        }}
        onDragLeave={() => setDragOver(false)}
        onDrop={(e) => {
          e.preventDefault();
          setDragOver(false);
          const file = e.dataTransfer.files[0];
          if (file) handleFile(file);
        }}
        className={`
          relative overflow-hidden border-2 border-dashed rounded-3xl p-14 text-center cursor-pointer transition-all duration-300
          ${
            dragOver
              ? "border-blue-400 bg-blue-400/20 scale-[1.02] shadow-xl shadow-blue-500/30"
              : "border-gray-600 hover:border-blue-400/60 hover:bg-gray-800/40"
          }
          ${uploading ? "pointer-events-none opacity-70" : ""}
        `}
        onClick={() => {
          if (uploading) return;
          const input = document.createElement("input");
          input.type = "file";
          input.accept = "video/mp4,video/quicktime,video/webm";
          input.onchange = () => {
            const file = input.files?.[0];
            if (file) handleFile(file);
          };
          input.click();
        }}
      >
        {uploading ? (
          <div>
            <div className="inline-block w-12 h-12 border-4 border-blue-500 border-t-transparent rounded-full animate-spin mb-4" />
            <div className="text-lg font-medium mb-3">アップロード中...</div>
            <div className="w-full max-w-xs mx-auto bg-gray-700 rounded-full h-2 overflow-hidden">
              <div
                className="bg-gradient-to-r from-blue-500 to-purple-500 h-2 rounded-full transition-all"
                style={{ width: `${progress}%` }}
              />
            </div>
          </div>
        ) : (
          <div>
            <div className="text-6xl mb-4">🎬</div>
            <div className="text-2xl font-bold mb-2">
              動画を<span className="bg-gradient-to-r from-blue-400 to-purple-400 bg-clip-text text-transparent">ドラッグ&ドロップ</span>
            </div>
            <div className="text-gray-400 text-sm">
              または<span className="underline">クリックしてファイルを選択</span>
            </div>
            <div className="flex flex-wrap gap-2 justify-center mt-5 text-xs">
              <span className="bg-gray-800/60 border border-gray-700 px-3 py-1 rounded-full text-gray-400">
                📁 MP4 / MOV / WebM
              </span>
              <span className="bg-gray-800/60 border border-gray-700 px-3 py-1 rounded-full text-gray-400">
                💾 最大 1GB
              </span>
              <span className="bg-gray-800/60 border border-gray-700 px-3 py-1 rounded-full text-gray-400">
                ⏱ 最大 5分
              </span>
            </div>
          </div>
        )}
      </div>

      {error && (
        <div className="p-3 bg-red-500/10 border border-red-500/40 rounded-xl text-red-300 text-sm flex items-center gap-2">
          <span>⚠️</span>
          <span>{error}</span>
        </div>
      )}

      <div className="text-center text-xs text-gray-500">
        TikTok / Instagram Reels 用の縦型動画（9:16）がおすすめ
      </div>
    </div>
  );
}
