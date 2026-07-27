import type { Metadata } from "next";
import { Hind_Siliguri, Manrope, Syne } from "next/font/google";

import { Providers } from "@/components/providers";
import { ThemeProvider, themeInitScript } from "@/lib/theme";

import "./globals.css";

const display = Syne({
  variable: "--font-display-syne",
  subsets: ["latin"],
  weight: ["600", "700", "800"],
});

const sans = Manrope({
  variable: "--font-sans-manrope",
  subsets: ["latin"],
  weight: ["400", "500", "600", "700"],
});

const hind = Hind_Siliguri({
  variable: "--font-hind",
  subsets: ["latin", "bengali"],
  weight: ["300", "400", "500", "600", "700"],
});

export const metadata: Metadata = {
  title: "NewsCrawl | Multilingual News Intelligence",
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
    <html lang="en" suppressHydrationWarning>
      <head>
        <script dangerouslySetInnerHTML={{ __html: themeInitScript }} />
      </head>
      <body
        className={`${hind.variable} ${sans.variable} ${display.variable} antialiased`}
        suppressHydrationWarning
      >
        <ThemeProvider>
          <Providers>{children}</Providers>
        </ThemeProvider>
      </body>
    </html>
  );
}
