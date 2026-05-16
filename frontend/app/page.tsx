// frontend/app/page.tsx
"use client";

import { useState, useCallback } from "react";
import VideoUploader from "@/components/VideoUploader";
import ProcessingPanel from "@/components/ProcessingPanel";
import ProgressView from "@/components/ProgressView";
import DownloadPanel from "@/components/DownloadPanel";
import TranscriptEditor from "@/components/TranscriptEditor";
import {
  startProcessing,
  subscribeProgress,
  getResult,
  transcribePreview,
  type ProcessSettings,
  type ProgressEvent,
  type JobResult,
  type TranscriptSegment,
} from "@/lib/api";

type Step = "upload" | "settings" | "preview" | "processing" | "done";

export default function Home() {
  const [step, setStep] = useState<Step>("upload");
  const [jobId, setJobId] = useState("");
  const [duration, setDuration] = useState(0);
  const [previewUrl, setPreviewUrl] = useState("");
  const [progressEvent, setProgressEvent] = useState<ProgressEvent | null>(null);
  const [result, setResult] = useState<JobResult | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [previewSegments, setPreviewSegments] = useState<TranscriptSegment[]>([]);
  const [pendingSettings, setPendingSettings] = useState<ProcessSettings | null>(null);
  const [loadingPreview, setLoadingPreview] = useState(false);

  const handleUploaded = useCallback(
    (id: string, dur: number, url: string) => {
      setJobId(id);
      setDuration(dur);
      setPreviewUrl(url);
      setStep("settings");
    },
    []
  );

  const runProcessing = useCallback(
    async (settings: ProcessSettings) => {
      setStep("processing");
      setError(null);

      try {
        await startProcessing(jobId, settings);

        subscribeProgress(
          jobId,
          async (event) => {
            setProgressEvent(event);

            if (event.status === "completed") {
              const jobResult = await getResult(jobId);
              setResult(jobResult);
              setStep("done");
            } else if (event.status === "failed") {
              setError(event.message);
              setStep("settings");
            }
          },
          (err) => {
            setError(err.message);
            setStep("settings");
          }
        );
      } catch (e) {
        setError(e instanceof Error ? e.message : "処理の開始に失敗しました");
        setStep("settings");
      }
    },
    [jobId]
  );

  const handleStartProcessing = useCallback(
    async (settings: ProcessSettings) => {
      setError(null);

      // 字幕が無効、または量産モード(skip_preview)なら即実行
      if (!settings.enable_subtitles || settings.skip_preview) {
        await runProcessing(settings);
        return;
      }

      // 字幕プレビュー（編集可能）モード
      setPendingSettings(settings);
      setLoadingPreview(true);
      try {
        const segments = await transcribePreview(
          jobId,
          settings.transcript_prompt || ""
        );
        setPreviewSegments(segments);
        setStep("preview");
      } catch (e) {
        setError(e instanceof Error ? e.message : "字幕プレビューに失敗しました");
      } finally {
        setLoadingPreview(false);
      }
    },
    [jobId, runProcessing]
  );

  const handleConfirmTranscript = useCallback(
    async (edited: TranscriptSegment[]) => {
      if (!pendingSettings) return;
      // 編集がない場合は edited_segments を送らない。
      // edited_segments を送ると backend で edited_provided=True パスに入り、
      // モーション字幕(ASS)が無効化されるため、プレビュー素通しでは未送信にする。
      const hasEdits =
        edited.length !== previewSegments.length ||
        edited.some((s, i) => s.text !== previewSegments[i]?.text);
      const settings: ProcessSettings = {
        ...pendingSettings,
        ...(hasEdits ? { edited_segments: edited } : {}),
      };
      await runProcessing(settings);
    },
    [pendingSettings, previewSegments, runProcessing]
  );

  const handleCancelPreview = useCallback(() => {
    setStep("settings");
    setPreviewSegments([]);
    setPendingSettings(null);
  }, []);

  const handleReset = useCallback(() => {
    setStep("upload");
    setJobId("");
    setDuration(0);
    setPreviewUrl("");
    setProgressEvent(null);
    setResult(null);
    setError(null);
    setPreviewSegments([]);
    setPendingSettings(null);
  }, []);

  const stepOrder: Step[] = ["upload", "settings", "preview", "processing", "done"];
  const stepLabels: Record<Step, { label: string; icon: string }> = {
    upload: { label: "アップロード", icon: "📤" },
    settings: { label: "設定", icon: "⚙️" },
    preview: { label: "字幕確認", icon: "📝" },
    processing: { label: "動画処理", icon: "🎬" },
    done: { label: "完了", icon: "✅" },
  };

  const currentIdx = stepOrder.indexOf(step);
  const progressPct = currentIdx === 0 ? 0 : (currentIdx / (stepOrder.length - 1)) * 100;

  return (
    <main className="min-h-screen flex flex-col bg-gradient-to-b from-gray-950 via-gray-900 to-gray-950">
      {/* Header */}
      <header className="py-8 text-center">
        <div className="inline-flex items-center gap-3">
          <span className="text-4xl">🎬</span>
          <h1 className="text-4xl font-bold bg-gradient-to-r from-blue-400 via-purple-400 to-pink-400 bg-clip-text text-transparent">
            Reel Creator
          </h1>
        </div>
        <p className="text-gray-400 mt-2 text-sm">TikTok / Instagram Reels 用動画を AI で一気に作成</p>
      </header>

      {/* Step indicator with progress line */}
      <div className="relative max-w-2xl mx-auto w-full px-8 pb-6">
        <div className="absolute left-12 right-12 top-[26px] h-0.5 bg-gray-800 rounded">
          <div
            className="h-full bg-gradient-to-r from-blue-500 via-purple-500 to-pink-500 rounded transition-all duration-700"
            style={{ width: `${progressPct}%` }}
          />
        </div>
        <div className="relative flex justify-between">
          {stepOrder.map((s, i) => {
            const isCurrent = step === s;
            const isPast = i < currentIdx;
            return (
              <div key={s} className="flex flex-col items-center gap-1 z-10">
                <div
                  className={`w-13 h-13 min-w-13 min-h-13 rounded-full flex items-center justify-center text-base font-bold transition-all duration-300 ${
                    isCurrent
                      ? "bg-gradient-to-br from-blue-500 to-purple-600 text-white shadow-lg shadow-blue-500/40 scale-110"
                      : isPast
                      ? "bg-blue-500/40 text-blue-100"
                      : "bg-gray-800 text-gray-500 border border-gray-700"
                  }`}
                  style={{ width: 52, height: 52 }}
                >
                  <span className="text-xl">{stepLabels[s].icon}</span>
                </div>
                <div
                  className={`text-[11px] font-medium whitespace-nowrap transition-colors ${
                    isCurrent
                      ? "text-white"
                      : isPast
                      ? "text-blue-300"
                      : "text-gray-500"
                  }`}
                >
                  {stepLabels[s].label}
                </div>
              </div>
            );
          })}
        </div>
      </div>

      {/* Content */}
      <div className="flex-1 flex items-start justify-center px-6 pb-12">
        <div className="w-full max-w-xl">
          {error && (
            <div className="mb-4 p-4 bg-red-500/10 border border-red-500/40 rounded-xl text-red-300 text-sm flex items-start gap-3">
              <span className="text-lg flex-shrink-0">⚠️</span>
              <div className="flex-1">{error}</div>
              <button
                onClick={() => setError(null)}
                className="text-red-300/60 hover:text-red-200 text-lg leading-none"
              >
                ×
              </button>
            </div>
          )}

          {loadingPreview && (
            <div className="mb-4 p-4 bg-blue-500/10 border border-blue-500/30 rounded-xl text-blue-200 text-sm flex items-center gap-3">
              <span className="inline-block w-4 h-4 border-2 border-blue-400 border-t-transparent rounded-full animate-spin" />
              <span>字幕プレビューを生成中... 30〜60秒かかります</span>
            </div>
          )}

          <div className="transition-opacity duration-300" key={step}>
          {step === "upload" && <VideoUploader onUploaded={handleUploaded} />}
          {step === "settings" && (
            <ProcessingPanel
              duration={duration}
              previewUrl={previewUrl}
              onStart={handleStartProcessing}
            />
          )}
          {step === "preview" && (
            <TranscriptEditor
              initialSegments={previewSegments}
              onConfirm={handleConfirmTranscript}
              onCancel={handleCancelPreview}
            />
          )}
          {step === "processing" && !progressEvent && (
            <div className="bg-gray-800/60 backdrop-blur rounded-2xl p-12 text-center border border-gray-700">
              <div className="inline-block w-10 h-10 border-4 border-blue-500 border-t-transparent rounded-full animate-spin mb-4" />
              <div className="text-gray-300">処理を開始しています...</div>
            </div>
          )}
          {step === "processing" && progressEvent && (
            <ProgressView event={progressEvent} />
          )}
          {step === "done" && result && (
            <DownloadPanel jobId={jobId} result={result} onReset={handleReset} />
          )}
          </div>
        </div>
      </div>
    </main>
  );
}
