// frontend/components/VideoUploader.tsx
"use client";

import { useCallback, useState } from "react";

interface Props {
  onUploaded: (jobId: string, duration: number, previewUrl: string) => void;
}

const ACCEPTED_TYPES = ["video/mp4", "video/quicktime", "video/webm"];
const MAX_SIZE = 500 * 1024 * 1024;

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
        setError("ファイルサイズは500MB以下にしてください");
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
        border-2 border-dashed rounded-2xl p-12 text-center transition-colors cursor-pointer
        ${dragOver ? "border-blue-400 bg-blue-400/10" : "border-gray-600 hover:border-gray-400"}
        ${uploading ? "pointer-events-none opacity-60" : ""}
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
          <div className="text-xl mb-4">アップロード中...</div>
          <div className="w-full bg-gray-700 rounded-full h-2">
            <div
              className="bg-blue-500 h-2 rounded-full transition-all"
              style={{ width: `${progress}%` }}
            />
          </div>
        </div>
      ) : (
        <div>
          <div className="text-5xl mb-4">🎬</div>
          <div className="text-xl mb-2">動画をドラッグ&ドロップ</div>
          <div className="text-gray-400">
            またはクリックしてファイルを選択
          </div>
          <div className="text-gray-500 text-sm mt-4">
            MP4 / MOV / WebM（最大500MB・3分まで）
          </div>
        </div>
      )}

      {error && (
        <div className="mt-4 text-red-400 text-sm">{error}</div>
      )}
    </div>
  );
}
