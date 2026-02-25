// frontend/app/page.tsx
"use client";

import { useState, useCallback } from "react";
import VideoUploader from "@/components/VideoUploader";
import ProcessingPanel from "@/components/ProcessingPanel";
import ProgressView from "@/components/ProgressView";
import DownloadPanel from "@/components/DownloadPanel";
import {
  startProcessing,
  subscribeProgress,
  getResult,
  type ProcessSettings,
  type ProgressEvent,
  type JobResult,
} from "@/lib/api";

type Step = "upload" | "settings" | "processing" | "done";

export default function Home() {
  const [step, setStep] = useState<Step>("upload");
  const [jobId, setJobId] = useState("");
  const [duration, setDuration] = useState(0);
  const [previewUrl, setPreviewUrl] = useState("");
  const [progressEvent, setProgressEvent] = useState<ProgressEvent | null>(null);
  const [result, setResult] = useState<JobResult | null>(null);
  const [error, setError] = useState<string | null>(null);

  const handleUploaded = useCallback(
    (id: string, dur: number, url: string) => {
      setJobId(id);
      setDuration(dur);
      setPreviewUrl(url);
      setStep("settings");
    },
    []
  );

  const handleStartProcessing = useCallback(
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

  const handleReset = useCallback(() => {
    setStep("upload");
    setJobId("");
    setDuration(0);
    setPreviewUrl("");
    setProgressEvent(null);
    setResult(null);
    setError(null);
  }, []);

  return (
    <main className="min-h-screen flex flex-col">
      {/* Header */}
      <header className="py-6 text-center border-b border-gray-800">
        <h1 className="text-3xl font-bold">Reel Creator</h1>
        <p className="text-gray-400 mt-1">TikTok/IGリール用動画を簡単作成</p>
      </header>

      {/* Step indicator */}
      <div className="flex justify-center gap-2 py-4">
        {(["upload", "settings", "processing", "done"] as const).map((s, i) => (
          <div key={s} className="flex items-center gap-2">
            <div
              className={`w-8 h-8 rounded-full flex items-center justify-center text-sm font-bold ${
                step === s
                  ? "bg-blue-500 text-white"
                  : i < ["upload", "settings", "processing", "done"].indexOf(step)
                  ? "bg-blue-500/30 text-blue-300"
                  : "bg-gray-700 text-gray-500"
              }`}
            >
              {i + 1}
            </div>
            {i < 3 && <div className="w-8 h-px bg-gray-700" />}
          </div>
        ))}
      </div>

      {/* Content */}
      <div className="flex-1 flex items-start justify-center p-6">
        <div className="w-full max-w-lg">
          {error && (
            <div className="mb-4 p-3 bg-red-500/20 border border-red-500/50 rounded-lg text-red-300 text-sm">
              {error}
            </div>
          )}

          {step === "upload" && <VideoUploader onUploaded={handleUploaded} />}
          {step === "settings" && (
            <ProcessingPanel
              duration={duration}
              previewUrl={previewUrl}
              onStart={handleStartProcessing}
            />
          )}
          {step === "processing" && progressEvent && (
            <ProgressView event={progressEvent} />
          )}
          {step === "done" && result && (
            <DownloadPanel jobId={jobId} result={result} onReset={handleReset} />
          )}
        </div>
      </div>
    </main>
  );
}
