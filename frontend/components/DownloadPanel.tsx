// frontend/components/DownloadPanel.tsx
"use client";

import { useState } from "react";
import type { JobResult, CaptionsResult, BuzzScoreResult } from "@/lib/api";
import {
  getDownloadUrl,
  generateCaptions,
  writeCaptionsToSheet,
  getBuzzScore,
} from "@/lib/api";

interface Props {
  jobId: string;
  result: JobResult;
  onReset: () => void;
}

function CopyableTextArea({ label, text }: { label: string; text: string }) {
  const [copied, setCopied] = useState(false);
  const handleCopy = async () => {
    try {
      await navigator.clipboard.writeText(text);
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    } catch {}
  };
  return (
    <div className="bg-gray-700/40 rounded-lg p-3">
      <div className="flex items-center justify-between mb-1">
        <span className="text-xs text-gray-400 font-medium">{label}</span>
        <button
          onClick={handleCopy}
          className="text-xs px-2 py-0.5 bg-gray-600 hover:bg-gray-500 rounded transition-colors"
        >
          {copied ? "✓ コピー" : "📋 コピー"}
        </button>
      </div>
      <p className="text-sm text-gray-200 whitespace-pre-wrap break-words">
        {text}
      </p>
    </div>
  );
}

function ScoreBar({ label, value }: { label: string; value: number }) {
  const pct = value * 10;
  const color =
    value >= 8
      ? "bg-green-400"
      : value >= 6
        ? "bg-blue-400"
        : value >= 4
          ? "bg-yellow-400"
          : "bg-red-400";
  return (
    <div>
      <div className="flex justify-between text-xs mb-1">
        <span className="text-gray-300">{label}</span>
        <span className="text-gray-400 font-mono">{value}</span>
      </div>
      <div className="bg-gray-700/60 h-1.5 rounded overflow-hidden">
        <div
          className={`h-full ${color} transition-all`}
          style={{ width: `${pct}%` }}
        />
      </div>
    </div>
  );
}

