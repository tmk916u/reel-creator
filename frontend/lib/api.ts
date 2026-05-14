// frontend/lib/api.ts
const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

export interface UploadResponse {
  job_id: string;
  filename: string;
  duration: number;
  file_size: number;
}

export interface ProcessSettings {
  silence_threshold: number;
  min_silence_duration: number;
  enable_subtitles: boolean;
  enable_jump_cut?: boolean;
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
    onError(new Error("Connection lost"));
    eventSource.close();
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
