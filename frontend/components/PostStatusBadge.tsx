import type { PostStatus } from "@/lib/api";

const STYLES: Record<PostStatus, string> = {
  draft: "bg-gray-700 text-gray-200",
  scheduled: "bg-blue-600/30 text-blue-200 border border-blue-500/40",
  posting: "bg-yellow-600/30 text-yellow-200 border border-yellow-500/40",
  posted: "bg-green-600/30 text-green-200 border border-green-500/40",
  failed: "bg-red-600/30 text-red-200 border border-red-500/40",
  cancelled: "bg-gray-700 text-gray-400",
};

const LABELS: Record<PostStatus, string> = {
  draft: "下書き",
  scheduled: "予約済み",
  posting: "投稿中",
  posted: "投稿済み",
  failed: "失敗",
  cancelled: "キャンセル",
};

export default function PostStatusBadge({ status }: { status: PostStatus }) {
  return (
    <span
      className={`inline-block rounded px-2 py-0.5 text-xs font-medium ${STYLES[status]}`}
    >
      {LABELS[status]}
    </span>
  );
}
