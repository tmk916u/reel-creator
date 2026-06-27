import type { Metadata } from "next";
import "./globals.css";

const BUILD_LABEL = (process.env.NEXT_PUBLIC_BUILD_LABEL || "")
  .trim()
  .toUpperCase();

export const metadata: Metadata = {
  title: BUILD_LABEL ? `[${BUILD_LABEL}] Reel Creator` : "Reel Creator",
  description: "TikTok/IGリール用動画を簡単作成",
};

function BuildBadge() {
  if (!BUILD_LABEL) return null;
  const isQuality = BUILD_LABEL.includes("QUALITY");
  const styles = isQuality
    ? "bg-yellow-500/25 text-yellow-100 border-yellow-400/50"
    : "bg-blue-500/15 text-blue-200 border-blue-400/30";
  return (
    <div
      className={`fixed top-2 right-2 z-50 px-2 py-1 text-[11px] font-mono rounded border pointer-events-none select-none ${styles}`}
      aria-label={`build: ${BUILD_LABEL}`}
    >
      {BUILD_LABEL}
    </div>
  );
}

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="ja">
      <body className="bg-gray-950 text-white min-h-screen">
        <BuildBadge />
        {children}
      </body>
    </html>
  );
}
