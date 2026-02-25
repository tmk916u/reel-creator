// frontend/components/ProcessingPanel.tsx
"use client";

import { useState } from "react";
import type { ProcessSettings } from "@/lib/api";

interface Props {
  duration: number;
  previewUrl: string;
  onStart: (settings: ProcessSettings) => void;
}

export default function ProcessingPanel({ duration, previewUrl, onStart }: Props) {
  const [settings, setSettings] = useState<ProcessSettings>({
    silence_threshold: -30,
    min_silence_duration: 0.5,
    enable_subtitles: false,
    font_size: "medium",
    subtitle_position: "bottom",
    subtitle_color: "white",
  });

  return (
    <div className="space-y-6">
      {/* プレビュー */}
      <div className="flex justify-center">
        <video
          src={previewUrl}
          controls
          className="rounded-xl max-h-[400px]"
        />
      </div>

      <div className="text-center text-gray-400">
        動画の長さ: {duration.toFixed(1)}秒
      </div>

      {/* 設定 */}
      <div className="bg-gray-800 rounded-xl p-6 space-y-5">
        <h3 className="text-lg font-semibold">処理設定</h3>

        {/* 無音閾値 */}
        <div>
          <label className="block text-sm text-gray-300 mb-1">
            無音の閾値: {settings.silence_threshold}dB
          </label>
          <input
            type="range"
            min={-50}
            max={-10}
            step={1}
            value={settings.silence_threshold}
            onChange={(e) =>
              setSettings((s) => ({ ...s, silence_threshold: Number(e.target.value) }))
            }
            className="w-full"
          />
          <div className="flex justify-between text-xs text-gray-500">
            <span>敏感（-50dB）</span>
            <span>鈍感（-10dB）</span>
          </div>
        </div>

        {/* 最小無音長 */}
        <div>
          <label className="block text-sm text-gray-300 mb-1">
            最小無音長: {settings.min_silence_duration}秒
          </label>
          <input
            type="range"
            min={0.1}
            max={3.0}
            step={0.1}
            value={settings.min_silence_duration}
            onChange={(e) =>
              setSettings((s) => ({ ...s, min_silence_duration: Number(e.target.value) }))
            }
            className="w-full"
          />
          <div className="flex justify-between text-xs text-gray-500">
            <span>短い無音も削除</span>
            <span>長い無音のみ削除</span>
          </div>
        </div>

        {/* 字幕トグル */}
        <div className="flex items-center justify-between">
          <span className="text-sm text-gray-300">AI字幕を追加</span>
          <button
            onClick={() =>
              setSettings((s) => ({ ...s, enable_subtitles: !s.enable_subtitles }))
            }
            className={`
              relative w-12 h-6 rounded-full transition-colors
              ${settings.enable_subtitles ? "bg-blue-500" : "bg-gray-600"}
            `}
          >
            <span
              className={`
                absolute top-0.5 left-0.5 w-5 h-5 bg-white rounded-full transition-transform
                ${settings.enable_subtitles ? "translate-x-6" : ""}
              `}
            />
          </button>
        </div>

        {/* 字幕オプション */}
        {settings.enable_subtitles && (
          <div className="space-y-3 pl-4 border-l-2 border-blue-500/30">
            <div>
              <label className="block text-sm text-gray-400 mb-1">フォントサイズ</label>
              <div className="flex gap-2">
                {(["small", "medium", "large"] as const).map((size) => (
                  <button
                    key={size}
                    onClick={() => setSettings((s) => ({ ...s, font_size: size }))}
                    className={`px-3 py-1 rounded-lg text-sm ${
                      settings.font_size === size
                        ? "bg-blue-500 text-white"
                        : "bg-gray-700 text-gray-300"
                    }`}
                  >
                    {{ small: "小", medium: "中", large: "大" }[size]}
                  </button>
                ))}
              </div>
            </div>

            <div>
              <label className="block text-sm text-gray-400 mb-1">位置</label>
              <div className="flex gap-2">
                {(["bottom", "center"] as const).map((pos) => (
                  <button
                    key={pos}
                    onClick={() => setSettings((s) => ({ ...s, subtitle_position: pos }))}
                    className={`px-3 py-1 rounded-lg text-sm ${
                      settings.subtitle_position === pos
                        ? "bg-blue-500 text-white"
                        : "bg-gray-700 text-gray-300"
                    }`}
                  >
                    {{ bottom: "下部", center: "中央" }[pos]}
                  </button>
                ))}
              </div>
            </div>

            <div>
              <label className="block text-sm text-gray-400 mb-1">文字色</label>
              <div className="flex gap-2">
                {(["white", "yellow"] as const).map((color) => (
                  <button
                    key={color}
                    onClick={() => setSettings((s) => ({ ...s, subtitle_color: color }))}
                    className={`px-3 py-1 rounded-lg text-sm ${
                      settings.subtitle_color === color
                        ? "bg-blue-500 text-white"
                        : "bg-gray-700 text-gray-300"
                    }`}
                  >
                    {{ white: "白", yellow: "黄色" }[color]}
                  </button>
                ))}
              </div>
            </div>
          </div>
        )}
      </div>

      {/* 処理開始ボタン */}
      <button
        onClick={() => onStart(settings)}
        className="w-full py-3 bg-blue-600 hover:bg-blue-500 rounded-xl text-lg font-semibold transition-colors"
      >
        動画を処理する
      </button>
    </div>
  );
}
