// frontend/components/ProcessingPanel.tsx
"use client";

import { useState } from "react";
import {
  analyzeVideo,
  gradePreviewUrl,
  type AnalyzeResult,
  type ProcessSettings,
} from "@/lib/api";

interface Props {
  jobId: string;
  duration: number;
  previewUrl: string;
  onStart: (settings: ProcessSettings) => void;
}

type Preset = "custom" | "education" | "entertainment" | "tight" | "news";

const PRESETS: Record<Exclude<Preset, "custom">, Partial<ProcessSettings>> = {
  education: {
    enable_subtitles: true,
    enable_jump_cut: true,
    enable_buzz_mode: true,
    silence_threshold: -30,
    min_silence_duration: 0.3,
    voice_padding: 0.04,
    tempo_max_pause: 0.6,
    tempo_target_pause: 0.3,
    font_size: "medium",
    subtitle_position: "bottom",
    subtitle_color: "white",
    color_grade: "minimal",
    subtitle_motion: "fade",
  },
  entertainment: {
    enable_subtitles: true,
    enable_jump_cut: true,
    enable_buzz_mode: true,
    silence_threshold: -25,
    min_silence_duration: 0.3,
    voice_padding: 0.04,
    tempo_max_pause: 0.5,
    tempo_target_pause: 0.25,
    font_size: "large",
    subtitle_position: "bottom",
    subtitle_color: "yellow",
    color_grade: "pop",
    subtitle_motion: "pop",
  },
  tight: {
    enable_subtitles: true,
    enable_jump_cut: true,
    enable_buzz_mode: true,
    silence_threshold: -25,
    min_silence_duration: 0.2,
    voice_padding: 0.05,
    tempo_max_pause: 0.35,
    tempo_target_pause: 0.15,
    word_gap_max: 0.2,
    word_gap_target: 0.08,
    max_word_duration: 0.8, // 攻めに: 0.8秒以上の word は中身に沈黙ありとみなす
    micro_silence_min_duration: 0.1,
    subtitle_max_chars: 10,
    skip_preview: true, // 量産用: 字幕プレビューを飛ばす
    font_size: "large",
    subtitle_position: "bottom",
    subtitle_color: "yellow",
    color_grade: "pop",
    subtitle_motion: "pop",
  },
  news: {
    enable_subtitles: true,
    enable_jump_cut: false,
    enable_buzz_mode: false,
    silence_threshold: -35,
    min_silence_duration: 0.7,
    voice_padding: 0.08,
    tempo_max_pause: 0.8,
    tempo_target_pause: 0.4,
    font_size: "medium",
    subtitle_position: "bottom",
    subtitle_color: "white",
    color_grade: "none",
    subtitle_motion: "karaoke",
  },
};

