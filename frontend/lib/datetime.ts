// JST 前提の日時ユーティリティ（ユーザーのブラウザは JST 想定）

const pad = (n: number) => String(n).padStart(2, "0");

/** ISO 文字列 → datetime-local 入力値（YYYY-MM-DDTHH:mm, ローカル＝JST）。 */
export function isoToLocalInput(iso: string | null | undefined): string {
  if (!iso) return "";
  const d = new Date(iso);
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`;
}

/** datetime-local 入力値 → 絶対時刻 ISO（UTC）。空なら undefined。 */
export function localInputToIso(local: string): string | undefined {
  if (!local) return undefined;
  return new Date(local).toISOString();
}

/** 表示用フォーマット（JST）。 */
export function formatJst(iso: string | null | undefined): string {
  if (!iso) return "—";
  return new Date(iso).toLocaleString("ja-JP", {
    timeZone: "Asia/Tokyo",
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  });
}
