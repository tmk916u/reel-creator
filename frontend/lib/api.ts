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
  suspicious?: boolean; // 誤認識候補なら true (赤字ハイライト用)
}

export interface AnalyzeResult {
  profile: "talk" | "visual" | "mixed";
  label: string;
  reason: string;
  speech_ratio: number;
  orientation: "vertical" | "landscape";
  settings: Partial<ProcessSettings>;
}

export async function analyzeVideo(jobId: string): Promise<AnalyzeResult> {
  const res = await fetch(`${API_URL}/api/analyze/${jobId}`, { method: "POST" });
  if (!res.ok) {
    const err = await res.json();
    throw new Error(err.detail || "解析に失敗しました");
  }
  return res.json();
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
  topic_style?: "default" | "sleek" | "clean";
  enable_sfx?: boolean;
  subtitle_max_chars?: number;
  trim_leading_silence?: boolean;
  skip_preview?: boolean; // 字幕プレビューを飛ばして直接処理に進む（量産モード）
  enable_subtitles: boolean;
  enable_jump_cut?: boolean;
  enable_buzz_mode?: boolean;
  editor_mode?: "rule_based" | "director"; // 編集方針
  director_target_min?: number;
  director_target_max?: number;
  transcript_prompt?: string;
  edited_segments?: TranscriptSegment[];
  font_size: "small" | "medium" | "large";
  subtitle_position: "bottom" | "center";
  subtitle_color: "white" | "yellow";
  subtitle_motion?: "none" | "karaoke" | "fade" | "pop";
  color_grade?: "none" | "minimal" | "cinematic" | "monochrome" | "pop";
  enable_auto_reframe?: boolean;
  reframe_sample_fps?: number;
  reframe_smoothing?: number;
  reframe_padding?: number;
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
  transcriptPrompt: string,
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
  settings: ProcessSettings,
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
  onError: (error: Error) => void,
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
  const res = await fetch(`${API_URL}/api/captions/${jobId}`, {
    method: "POST",
  });
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
  },
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
    hook: number;
    clarity: number;
    density: number;
    structure: number;
    cta: number;
    pace: number;
    searchability: number;
    length_fit: number;
  };
  strengths: string[];
  weaknesses: string[];
  suggestions: string[];
}

export async function getBuzzScore(jobId: string): Promise<BuzzScoreResult> {
  const res = await fetch(`${API_URL}/api/buzz-score/${jobId}`, {
    method: "POST",
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail || "バズスコア取得に失敗");
  }
  return res.json();
}

// ===== 投稿機能 (social-publishing) =====

export type PostPlatform = "instagram" | "youtube";
export type PostStatus =
  | "draft"
  | "scheduled"
  | "posting"
  | "posted"
  | "failed"
  | "cancelled";
export type PrivacyStatus = "public" | "private" | "unlisted";

export interface ScheduledPost {
  id: string;
  platform: PostPlatform;
  scheduled_at: string | null;
  status: PostStatus;
  caption: string | null;
  title: string | null;
  description: string | null;
  hashtags: string | null;
  privacy_status: string | null;
  posted_url: string | null;
  external_post_id: string | null;
  error_message: string | null;
  retry_count: number;
  posted_at: string | null;
  created_at: string;
  updated_at: string;
}

export interface PostItem {
  id: string;
  file_url: string;
  thumbnail_url: string | null;
  duration_seconds: number | null;
  aspect_ratio: string | null;
  theme: string | null;
  memo: string | null;
  original_filename: string | null;
  created_at: string;
  updated_at: string;
  posts: ScheduledPost[];
}

export interface UploadVideoResult {
  video_id: string;
  file_url: string;
  thumbnail_url: string | null;
  duration_seconds: number | null;
  original_filename: string | null;
}

export interface PostCreatePayload {
  video_id: string;
  theme?: string;
  memo?: string;
  hashtags?: string;
  post_to_instagram: boolean;
  post_to_youtube: boolean;
  instagram_caption?: string;
  instagram_scheduled_at?: string;
  youtube_title?: string;
  youtube_description?: string;
  youtube_scheduled_at?: string;
  privacy_status?: PrivacyStatus;
}

export interface PostUpdatePayload {
  theme?: string;
  memo?: string;
  hashtags?: string;
  instagram_caption?: string;
  instagram_scheduled_at?: string;
  youtube_title?: string;
  youtube_description?: string;
  youtube_scheduled_at?: string;
  privacy_status?: PrivacyStatus;
}

function extractError(detail: unknown, fallback: string): string {
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail)) {
    const msgs = detail
      .map((d) =>
        d && typeof d === "object" && "msg" in d
          ? (d as { msg: string }).msg
          : "",
      )
      .filter(Boolean);
    if (msgs.length) return msgs.join(" / ");
  }
  return fallback;
}

async function throwApiError(res: Response, fallback: string): Promise<never> {
  const body = await res.json().catch(() => ({}));
  throw new Error(
    extractError((body as { detail?: unknown }).detail, fallback),
  );
}

