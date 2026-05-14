// frontend/components/ProgressView.tsx
"use client";

import { useEffect, useRef, useState } from "react";
import type { ProgressEvent } from "@/lib/api";

interface Props {
  event: ProgressEvent;
}

const stageIcons: Record<string, string> = {
  audio_extract: "🎵",
  silence_detect: "🔍",
  cut_concat: "✂️",
  transcribe: "💬",
  transcribe_for_cut: "🎤",
  jump_cut: "⚡",
  burn_subtitles: "📝",
  buzz_topics: "🔢",
  buzz_hook: "🎯",
  buzz_cta: "👇",
  buzz_bgm: "🎶",
  done: "✅",
  error: "❌",
  init: "⏳",
};

function formatTime(s: number): string {
  if (!isFinite(s) || s < 0) return "--:--";
  const m = Math.floor(s / 60);
  const sec = Math.floor(s % 60);
  return `${m}:${sec.toString().padStart(2, "0")}`;
}

export default function ProgressView({ event }: Props) {
  const startedAtRef = useRef<number>(Date.now());
  const [now, setNow] = useState(Date.now());

  useEffect(() => {
    const id = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(id);
  }, []);

  const elapsedSec = (now - startedAtRef.current) / 1000;
  const progress = Math.max(1, event.progress);
  const totalEstimateSec = elapsedSec / (progress / 100);
  const remainingSec = totalEstimateSec - elapsedSec;
  const showEta = event.progress >= 5 && event.progress < 100;

  return (
    <div className="text-center space-y-6">
      <div className="text-6xl animate-pulse">
        {stageIcons[event.stage] || "⚙️"}
      </div>

      <div className="text-xl">{event.message}</div>

      <div className="w-full max-w-md mx-auto">
        <div className="bg-gray-700 rounded-full h-3">
          <div
            className="bg-blue-500 h-3 rounded-full transition-all duration-500"
            style={{ width: `${event.progress}%` }}
          />
        </div>
        <div className="text-gray-400 text-sm mt-2">{event.progress}%</div>
      </div>

      <div className="flex justify-center gap-6 text-sm text-gray-400">
        <div>
          <span className="text-gray-500">経過: </span>
          <span className="font-mono">{formatTime(elapsedSec)}</span>
        </div>
        {showEta && (
          <div>
            <span className="text-gray-500">残り: </span>
            <span className="font-mono">約 {formatTime(remainingSec)}</span>
          </div>
        )}
      </div>
    </div>
  );
}
