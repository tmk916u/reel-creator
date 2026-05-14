// frontend/components/ProcessingPanel.tsx
"use client";

import { useState } from "react";
import type { ProcessSettings } from "@/lib/api";

interface Props {
  duration: number;
  previewUrl: string;
  onStart: (settings: ProcessSettings) => void;
}

type Preset = "custom" | "education" | "entertainment" | "news";

const PRESETS: Record<Exclude<Preset, "custom">, Partial<ProcessSettings>> = {
  education: {
    enable_subtitles: true,
    enable_jump_cut: true,
    enable_buzz_mode: true,
    silence_threshold: -30,
    min_silence_duration: 0.5,
    font_size: "medium",
    subtitle_position: "bottom",
    subtitle_color: "white",
  },
  entertainment: {
    enable_subtitles: true,
    enable_jump_cut: true,
    enable_buzz_mode: true,
    silence_threshold: -25,
    min_silence_duration: 0.3,
    font_size: "large",
    subtitle_position: "bottom",
    subtitle_color: "yellow",
  },
  news: {
    enable_subtitles: true,
    enable_jump_cut: false,
    enable_buzz_mode: false,
    silence_threshold: -35,
    min_silence_duration: 0.7,
    font_size: "medium",
    subtitle_position: "bottom",
    subtitle_color: "white",
  },
};

export default function ProcessingPanel({ duration, previewUrl, onStart }: Props) {
  const [settings, setSettings] = useState<ProcessSettings>({
    silence_threshold: -30,
    min_silence_duration: 0.5,
    enable_subtitles: false,
    enable_jump_cut: false,
    enable_buzz_mode: false,
    transcript_prompt: "",
    font_size: "medium",
    subtitle_position: "bottom",
    subtitle_color: "white",
  });
  const [preset, setPreset] = useState<Preset>("custom");
  const [showAdvanced, setShowAdvanced] = useState(false);

  const applyPreset = (p: Exclude<Preset, "custom">) => {
    setPreset(p);
    setSettings((s) => ({ ...s, ...PRESETS[p] }));
  };

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

        {/* プリセット */}
        <div>
          <label className="block text-sm text-gray-300 mb-2">プリセット</label>
          <div className="grid grid-cols-3 gap-2">
            {([
              ["education", "📚 教育系"],
              ["entertainment", "🎬 エンタメ"],
              ["news", "📰 ニュース"],
            ] as const).map(([key, label]) => (
              <button
                key={key}
                onClick={() => applyPreset(key)}
                className={`px-3 py-2 rounded-lg text-sm font-medium transition-colors ${
                  preset === key
                    ? "bg-purple-500 text-white"
                    : "bg-gray-700 text-gray-300 hover:bg-gray-600"
                }`}
              >
                {label}
              </button>
            ))}
          </div>
          <p className="text-xs text-gray-500 mt-1">
            ボタン1つで字幕・カット・バズモードがおすすめ設定になります
          </p>
        </div>

        <button
          onClick={() => setShowAdvanced((v) => !v)}
          className="text-xs text-gray-400 hover:text-gray-200 underline"
        >
          {showAdvanced ? "▲ 詳細設定を閉じる" : "▼ 詳細設定を開く"}
        </button>

        {showAdvanced && (
          <>

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

        {/* AIジャンプカットトグル */}
        <div>
          <div className="flex items-center justify-between">
            <span className="text-sm text-gray-300">AIジャンプカット</span>
            <button
              onClick={() =>
                setSettings((s) => ({ ...s, enable_jump_cut: !s.enable_jump_cut }))
              }
              className={`
                relative w-12 h-6 rounded-full transition-colors
                ${settings.enable_jump_cut ? "bg-purple-500" : "bg-gray-600"}
              `}
            >
              <span
                className={`
                  absolute top-0.5 left-0.5 w-5 h-5 bg-white rounded-full transition-transform
                  ${settings.enable_jump_cut ? "translate-x-6" : ""}
                `}
              />
            </button>
          </div>
          <p className="text-xs text-gray-500 mt-1">
            フィラー・言い直し・長い間を自動で削減します（LLM API使用）
          </p>
        </div>

        {/* 動画テーマ（Whisper initial_prompt） */}
        {(settings.enable_jump_cut || settings.enable_subtitles) && (
          <div>
            <label className="block text-sm text-gray-300 mb-1">
              動画のテーマ・専門用語（任意）
            </label>
            <input
              type="text"
              value={settings.transcript_prompt || ""}
              onChange={(e) =>
                setSettings((s) => ({ ...s, transcript_prompt: e.target.value }))
              }
              placeholder="例: 健康・筋肉・血流について解説する動画"
              className="w-full px-3 py-2 bg-gray-700 rounded-lg text-sm text-white placeholder-gray-500"
            />
            <p className="text-xs text-gray-500 mt-1">
              文字起こしの精度向上に使われます（同音異義語の判別など）
            </p>
          </div>
        )}

        {/* バズモード */}
        <div>
          <div className="flex items-center justify-between">
            <span className="text-sm text-gray-300">🔥 バズモード</span>
            <button
              onClick={() =>
                setSettings((s) => ({ ...s, enable_buzz_mode: !s.enable_buzz_mode }))
              }
              className={`
                relative w-12 h-6 rounded-full transition-colors
                ${settings.enable_buzz_mode ? "bg-pink-500" : "bg-gray-600"}
              `}
            >
              <span
                className={`
                  absolute top-0.5 left-0.5 w-5 h-5 bg-white rounded-full transition-transform
                  ${settings.enable_buzz_mode ? "translate-x-6" : ""}
                `}
              />
            </button>
          </div>
          <p className="text-xs text-gray-500 mt-1">
            冒頭フックを自動生成して動画の先頭にオーバーレイ表示します（LLM使用）
          </p>
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
          </>
        )}
      </div>

      {/* 処理開始ボタン */}
      <button
        onClick={() => onStart(settings)}
        className="w-full py-3.5 bg-gradient-to-r from-blue-500 to-purple-600 hover:from-blue-400 hover:to-purple-500 rounded-xl text-base font-semibold transition-all shadow-lg shadow-blue-500/30 hover:shadow-blue-500/50 active:scale-[0.98]"
      >
        {settings.enable_subtitles ? "字幕プレビューに進む →" : "動画を処理する →"}
      </button>

      {settings.enable_subtitles && (
        <p className="text-xs text-gray-500 text-center -mt-2 flex items-center justify-center gap-1">
          <span>💬</span>
          次に字幕の自動生成 → 確認・編集ができます（30〜60秒）
        </p>
      )}
    </div>
  );
}