export function postMediaUrl(videoId: string): string {
  return `${API_URL}/api/posts/media/${videoId}`;
}

export function postThumbnailUrl(videoId: string): string {
  return `${API_URL}/api/posts/media/${videoId}/thumbnail`;
}

export async function uploadPostVideo(file: File): Promise<UploadVideoResult> {
  const formData = new FormData();
  formData.append("file", file);
  const res = await fetch(`${API_URL}/api/posts/upload`, {
    method: "POST",
    body: formData,
  });
  if (!res.ok) await throwApiError(res, "アップロードに失敗しました");
  return res.json();
}

export async function createPost(
  payload: PostCreatePayload,
): Promise<PostItem> {
  const res = await fetch(`${API_URL}/api/posts`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  if (!res.ok) await throwApiError(res, "投稿の作成に失敗しました");
  return res.json();
}

export async function listPosts(): Promise<PostItem[]> {
  const res = await fetch(`${API_URL}/api/posts`, { cache: "no-store" });
  if (!res.ok) await throwApiError(res, "一覧の取得に失敗しました");
  return res.json();
}

export async function getPost(id: string): Promise<PostItem> {
  const res = await fetch(`${API_URL}/api/posts/${id}`, { cache: "no-store" });
  if (!res.ok) await throwApiError(res, "投稿の取得に失敗しました");
  return res.json();
}

export async function updatePost(
  id: string,
  payload: PostUpdatePayload,
): Promise<PostItem> {
  const res = await fetch(`${API_URL}/api/posts/${id}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  if (!res.ok) await throwApiError(res, "投稿の更新に失敗しました");
  return res.json();
}

export async function deletePost(id: string): Promise<void> {
  const res = await fetch(`${API_URL}/api/posts/${id}`, { method: "DELETE" });
  if (!res.ok && res.status !== 204)
    await throwApiError(res, "削除に失敗しました");
}

export async function publishNow(postId: string): Promise<ScheduledPost> {
  const res = await fetch(`${API_URL}/api/posts/${postId}/publish_now`, {
    method: "POST",
  });
  if (!res.ok) await throwApiError(res, "投稿に失敗しました");
  return res.json();
}

export async function retryPost(postId: string): Promise<ScheduledPost> {
  const res = await fetch(`${API_URL}/api/posts/${postId}/retry`, {
    method: "POST",
  });
  if (!res.ok) await throwApiError(res, "リトライに失敗しました");
  return res.json();
}

// --- SNS 連携 (social connections) ---

export interface ConnectionItem {
  id: string;
  platform: PostPlatform;
  account_name: string | null;
  external_account_id: string | null;
  is_active: boolean;
  token_expires_at: string | null;
  created_at: string;
}

export async function listConnections(): Promise<ConnectionItem[]> {
  const res = await fetch(`${API_URL}/api/connections`, { cache: "no-store" });
  if (!res.ok) await throwApiError(res, "連携状態の取得に失敗しました");
  return res.json();
}

export function youtubeConnectUrl(): string {
  return `${API_URL}/api/connections/youtube/start`;
}

export function instagramConnectUrl(): string {
  return `${API_URL}/api/connections/meta/start`;
}

export async function disconnect(id: string): Promise<void> {
  const res = await fetch(`${API_URL}/api/connections/${id}`, {
    method: "DELETE",
  });
  if (!res.ok && res.status !== 204)
    await throwApiError(res, "連携解除に失敗しました");
}

// --- AI キャプション生成 (add-ai-caption-suggest) ---

export interface CaptionSuggestion {
  instagram_caption: string;
  youtube_title: string;
  youtube_description: string;
  hashtags: string[];
  cover_text_candidates: string[];
}

export async function suggestCaptions(
  videoId: string,
  theme?: string,
): Promise<CaptionSuggestion> {
  const res = await fetch(`${API_URL}/api/posts/${videoId}/suggest`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ theme: theme || null }),
  });
  if (!res.ok) await throwApiError(res, "AI 生成に失敗しました");
  return res.json();
}

// --- アカウント文脈プロファイル (account-context-profile) ---

export interface AccountProfile {
  id: string;
  niche: string | null;
  target_audience: string | null;
  tone: string | null;
  goals: string | null;
  hashtags: string | null;
  ng_words: string | null;
  notes: string | null;
  updated_at: string;
}

export type AccountProfileInput = Omit<AccountProfile, "id" | "updated_at">;

export async function getAccountProfile(): Promise<AccountProfile> {
  const res = await fetch(`${API_URL}/api/account-profile`, {
    cache: "no-store",
  });
  if (!res.ok) await throwApiError(res, "プロファイルの取得に失敗しました");
  return res.json();
}

export async function updateAccountProfile(
  input: Partial<AccountProfileInput>,
): Promise<AccountProfile> {
  const res = await fetch(`${API_URL}/api/account-profile`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(input),
  });
  if (!res.ok) await throwApiError(res, "プロファイルの保存に失敗しました");
  return res.json();
}