export default function ProcessingPanel({
  jobId,
  duration,
  previewUrl,
  onStart,
}: Props) {
  // デフォルトで「⚡ぎっしり」 プリセットを適用 (プリセット未選択で処理されるバグ回避)
  const [settings, setSettings] = useState<ProcessSettings>({
    silence_threshold: -30,
    min_silence_duration: 0.3,
    voice_padding: 0.04,
    tempo_max_pause: 0.6,
    tempo_target_pause: 0.3,
    word_gap_max: 0.25,
    word_gap_target: 0.1,
    max_word_duration: 1.0,
    micro_silence_min_duration: 0.1,
    subtitle_max_chars: 12,
    enable_subtitles: false,
    enable_jump_cut: false,
    enable_buzz_mode: false,
    editor_mode: "rule_based",
    director_target_min: 50.0,
    director_target_max: 80.0,
    transcript_prompt:
      "整体師が血流・筋肉・老廃物・不定愁訴・健康・整骨院・整体・姿勢・自律神経について解説する動画です。",
    font_size: "medium",
    subtitle_position: "bottom",
    subtitle_color: "white",
    color_grade: "none",
    subtitle_motion: "pop",
    enable_auto_reframe: false,
    // ⚡ぎっしりプリセットの設定をマージ (初期適用)
    ...PRESETS.tight,
  });
  const [preset, setPreset] = useState<Preset>("tight");
  const [showAdvanced, setShowAdvanced] = useState(false);

  const applyPreset = (p: Exclude<Preset, "custom">) => {
    setPreset(p);
    setSettings((s) => ({ ...s, ...PRESETS[p] }));
  };

  const [analyzing, setAnalyzing] = useState(false);
  const [analysis, setAnalysis] = useState<AnalyzeResult | null>(null);
  const [analyzeError, setAnalyzeError] = useState("");

  const handleAuto = async () => {
    setAnalyzing(true);
    setAnalyzeError("");
    try {
      const r = await analyzeVideo(jobId);
      setAnalysis(r);
      setPreset("custom");
      setSettings((s) => ({ ...s, ...r.settings }));
    } catch (e) {
      setAnalyzeError(e instanceof Error ? e.message : "解析に失敗しました");
    } finally {
      setAnalyzing(false);
    }
  };

  return (
    <div className="space-y-6">
      {/* プレビュー */}
      <div className="flex justify-center">
        <video src={previewUrl} controls className="rounded-xl max-h-[400px]" />
      </div>

      <div className="text-center text-gray-400">
        動画の長さ: {duration.toFixed(1)}秒
      </div>

      {/* 設定 */}
      <div className="bg-gray-800 rounded-xl p-6 space-y-5">
        <h3 className="text-lg font-semibold">処理設定</h3>

        {/* ✨ おまかせ（自動判定） */}
        <div className="rounded-lg border border-amber-400/40 bg-amber-500/10 p-3">
          <div className="flex items-center justify-between gap-3">
            <div>
              <div className="text-sm font-semibold text-amber-200">
                ✨ おまかせ（自動判定）
              </div>
              <div className="text-xs text-gray-400 mt-0.5">
                動画の中身を解析して最適な設定を自動でセット
              </div>
            </div>
            <button
              onClick={handleAuto}
              disabled={analyzing || !jobId}
              className="shrink-0 px-4 py-2 rounded-lg text-sm font-medium bg-amber-500 text-white hover:bg-amber-400 disabled:opacity-50 transition-colors"
            >
              {analyzing ? "解析中..." : "おまかせ設定"}
            </button>
          </div>
          {analysis && (
            <div className="mt-2 text-xs text-amber-100 bg-black/20 rounded p-2">
              <span className="font-semibold">判定: {analysis.label}</span>
              <span className="text-gray-300">
                （発話 {Math.round(analysis.speech_ratio * 100)}% /{" "}
                {analysis.orientation === "vertical" ? "縦" : "横"}）
              </span>
              <div className="text-gray-300 mt-1">{analysis.reason}</div>
            </div>
          )}
          {analyzeError && (
            <div className="mt-2 text-xs text-red-300">{analyzeError}</div>
          )}
        </div>

        {/* プリセット */}
        <div>
          <label className="block text-sm text-gray-300 mb-2">プリセット</label>
          <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
            {(
              [
                ["education", "📚 教育系"],
                ["entertainment", "🎬 エンタメ"],
                ["tight", "⚡ ぎっしり"],
                ["news", "📰 ニュース"],
              ] as const
            ).map(([key, label]) => (
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

        {/* 編集方針: rule_based (削るだけ) vs director (LLM がストーリー再構成) */}
        <div>
          <label className="block text-sm text-gray-300 mb-2">編集方針</label>
          <div className="grid grid-cols-1 gap-2 sm:grid-cols-2">
            <button
              onClick={() =>
                setSettings((s) => ({ ...s, editor_mode: "rule_based" }))
              }
              className={`text-left rounded-lg p-3 border transition-colors ${
                settings.editor_mode === "rule_based"
                  ? "bg-purple-500/20 border-purple-400 text-white"
                  : "bg-gray-700 border-gray-600 text-gray-300 hover:bg-gray-600"
              }`}
            >
              <div className="font-semibold text-sm">✂️ 標準モード</div>
              <div className="text-xs mt-1 opacity-80">
                不要な間とフィラーを削除して短くする
                <br />
                <span className="text-gray-400">推奨: 台本ありの撮影</span>
              </div>
            </button>
            <button
              onClick={() =>
                setSettings((s) => ({ ...s, editor_mode: "director" }))
              }
              className={`text-left rounded-lg p-3 border transition-colors ${
                settings.editor_mode === "director"
                  ? "bg-amber-500/20 border-amber-400 text-white"
                  : "bg-gray-700 border-gray-600 text-gray-300 hover:bg-gray-600"
              }`}
            >
              <div className="font-semibold text-sm">
                🎬 AI 監督モード{" "}
                <span className="text-xs px-1.5 py-0.5 bg-amber-500/30 rounded ml-1">
                  Beta
                </span>
              </div>
              <div className="text-xs mt-1 opacity-80">
                LLM がストーリーを設計して残す区間を決定
                <br />
                <span className="text-gray-400">
                  推奨: 雑撮り・言い直し多い動画
                </span>
              </div>
            </button>
          </div>
          {settings.editor_mode === "director" && (
            <p className="text-xs text-amber-300 mt-2">
              ※ Beta: LLM 失敗時は標準モードに自動フォールバックします。
              処理時間 +5-15 秒、 LLM コスト +$0.05/本程度
            </p>
          )}
        </div>

        {/* 現在の処理モード を明示 */}
        <div
          className={`rounded-lg p-3 border ${
            settings.skip_preview
              ? "bg-pink-500/10 border-pink-500/40"
              : "bg-blue-500/10 border-blue-500/40"
          }`}
        >
          <div className="flex items-center justify-between gap-2">
            <div className="flex-1">
              <div className="text-sm font-semibold">
                {settings.skip_preview ? (
                  <span className="text-pink-300">
                    ⚡ 量産モード (字幕プレビューを飛ばす)
                  </span>
                ) : (
                  <span className="text-blue-300">
                    📝 編集モード (字幕プレビューあり)
                  </span>
                )}
              </div>
              <p className="text-xs text-gray-400 mt-1">
                {settings.skip_preview
                  ? "速い処理 (~4分)。 ただし誤認識を手動修正できないので、 投稿前に動画再生でチェックしてください。"
                  : "推奨。 字幕プレビューで「⚠ 要確認」 の赤字 Dialogue を 5-10 秒チェック・修正できます (合計 ~6分)。"}
              </p>
            </div>
            <button
              onClick={() =>
                setSettings((s) => ({ ...s, skip_preview: !s.skip_preview }))
              }
              className={`shrink-0 px-3 py-1.5 rounded-lg text-xs font-medium transition-colors ${
                settings.skip_preview
                  ? "bg-blue-500 hover:bg-blue-400 text-white"
                  : "bg-pink-500 hover:bg-pink-400 text-white"
              }`}
              title="モードを切替"
            >
              {settings.skip_preview ? "編集モードに" : "量産モードに"}
            </button>
          </div>
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
                  setSettings((s) => ({
                    ...s,
                    silence_threshold: Number(e.target.value),
                  }))
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
                  setSettings((s) => ({
                    ...s,
                    min_silence_duration: Number(e.target.value),
                  }))
                }
                className="w-full"
              />
              <div className="flex justify-between text-xs text-gray-500">
                <span>短い無音も削除</span>
                <span>長い無音のみ削除</span>
              </div>
            </div>

            {/* 微小無音検出 (word 内部の「ちょっとした間」) */}
            <div>
              <label className="block text-sm text-gray-300 mb-1">
                微小無音の検出閾値:{" "}
                {(settings.micro_silence_min_duration ?? 0.1).toFixed(2)}秒
              </label>
              <input
                type="range"
                min={0}
                max={0.3}
                step={0.01}
                value={settings.micro_silence_min_duration ?? 0.1}
                onChange={(e) =>
                  setSettings((s) => ({
                    ...s,
                    micro_silence_min_duration: Number(e.target.value),
                  }))
                }
                className="w-full"
              />
              <div className="flex justify-between text-xs text-gray-500">
                <span>OFF(0)</span>
                <span>緩(0.30秒)</span>
              </div>
              <p className="text-xs text-gray-500 mt-1">
                ReazonSpeech が拾わない word
                内部の短い無音(整骨院の前のちょっとした間など)も削除します
              </p>
            </div>

            {/* 前後padding（有音区間の前後保護） */}
            <div>
              <label className="block text-sm text-gray-300 mb-1">
                前後の余白: {(settings.voice_padding ?? 0.04).toFixed(2)}秒
              </label>
              <input
                type="range"
                min={0}
                max={0.2}
                step={0.01}
                value={settings.voice_padding ?? 0.04}
                onChange={(e) =>
                  setSettings((s) => ({
                    ...s,
                    voice_padding: Number(e.target.value),
                  }))
                }
                className="w-full"
              />
              <div className="flex justify-between text-xs text-gray-500">
                <span>ぎっしり（0）</span>
                <span>余裕（0.2秒）</span>
              </div>
            </div>

            {/* 発話間ギャップ（鼻啜り音・微妙な間） */}
            <div>
              <label className="block text-sm text-gray-300 mb-1">
                発話間ギャップ: 最大{" "}
                {(settings.word_gap_max ?? 0.25).toFixed(2)}秒 →{" "}
                {(settings.word_gap_target ?? 0.1).toFixed(2)}秒に圧縮
              </label>
              <div className="grid grid-cols-2 gap-2">
                <input
                  type="range"
                  min={0.1}
                  max={0.8}
                  step={0.05}
                  value={settings.word_gap_max ?? 0.25}
                  onChange={(e) =>
                    setSettings((s) => ({
                      ...s,
                      word_gap_max: Number(e.target.value),
                    }))
                  }
                  className="w-full"
                  aria-label="word_gap_max"
                />
                <input
                  type="range"
                  min={0.05}
                  max={0.3}
                  step={0.01}
                  value={settings.word_gap_target ?? 0.1}
                  onChange={(e) =>
                    setSettings((s) => ({
                      ...s,
                      word_gap_target: Number(e.target.value),
                    }))
                  }
                  className="w-full"
                  aria-label="word_gap_target"
                />
              </div>
              <div className="flex justify-between text-xs text-gray-500">
                <span>検出閾値（左）</span>
                <span>残すギャップ（右）</span>
              </div>
              <p className="text-xs text-gray-500 mt-1">
                鼻啜り音・息継ぎ・考える間を句読点不問で圧縮（AIジャンプカット
                ON 時のみ）
              </p>
            </div>

            {/* 句読点後の間（テンポカット） */}
            <div>
              <label className="block text-sm text-gray-300 mb-1">
                句読点後の間: 最大{" "}
                {(settings.tempo_max_pause ?? 0.6).toFixed(2)}秒 →{" "}
                {(settings.tempo_target_pause ?? 0.3).toFixed(2)}秒に短縮
              </label>
              <div className="grid grid-cols-2 gap-2">
                <input
                  type="range"
                  min={0.2}
                  max={1.5}
                  step={0.05}
                  value={settings.tempo_max_pause ?? 0.6}
                  onChange={(e) =>
                    setSettings((s) => ({
                      ...s,
                      tempo_max_pause: Number(e.target.value),
                    }))
                  }
                  className="w-full"
                  aria-label="tempo_max_pause"
                />
                <input
                  type="range"
                  min={0.1}
                  max={0.8}
                  step={0.05}
                  value={settings.tempo_target_pause ?? 0.3}
                  onChange={(e) =>
                    setSettings((s) => ({
                      ...s,
                      tempo_target_pause: Number(e.target.value),
                    }))
                  }
                  className="w-full"
                  aria-label="tempo_target_pause"
                />
              </div>
              <div className="flex justify-between text-xs text-gray-500">
                <span>検出閾値（左）</span>
                <span>残す間（右）</span>
              </div>
              <p className="text-xs text-gray-500 mt-1">
                AIジャンプカット ON 時のみ有効
              </p>
            </div>

            {/* 字幕の最大文字数 */}
            <div>
              <label className="block text-sm text-gray-300 mb-1">
                1字幕の最大文字数: {settings.subtitle_max_chars ?? 12}文字
              </label>
              <input
                type="range"
                min={8}
                max={24}
                step={1}
                value={settings.subtitle_max_chars ?? 12}
                onChange={(e) =>
                  setSettings((s) => ({
                    ...s,
                    subtitle_max_chars: Number(e.target.value),
                  }))
                }
                className="w-full"
              />
              <div className="flex justify-between text-xs text-gray-500">
                <span>短く読みやすい（8）</span>
                <span>1行に多く（24）</span>
              </div>
              <p className="text-xs text-gray-500 mt-1">
                リールは 10〜12 文字が読みやすい目安
              </p>
            </div>

            {/* AIジャンプカットトグル */}
            <div>
              <div className="flex items-center justify-between">
                <span className="text-sm text-gray-300">AIジャンプカット</span>
                <button
                  onClick={() =>
                    setSettings((s) => ({
                      ...s,
                      enable_jump_cut: !s.enable_jump_cut,
                    }))
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
                    setSettings((s) => ({
                      ...s,
                      transcript_prompt: e.target.value,
                    }))
                  }
                  placeholder="例: 健康・筋肉・血流について解説する動画"
                  className="w-full px-3 py-2 bg-gray-700 rounded-lg text-sm text-white placeholder-gray-500"
                />
                <p className="text-xs text-gray-500 mt-1">
                  文字起こしの精度向上に使われます（同音異義語の判別など）
                </p>
              </div>
            )}

            {/* カラーグレード（テイスト別の色味・常時適用） */}
            <div>
              <label className="block text-sm text-gray-300 mb-2">
                🎞️ カラーグレード（色味）
              </label>
              <div className="grid grid-cols-3 gap-2">
                {(
                  [
                    ["none", "なし"],
                    ["minimal", "🤍 ミニマル"],
                    ["cinematic", "🎬 シネマ"],
                    ["monochrome", "◼️ モノトーン"],
                    ["pop", "🌈 ポップ"],
                  ] as const
                ).map(([key, label]) => {
                  const selected = (settings.color_grade ?? "none") === key;
                  return (
                    <button
                      key={key}
                      onClick={() =>
                        setSettings((s) => ({ ...s, color_grade: key }))
                      }
                      className={`overflow-hidden rounded-lg border-2 transition-colors ${
                        selected
                          ? "border-purple-500"
                          : "border-transparent hover:border-gray-600"
                      }`}
                    >
                      <div className="relative aspect-[9/16] bg-gray-700">
                        {jobId && (
                          // eslint-disable-next-line @next/next/no-img-element
                          <img
                            src={gradePreviewUrl(jobId, key)}
                            alt={label}
                            loading="lazy"
                            className="h-full w-full object-cover"
                            onError={(e) => {
                              (
                                e.currentTarget as HTMLImageElement
                              ).style.visibility = "hidden";
                            }}
                          />
                        )}
                      </div>
                      <div
                        className={`px-1 py-1 text-center text-xs font-medium ${
                          selected
                            ? "bg-purple-500 text-white"
                            : "bg-gray-700 text-gray-300"
                        }`}
                      >
                        {label}
                      </div>
                    </button>
                  );
                })}
              </div>
              <p className="text-xs text-gray-500 mt-1">
                あなたの動画で色味を見比べて選べます（字幕・テロップの色は変わりません）
              </p>
            </div>

            {/* 字幕の動き（キネティック字幕、バズモード時のみ有効） */}
            <div>
              <label className="block text-sm text-gray-300 mb-2">
                ✨ 字幕の動き
              </label>
              <div className="grid grid-cols-3 gap-2">
                {(
                  [
                    ["none", "なし"],
                    ["karaoke", "🎤 カラオケ"],
                    ["fade", "🌫️ フェード"],
                    ["pop", "💥 ポップ"],
                  ] as const
                ).map(([key, label]) => (
                  <button
                    key={key}
                    onClick={() =>
                      setSettings((s) => ({ ...s, subtitle_motion: key }))
                    }
                    className={`px-3 py-2 rounded-lg text-sm font-medium transition-colors ${
                      (settings.subtitle_motion ?? "pop") === key
                        ? "bg-purple-500 text-white"
                        : "bg-gray-700 text-gray-300 hover:bg-gray-600"
                    }`}
                  >
                    {label}
                  </button>
                ))}
              </div>
              <p className="text-xs text-gray-500 mt-1">
                語ごとの動き（フェード=上品 /
                ポップ=元気め）。バズモード時のみ有効
              </p>
            </div>

            {/* トピックテロップのスタイル */}
            <div>
              <label className="block text-sm text-gray-300 mb-2">
                🎨 トピックテロップのスタイル
              </label>
              <div className="grid grid-cols-3 gap-2">
                {(
                  [
                    ["default", "🎬 派手"],
                    ["sleek", "✨ シック"],
                    ["clean", "🩺 クリーン"],
                  ] as const
                ).map(([key, label]) => (
                  <button
                    key={key}
                    onClick={() =>
                      setSettings((s) => ({ ...s, topic_style: key }))
                    }
                    className={`px-3 py-2 rounded-lg text-sm font-medium transition-colors ${
                      (settings.topic_style ?? "default") === key
                        ? "bg-purple-500 text-white"
                        : "bg-gray-700 text-gray-300 hover:bg-gray-600"
                    }`}
                  >
                    {label}
                  </button>
                ))}
              </div>
              <p className="text-xs text-gray-500 mt-1">
                右上の番号バッジ + テーマラベルの色味（バズモード時のみ表示）
              </p>
            </div>

            {/* 効果音 */}
            <div className="flex items-center justify-between">
              <span className="text-sm text-gray-300">
                🔊 効果音(カット境界)
              </span>
              <button
                onClick={() =>
                  setSettings((s) => ({ ...s, enable_sfx: !s.enable_sfx }))
                }
                className={`relative w-12 h-6 rounded-full transition-colors ${
                  settings.enable_sfx ? "bg-pink-500" : "bg-gray-600"
                }`}
              >
                <span
                  className={`absolute top-0.5 left-0.5 w-5 h-5 bg-white rounded-full transition-transform ${
                    settings.enable_sfx ? "translate-x-6" : ""
                  }`}
                />
              </button>
            </div>
            <p className="text-xs text-gray-500 -mt-3">
              backend/app/data/sfx/cut.mp3 を配置すると鳴ります
            </p>

            {/* オートリフレーム（被写体追従） */}
            <div className="flex items-center justify-between">
              <span className="text-sm text-gray-300">
                🎥 オートリフレーム(被写体追従)
              </span>
              <button
                onClick={() =>
                  setSettings((s) => ({
                    ...s,
                    enable_auto_reframe: !s.enable_auto_reframe,
                  }))
                }
                className={`relative w-12 h-6 rounded-full transition-colors ${
                  settings.enable_auto_reframe ? "bg-pink-500" : "bg-gray-600"
                }`}
              >
                <span
                  className={`absolute top-0.5 left-0.5 w-5 h-5 bg-white rounded-full transition-transform ${
                    settings.enable_auto_reframe ? "translate-x-6" : ""
                  }`}
                />
              </button>
            </div>
            <p className="text-xs text-gray-500 -mt-3">
              横動画でも被写体を中心に保って縦リール化。処理時間が少し伸びます
            </p>

            {/* バズモード */}
            <div>
              <div className="flex items-center justify-between">
                <span className="text-sm text-gray-300">🔥 バズモード</span>
                <button
                  onClick={() =>
                    setSettings((s) => ({
                      ...s,
                      enable_buzz_mode: !s.enable_buzz_mode,
                    }))
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
                  setSettings((s) => ({
                    ...s,
                    enable_subtitles: !s.enable_subtitles,
                  }))
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
                  <label className="block text-sm text-gray-400 mb-1">
                    フォントサイズ
                  </label>
                  <div className="flex gap-2">
                    {(["small", "medium", "large"] as const).map((size) => (
                      <button
                        key={size}
                        onClick={() =>
                          setSettings((s) => ({ ...s, font_size: size }))
                        }
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
                  <label className="block text-sm text-gray-400 mb-1">
                    位置
                  </label>
                  <div className="flex gap-2">
                    {(["bottom", "center"] as const).map((pos) => (
                      <button
                        key={pos}
                        onClick={() =>
                          setSettings((s) => ({ ...s, subtitle_position: pos }))
                        }
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
                  <label className="block text-sm text-gray-400 mb-1">
                    文字色
                  </label>
                  <div className="flex gap-2">
                    {(["white", "yellow"] as const).map((color) => (
                      <button
                        key={color}
                        onClick={() =>
                          setSettings((s) => ({ ...s, subtitle_color: color }))
                        }
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
        {settings.enable_subtitles
          ? "字幕プレビューに進む →"
          : "動画を処理する →"}
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
