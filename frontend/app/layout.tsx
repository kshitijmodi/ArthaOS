import type { Metadata } from "next";
import { Inter } from "next/font/google";
import "./globals.css";

const inter = Inter({ subsets: ["latin"] });

export const metadata: Metadata = {
  title: "ArthaOS — Personal Financial Intelligence",
  description: "Local-first agentic AI finance system",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" className="h-full antialiased dark">
      <body className={`${inter.className} min-h-full bg-[#0a0a0f] text-white`}>{children}</body>
    </html>
  );
}
