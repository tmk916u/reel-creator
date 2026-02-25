// frontend/components/ProgressView.tsx
"use client";

import type { ProgressEvent } from "@/lib/api";

interface Props {
  event: ProgressEvent;
}

const stageIcons: Record<string, string> = {
  audio_extract: "🎵",
  silence_detect: "🔍",
  cut_concat: "✂️",
  transcribe: "💬",
  burn_subtitles: "📝",
  done: "✅",
  error: "❌",
  init: "⏳",
};

export default function ProgressView({ event }: Props) {
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
    </div>
  );
}
