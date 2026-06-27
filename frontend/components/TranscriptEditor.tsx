// frontend/components/TranscriptEditor.tsx
"use client";

import { useMemo, useState } from "react";
import type { TranscriptSegment } from "@/lib/api";

interface Props {
  initialSegments: TranscriptSegment[];
  onConfirm: (segments: TranscriptSegment[]) => void;
  onCancel: () => void;
}

function formatTime(s: number): string {
  const m = Math.floor(s / 60);
  const sec = (s - m * 60).toFixed(1);
  return `${m}:${sec.padStart(4, "0")}`;
}

export default function TranscriptEditor({
  initialSegments,
  onConfirm,
  onCancel,
}: Props) {
  const [segments, setSegments] =
    useState<TranscriptSegment[]>(initialSegments);
  const [submitting, setSubmitting] = useState(false);

  const updateText = (i: number, text: string) => {
    setSegments((prev) =>
      prev.map((s, idx) => (idx === i ? { ...s, text } : s)),
    );
  };

  const deleteSegment = (i: number) => {
    setSegments((prev) => prev.filter((_, idx) => idx !== i));
  };

  const resetText = (i: number) => {
    setSegments((prev) =>
      prev.map((s, idx) =>
        idx === i ? { ...s, text: initialSegments[i].text } : s,
      ),
    );
  };

  const editedCount = useMemo(
    () => segments.filter((s, i) => s.text !== initialSegments[i]?.text).length,
    [segments, initialSegments],
  );
  const deletedCount = initialSegments.length - segments.length;

  return (
    <div className="space-y-4">
      <div className="bg-gradient-to-br from-blue-500/10 to-purple-500/10 border border-blue-500/30 rounded-2xl p-5">
        <h2 className="text-xl font-semibold flex items-center gap-2">
          <span>📝</span>字幕プレビュー＆編集
        </h2>
        <p className="text-sm text-gray-300 mt-2">
          AIが生成した字幕です。誤認識があれば修正して、OK
          で動画処理に進みましょう。
        </p>
        <div className="flex flex-wrap gap-3 mt-3 text-xs">
          <span className="bg-gray-800/60 px-3 py-1 rounded-full text-gray-300">
            📊 {segments.length} 件
          </span>
          {editedCount > 0 && (
            <span className="bg-yellow-500/20 px-3 py-1 rounded-full text-yellow-300">
              ✏️ {editedCount} 件修正
            </span>
          )}
          {deletedCount > 0 && (
            <span className="bg-red-500/20 px-3 py-1 rounded-full text-red-300">
              🗑 {deletedCount} 件削除
            </span>
          )}
        </div>
        <p className="text-[11px] text-gray-500 mt-3">
          💡 編集なしで OK
          を押すとモーション字幕（カラオケ風）が有効のまま処理されます。
          編集すると静的字幕に切り替わります。
        </p>
      </div>

      <div className="bg-gray-800/40 backdrop-blur rounded-2xl p-3 max-h-[55vh] overflow-y-auto space-y-2 border border-gray-700/50">
        {segments.length === 0 && (
          <div className="text-gray-500 text-center py-8">
            <div className="text-3xl mb-2">📭</div>
            字幕セグメントがありません
          </div>
        )}
        {segments.map((seg, i) => {
          const original = initialSegments[i]?.text ?? "";
          const changed = seg.text !== original;
          // suspicious: backend のヒューリスティック判定。 編集すると解除
          const suspicious =
            (initialSegments[i]?.suspicious ?? false) && !changed;
          return (
            <div
              key={i}
              className={`group p-3 rounded-xl transition-all ${
                changed
                  ? "bg-yellow-500/10 border border-yellow-500/40 ring-1 ring-yellow-500/20"
                  : suspicious
                    ? "bg-red-500/10 border border-red-500/50 ring-1 ring-red-500/30"
                    : "bg-gray-700/30 border border-transparent hover:border-gray-600"
              }`}
            >
              <div className="flex items-center justify-between mb-1.5">
                <div className="flex items-center gap-2">
                  <span className="text-[10px] text-gray-500 font-mono bg-gray-900/40 px-2 py-0.5 rounded">
                    #{i + 1}
                  </span>
                  <span className="text-[11px] text-gray-400 font-mono">
                    {formatTime(seg.start)} → {formatTime(seg.end)}
                  </span>
                  {changed && (
                    <span className="text-[10px] text-yellow-400 font-medium">
                      編集済
                    </span>
                  )}
                  {suspicious && (
                    <span
                      className="text-[10px] text-red-400 font-medium"
                      title="誤認識の可能性が高い箇所です。 確認・修正してください"
                    >
                      ⚠ 要確認
                    </span>
                  )}
                </div>
                <div className="flex gap-1 opacity-0 group-hover:opacity-100 transition-opacity">
                  {changed && (
                    <button
                      onClick={() => resetText(i)}
                      className="text-xs text-gray-400 hover:text-gray-100 px-2 py-1 hover:bg-gray-600/50 rounded transition-colors"
                      title="元に戻す"
                    >
                      ↩
                    </button>
                  )}
                  <button
                    onClick={() => deleteSegment(i)}
                    className="text-xs text-red-400 hover:text-red-300 px-2 py-1 hover:bg-red-900/40 rounded transition-colors"
                    title="このセグメントを削除"
                  >
                    🗑
                  </button>
                </div>
              </div>
              <input
                type="text"
                value={seg.text}
                onChange={(e) => updateText(i, e.target.value)}
                className="w-full bg-transparent text-white outline-none border-b border-gray-600/60 focus:border-blue-400 py-1.5 text-sm transition-colors"
              />
              {changed && (
                <p className="text-[10px] text-gray-500 mt-1 font-mono">
                  元: {original}
                </p>
              )}
            </div>
          );
        })}
      </div>

      <div className="flex gap-3">
        <button
          onClick={onCancel}
          disabled={submitting}
          className="flex-1 py-3 bg-gray-700/60 hover:bg-gray-600 disabled:opacity-40 disabled:cursor-not-allowed rounded-xl font-medium transition-all border border-gray-600/50"
        >
          ← 設定に戻る
        </button>
        <button
          onClick={() => {
            if (submitting) return;
            setSubmitting(true);
            onConfirm(segments);
          }}
          disabled={submitting}
          className="flex-1 py-3 bg-gradient-to-r from-blue-500 to-purple-600 hover:from-blue-400 hover:to-purple-500 disabled:from-blue-800 disabled:to-purple-900 disabled:cursor-not-allowed rounded-xl text-base font-semibold shadow-lg shadow-blue-500/30 transition-all"
        >
          {submitting ? "処理を開始中..." : "OK・動画処理に進む →"}
        </button>
      </div>
    </div>
  );
}
