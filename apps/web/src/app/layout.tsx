import type { Metadata } from "next";
import { Manrope, Syne } from "next/font/google";

import { Providers } from "@/components/providers";

import "./globals.css";

const display = Syne({
  variable: "--font-display",
  subsets: ["latin"],
  weight: ["600", "700", "800"],
});

const sans = Manrope({
  variable: "--font-sans",
  subsets: ["latin"],
  weight: ["400", "500", "600", "700"],
});

export const metadata: Metadata = {
  title: "NewsCrawl — Multilingual News Intelligence",
  description:
    "Distributed Bangla + English news crawling, LLM extraction, and semantic search for operators who need signal, not noise.",
  icons: {
    icon: [{ url: "/icon.svg", type: "image/svg+xml" }],
    apple: [{ url: "/logo.svg", type: "image/svg+xml" }],
  },
};

export default function RootLayout({
  children,
}: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en" className="dark">
      <body className={`${display.variable} ${sans.variable} antialiased`}>
        <Providers>{children}</Providers>
      </body>
    </html>
  );
}
