import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Reel Creator",
  description: "TikTok/IGリール用動画を簡単作成",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="ja">
      <body className="bg-gray-950 text-white min-h-screen">{children}</body>
    </html>
  );
}