export default function DownloadPanel({ jobId, result, onReset }: Props) {
  const [captions, setCaptions] = useState<CaptionsResult | null>(null);
  const [captionsLoading, setCaptionsLoading] = useState(false);
  const [captionsError, setCaptionsError] = useState<string | null>(null);

  const [buzz, setBuzz] = useState<BuzzScoreResult | null>(null);
  const [buzzLoading, setBuzzLoading] = useState(false);
  const [buzzError, setBuzzError] = useState<string | null>(null);

  const [sheetRow, setSheetRow] = useState<string>("");
  const [sheetWriting, setSheetWriting] = useState(false);
  const [sheetWritten, setSheetWritten] = useState(false);

  const fetchCaptions = async () => {
    setCaptionsLoading(true);
    setCaptionsError(null);
    try {
      const c = await generateCaptions(jobId);
      setCaptions(c);
    } catch (e) {
      setCaptionsError(e instanceof Error ? e.message : "失敗");
    } finally {
      setCaptionsLoading(false);
    }
  };

  const fetchBuzz = async () => {
    setBuzzLoading(true);
    setBuzzError(null);
    try {
      const b = await getBuzzScore(jobId);
      setBuzz(b);
    } catch (e) {
      setBuzzError(e instanceof Error ? e.message : "失敗");
    } finally {
      setBuzzLoading(false);
    }
  };

  const writeToSheet = async () => {
    if (!captions) return;
    const row = parseInt(sheetRow, 10);
    if (!row || row < 2) {
      setCaptionsError(
        "シート行番号を入力してください（ヘッダーは1なので2以上）",
      );
      return;
    }
    setSheetWriting(true);
    setCaptionsError(null);
    try {
      await writeCaptionsToSheet(jobId, {
        sheet_row: row,
        ig_caption: captions.instagram_caption,
        tiktok_caption: captions.tiktok_caption,
        hashtags: captions.hashtags,
      });
      setSheetWritten(true);
      setTimeout(() => setSheetWritten(false), 2500);
    } catch (e) {
      setCaptionsError(e instanceof Error ? e.message : "シート書き込み失敗");
    } finally {
      setSheetWriting(false);
    }
  };

  const overallColor = !buzz
    ? ""
    : buzz.overall >= 8
      ? "text-green-400"
      : buzz.overall >= 6
        ? "text-blue-400"
        : buzz.overall >= 4
          ? "text-yellow-400"
          : "text-red-400";

  return (
    <div className="space-y-6">
      <div className="text-center space-y-4">
        <div className="text-6xl">✅</div>
        <h2 className="text-2xl font-bold">処理が完了しました！</h2>
      </div>

      <div className="bg-gradient-to-br from-blue-500/10 to-purple-500/10 border border-blue-500/30 rounded-2xl p-5">
        <div className="grid grid-cols-3 gap-3 text-center">
          <div>
            <div className="text-gray-400 text-xs">元の長さ</div>
            <div className="text-lg font-semibold">
              {result.original_duration.toFixed(1)}s
            </div>
          </div>
          <div>
            <div className="text-gray-400 text-xs">処理後</div>
            <div className="text-lg font-semibold">
              {result.processed_duration.toFixed(1)}s
            </div>
          </div>
          <div>
            <div className="text-gray-400 text-xs">短縮</div>
            <div className="text-lg font-semibold text-blue-300">
              {(
                (result.silence_removed / result.original_duration) *
                100
              ).toFixed(0)}
              %
            </div>
          </div>
        </div>
      </div>

      <video
        src={getDownloadUrl(jobId)}
        controls
        className="rounded-xl max-h-[400px] mx-auto w-full"
      />

      <div className="flex gap-3">
        <a
          href={getDownloadUrl(jobId)}
          download
          className="flex-1 py-3 text-center bg-gradient-to-r from-blue-500 to-purple-600 hover:from-blue-400 hover:to-purple-500 rounded-xl font-semibold shadow-lg shadow-blue-500/30 transition-all"
        >
          ⬇️ ダウンロード
        </a>
        <button
          onClick={onReset}
          className="px-5 py-3 bg-gray-700/60 hover:bg-gray-600 rounded-xl border border-gray-600/50 transition-colors"
        >
          🔁 もう1本
        </button>
      </div>

      {/* バズスコア予測 */}
      <div className="bg-gray-800/40 backdrop-blur rounded-2xl p-5 border border-gray-700/50">
        <div className="flex items-center justify-between mb-3">
          <h3 className="font-semibold flex items-center gap-2">
            <span>🔥</span>バズスコア予測
          </h3>
          {!buzz && !buzzLoading && (
            <button
              onClick={fetchBuzz}
              className="text-xs px-3 py-1.5 bg-orange-500/80 hover:bg-orange-400 rounded-lg font-medium transition-colors"
            >
              評価する
            </button>
          )}
        </div>
        {buzzLoading && (
          <div className="flex items-center gap-2 text-sm text-gray-400">
            <span className="inline-block w-4 h-4 border-2 border-orange-400 border-t-transparent rounded-full animate-spin" />
            LLMで評価中...
          </div>
        )}
        {buzzError && <p className="text-xs text-red-300">{buzzError}</p>}
        {buzz && (
          <div className="space-y-4">
            <div className="text-center">
              <div className={`text-5xl font-bold ${overallColor}`}>
                {buzz.overall.toFixed(1)}
                <span className="text-gray-500 text-2xl"> / 10</span>
              </div>
            </div>
            <div className="grid grid-cols-2 gap-x-4 gap-y-2">
              <ScoreBar label="フック" value={buzz.scores.hook} />
              <ScoreBar label="テーマ明確さ" value={buzz.scores.clarity} />
              <ScoreBar label="情報密度" value={buzz.scores.density} />
              <ScoreBar label="構造" value={buzz.scores.structure} />
              <ScoreBar label="CTA" value={buzz.scores.cta} />
              <ScoreBar label="テンポ" value={buzz.scores.pace} />
              <ScoreBar label="検索性" value={buzz.scores.searchability} />
              <ScoreBar label="長さ適合" value={buzz.scores.length_fit} />
            </div>
            {buzz.strengths.length > 0 && (
              <div className="text-sm">
                <div className="text-green-400 font-medium mb-1">✅ 強み</div>
                <ul className="text-gray-300 space-y-1 pl-4 list-disc">
                  {buzz.strengths.map((s, i) => (
                    <li key={i}>{s}</li>
                  ))}
                </ul>
              </div>
            )}
            {buzz.weaknesses.length > 0 && (
              <div className="text-sm">
                <div className="text-yellow-400 font-medium mb-1">
                  ⚠️ 改善ポイント
                </div>
                <ul className="text-gray-300 space-y-1 pl-4 list-disc">
                  {buzz.weaknesses.map((s, i) => (
                    <li key={i}>{s}</li>
                  ))}
                </ul>
              </div>
            )}
            {buzz.suggestions.length > 0 && (
              <div className="text-sm">
                <div className="text-blue-400 font-medium mb-1">
                  🎯 次のアクション
                </div>
                <ol className="text-gray-300 space-y-1 pl-4 list-decimal">
                  {buzz.suggestions.map((s, i) => (
                    <li key={i}>{s}</li>
                  ))}
                </ol>
              </div>
            )}
          </div>
        )}
      </div>

      {/* AIタイトル・ハッシュタグ */}
      <div className="bg-gray-800/40 backdrop-blur rounded-2xl p-5 border border-gray-700/50">
        <div className="flex items-center justify-between mb-3">
          <h3 className="font-semibold flex items-center gap-2">
            <span>📝</span>SNSキャプション・ハッシュタグ
          </h3>
          {!captions && !captionsLoading && (
            <button
              onClick={fetchCaptions}
              className="text-xs px-3 py-1.5 bg-blue-500/80 hover:bg-blue-400 rounded-lg font-medium transition-colors"
            >
              生成する
            </button>
          )}
        </div>
        {captionsLoading && (
          <div className="flex items-center gap-2 text-sm text-gray-400">
            <span className="inline-block w-4 h-4 border-2 border-blue-400 border-t-transparent rounded-full animate-spin" />
            LLMで生成中...
          </div>
        )}
        {captionsError && (
          <p className="text-xs text-red-300 mb-2">{captionsError}</p>
        )}
        {captions && (
          <div className="space-y-3">
            <CopyableTextArea
              label="🎵 TikTok キャプション"
              text={captions.tiktok_caption}
            />
            <CopyableTextArea
              label="📷 Instagram キャプション"
              text={captions.instagram_caption}
            />
            <CopyableTextArea
              label="#️⃣ ハッシュタグ"
              text={captions.hashtags}
            />

            <div className="border-t border-gray-700 pt-3 space-y-2">
              <p className="text-xs text-gray-400">
                Google Sheets の指定行に書き込み:
              </p>
              <div className="flex gap-2">
                <input
                  type="number"
                  min={2}
                  value={sheetRow}
                  onChange={(e) => setSheetRow(e.target.value)}
                  placeholder="行番号 (2〜)"
                  className="flex-1 px-3 py-2 bg-gray-700 rounded-lg text-sm outline-none focus:ring-2 ring-blue-400/50"
                />
                <button
                  onClick={writeToSheet}
                  disabled={sheetWriting || !sheetRow}
                  className="px-4 py-2 bg-green-500/80 hover:bg-green-400 disabled:bg-gray-600 disabled:cursor-not-allowed rounded-lg text-sm font-medium transition-colors"
                >
                  {sheetWritten
                    ? "✓ 書き込み済"
                    : sheetWriting
                      ? "書込中..."
                      : "Sheets に追加"}
                </button>
              </div>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
