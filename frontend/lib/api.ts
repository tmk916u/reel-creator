// frontend/lib/api.ts
const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

export interface UploadResponse {
  job_id: string;
  filename: string;
  duration: number;
  file_size: number;
}

export interface TranscriptSegment {
  start: number;
  end: number;
  text: string;
}

export interface ProcessSettings {
  silence_threshold: number;
  min_silence_duration: number;
  voice_padding?: number;
  tempo_max_pause?: number;
  tempo_target_pause?: number;
  word_gap_max?: number;
  word_gap_target?: number;
  max_word_duration?: number;
  micro_silence_min_duration?: number;
  subtitle_max_chars?: number;
  trim_leading_silence?: boolean;
  skip_preview?: boolean;  // 字幕プレビューを飛ばして直接処理に進む（量産モード）
  enable_subtitles: boolean;
  enable_jump_cut?: boolean;
  enable_buzz_mode?: boolean;
  transcript_prompt?: string;
  edited_segments?: TranscriptSegment[];
  font_size: "small" | "medium" | "large";
  subtitle_position: "bottom" | "center";
  subtitle_color: "white" | "yellow";
}

export interface ProgressEvent {
  job_id: string;
  status: "pending" | "processing" | "completed" | "failed";
  stage: string;
  progress: number;
  message: string;
}

export interface JobResult {
  job_id: string;
  status: string;
  original_duration: number;
  processed_duration: number;
  silence_removed: number;
}

export async function uploadVideo(file: File): Promise<UploadResponse> {
  const formData = new FormData();
  formData.append("file", file);

  const res = await fetch(`${API_URL}/api/upload`, {
    method: "POST",
    body: formData,
  });

  if (!res.ok) {
    const err = await res.json();
    throw new Error(err.detail || "Upload failed");
  }

  return res.json();
}

export async function transcribePreview(
  jobId: string,
  transcriptPrompt: string
): Promise<TranscriptSegment[]> {
  const res = await fetch(`${API_URL}/api/transcribe/${jobId}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ transcript_prompt: transcriptPrompt }),
  });
  if (!res.ok) {
    const err = await res.json();
    throw new Error(err.detail || "字幕プレビュー失敗");
  }
  const data = await res.json();
  return data.segments as TranscriptSegment[];
}

export async function startProcessing(
  jobId: string,
  settings: ProcessSettings
): Promise<void> {
  const res = await fetch(`${API_URL}/api/process/${jobId}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(settings),
  });

  if (!res.ok) {
    const err = await res.json();
    throw new Error(err.detail || "Processing failed");
  }
}

export function subscribeProgress(
  jobId: string,
  onEvent: (event: ProgressEvent) => void,
  onError: (error: Error) => void
): () => void {
  const eventSource = new EventSource(`${API_URL}/api/progress/${jobId}`);

  eventSource.onmessage = (e) => {
    const data: ProgressEvent = JSON.parse(e.data);
    onEvent(data);

    if (data.status === "completed" || data.status === "failed") {
      eventSource.close();
    }
  };

  eventSource.onerror = () => {
    // CONNECTING(0)はブラウザが自動再接続中なのでエラー扱いしない。
    // CLOSED(2)に遷移したときだけ呼び出し側に通知する。
    if (eventSource.readyState === EventSource.CLOSED) {
      onError(new Error("Connection lost"));
    }
  };

  return () => eventSource.close();
}

export async function getResult(jobId: string): Promise<JobResult> {
  const res = await fetch(`${API_URL}/api/result/${jobId}`);
  if (!res.ok) throw new Error("Failed to get result");
  return res.json();
}

export function getDownloadUrl(jobId: string): string {
  return `${API_URL}/api/download/${jobId}`;
}

export interface CaptionsResult {
  job_id: string;
  tiktok_caption: string;
  instagram_caption: string;
  hashtags: string;
}

export async function generateCaptions(jobId: string): Promise<CaptionsResult> {
  const res = await fetch(`${API_URL}/api/captions/${jobId}`, { method: "POST" });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail || "キャプション生成に失敗");
  }
  return res.json();
}

export async function writeCaptionsToSheet(
  jobId: string,
  payload: {
    sheet_row: number;
    ig_caption: string;
    tiktok_caption: string;
    hashtags: string;
  }
): Promise<void> {
  const res = await fetch(`${API_URL}/api/captions/${jobId}/write-sheet`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail || "シート書き込みに失敗");
  }
}

export interface BuzzScoreResult {
  job_id: string;
  overall: number;
  scores: {
    hook: number; clarity: number; density: number; structure: number;
    cta: number; pace: number; searchability: number; length_fit: number;
  };
  strengths: string[];
  weaknesses: string[];
  suggestions: string[];
}

export async function getBuzzScore(jobId: string): Promise<BuzzScoreResult> {
  const res = await fetch(`${API_URL}/api/buzz-score/${jobId}`, { method: "POST" });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail || "バズスコア取得に失敗");
  }
  return res.json();
}
