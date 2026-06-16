import type { Metadata } from "next";
import "./globals.css";
import { ThemeProvider } from "@/components/ThemeProvider";

export const metadata: Metadata = {
  title: "ArthaOS — Personal Financial Intelligence",
  description: "Your intelligent personal finance command center",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" className="dark" suppressHydrationWarning>
      <body className="font-sans bg-bg text-tx antialiased">
        <ThemeProvider>{children}</ThemeProvider>
      </body>
    </html>
  );
}
