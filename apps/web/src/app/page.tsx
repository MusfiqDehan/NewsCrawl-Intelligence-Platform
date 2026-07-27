"use client";

import {
  BrainCircuit,
  Languages,
  Radar,
  Search,
  ShieldCheck,
  Workflow,
} from "lucide-react";
import Link from "next/link";
import { useSyncExternalStore } from "react";

import { Brand, Logo } from "@/components/logo";
import { ThemeToggle } from "@/components/theme-toggle";
import { getToken, subscribeToAuth } from "@/lib/api";

const capabilities = [
  {
    icon: Radar,
    title: "Distributed crawling",
    body: "Scrapy workers with Playwright fallback pull Bangla and English sources on a controlled frontier — rate-limited, lease-aware, and retry-safe.",
  },
  {
    icon: Workflow,
    title: "Processing pipeline",
    body: "Raw HTML lands in object storage, then moves through cleaning, language detection, near-duplicate detection, and structured LLM extraction.",
  },
  {
    icon: Search,
    title: "Semantic search",
    body: "BGE-M3 embeddings and pgvector turn headlines and bodies into multilingual retrieval — find related coverage across outlets in seconds.",
  },
  {
    icon: BrainCircuit,
    title: "LLM intelligence",
    body: "Gemini-backed extraction captures entities, categories, and summaries so operators read signal instead of scrolling raw HTML dumps.",
  },
  {
    icon: Languages,
    title: "Bangla + English first",
    body: "Built for Bangladesh and international wires together: normalized URLs, content hashing, and language-aware indexing from day one.",
  },
  {
    icon: ShieldCheck,
    title: "Ops control plane",
    body: "Pause jobs, inspect queues, watch worker heartbeats, and audit source health from a single FastAPI + Next.js operations dashboard.",
  },
];

export default function LandingPage() {
  const token = useSyncExternalStore(subscribeToAuth, getToken, () => null);
  const primaryHref = token ? "/dashboard" : "/login";
  const primaryLabel = token ? "Open dashboard" : "Sign in";

  return (
    <div className="nc-landing min-h-screen bg-[var(--nc-ink)] text-slate-700 dark:text-slate-200">
      {/* ── Hero ─────────────────────────────────────────────────────────── */}
      <section className="relative isolate min-h-[100svh] overflow-hidden">
        <div
          aria-hidden
          className="nc-grid-drift absolute inset-[-8%] opacity-70"
          style={{
            backgroundImage: `
              radial-gradient(ellipse 80% 55% at 50% -10%, rgba(14,165,233,0.28), transparent 55%),
              linear-gradient(rgba(148,163,184,0.07) 1px, transparent 1px),
              linear-gradient(90deg, rgba(148,163,184,0.07) 1px, transparent 1px)
            `,
            backgroundSize: "auto, 72px 72px, 72px 72px",
          }}
        />
        <div
          aria-hidden
          className="nc-pulse-line absolute inset-x-0 top-[42%] h-px bg-gradient-to-r from-transparent via-sky-400/50 to-transparent"
        />
        <div
          aria-hidden
          className="absolute inset-0 bg-[linear-gradient(180deg,transparent_55%,var(--nc-ink)_92%)]"
        />

        <header className="relative z-10 mx-auto flex w-full max-w-6xl flex-wrap items-center justify-between gap-x-4 gap-y-3 px-4 py-4 sm:px-6 sm:py-6">
          <Link href="/" className="inline-flex items-center gap-3">
            <Logo className="h-9 w-9 sm:h-10 sm:w-10" />
            <span className="font-[family-name:var(--font-display)] text-base font-bold tracking-tight text-slate-900 dark:text-white sm:text-lg">
              NewsCrawl
            </span>
          </Link>
          <nav className="flex items-center gap-2 text-sm sm:gap-3">
            <Link
              href="/explore"
              className="hidden text-slate-500 transition hover:text-slate-900 dark:text-slate-400 dark:hover:text-white sm:inline"
            >
              Search news
            </Link>
            <a
              href="#capabilities"
              className="hidden text-slate-500 transition hover:text-slate-900 dark:text-slate-400 dark:hover:text-white sm:inline"
            >
              Capabilities
            </a>
            <ThemeToggle />
            <Link
              href={primaryHref}
              className="rounded-lg bg-sky-600 px-3 py-1.5 text-sm font-medium text-white transition hover:bg-sky-500 sm:px-4 sm:py-2"
            >
              {primaryLabel}
            </Link>
          </nav>
        </header>

        <div className="relative z-10 mx-auto flex min-h-[calc(100svh-5.5rem)] w-full max-w-6xl flex-col justify-end px-4 pb-20 pt-16 sm:px-6 sm:pb-28">
          <div className="nc-fade-up mb-8">
            <Logo className="h-16 w-16 sm:h-20 sm:w-20" />
          </div>
          <p className="nc-fade-up nc-fade-up-delay-1 font-[family-name:var(--font-display)] text-3xl font-extrabold leading-[0.95] tracking-tight text-slate-900 dark:text-white sm:text-6xl md:text-7xl lg:text-8xl">
            NewsCrawl
          </p>
          <h1 className="nc-fade-up nc-fade-up-delay-2 mt-6 max-w-3xl font-[family-name:var(--font-display)] text-2xl font-semibold leading-snug text-slate-700 dark:text-slate-100 sm:text-4xl">
            Multilingual news intelligence for teams who need the story before it cools.
          </h1>
          <p className="nc-fade-up nc-fade-up-delay-3 mt-5 max-w-xl text-base leading-relaxed text-slate-500 dark:text-slate-400 sm:text-lg">
            Crawl, clean, extract, and search Bangla and English coverage from one
            production-grade control plane.
          </p>
          <div className="nc-fade-up nc-fade-up-delay-3 mt-10 flex flex-wrap items-center gap-4">
            <Link
              href="/explore"
              className="rounded-lg bg-sky-600 px-6 py-3 text-sm font-semibold text-white transition hover:bg-sky-500"
            >
              Search news
            </Link>
            <Link
              href={primaryHref}
              className="rounded-lg border border-slate-300 px-6 py-3 text-sm font-medium text-slate-700 transition hover:border-slate-400 hover:text-slate-900 dark:border-slate-700 dark:text-slate-200 dark:hover:border-slate-500 dark:hover:text-white"
            >
              {primaryLabel}
            </Link>
          </div>
        </div>
      </section>

      {/* ── Capabilities ─────────────────────────────────────────────────── */}
      <section id="capabilities" className="border-t border-slate-200 dark:border-slate-900">
        <div className="mx-auto max-w-6xl px-6 py-24">
          <p className="text-sm font-medium uppercase tracking-[0.2em] text-sky-400">
            Capabilities
          </p>
          <h2 className="mt-3 max-w-2xl font-[family-name:var(--font-display)] text-3xl font-bold text-slate-900 dark:text-white sm:text-4xl">
            From source URL to searchable intelligence.
          </h2>
          <p className="mt-4 max-w-2xl text-slate-500 dark:text-slate-400">
            Five separated planes — control, crawl, processing, query, and observability —
            keep the system resilient under real-world newsroom load.
          </p>

          <div className="mt-16 divide-y divide-slate-200 border-y border-slate-200 dark:divide-slate-800 dark:border-slate-800">
            {capabilities.map(({ icon: Icon, title, body }) => (
              <article
                key={title}
                className="grid gap-4 py-10 sm:grid-cols-[auto_1fr] sm:gap-8"
              >
                <div className="flex h-12 w-12 items-center justify-center rounded-xl bg-[var(--nc-signal-soft)] text-sky-400">
                  <Icon className="h-5 w-5" strokeWidth={1.75} />
                </div>
                <div>
                  <h3 className="font-[family-name:var(--font-display)] text-xl font-semibold text-slate-900 dark:text-white">
                    {title}
                  </h3>
                  <p className="mt-2 max-w-3xl text-[15px] leading-relaxed text-slate-500 dark:text-slate-400">
                    {body}
                  </p>
                </div>
              </article>
            ))}
          </div>
        </div>
      </section>

      {/* ── Pipeline ─────────────────────────────────────────────────────── */}
      <section className="border-t border-slate-200 bg-[var(--nc-panel)] dark:border-slate-900">
        <div className="mx-auto max-w-6xl px-6 py-24">
          <p className="text-sm font-medium uppercase tracking-[0.2em] text-sky-400">
            Pipeline
          </p>
          <h2 className="mt-3 font-[family-name:var(--font-display)] text-3xl font-bold text-slate-900 dark:text-white sm:text-4xl">
            Built as a continuous news fabric.
          </h2>
          <p className="mt-4 max-w-2xl text-slate-500 dark:text-slate-400">
            Operators schedule crawls; workers fetch and normalize; processors enrich;
            the query plane serves dashboards and semantic search.
          </p>

          <ol className="mt-14 grid gap-10 md:grid-cols-4">
            {[
              { step: "01", label: "Discover", detail: "Frontier leases & source configs" },
              { step: "02", label: "Capture", detail: "HTML to S3-compatible storage" },
              { step: "03", label: "Enrich", detail: "Dedup · LLM · embeddings" },
              { step: "04", label: "Query", detail: "Ops UI · pgvector search" },
            ].map((item) => (
              <li key={item.step} className="relative">
                <div className="font-[family-name:var(--font-display)] text-sm font-semibold text-sky-400">
                  {item.step}
                </div>
                <div className="mt-3 text-lg font-semibold text-slate-900 dark:text-white">
                  {item.label}
                </div>
                <p className="mt-2 text-sm text-slate-500 dark:text-slate-400">{item.detail}</p>
              </li>
            ))}
          </ol>
        </div>
      </section>

      {/* ── CTA ──────────────────────────────────────────────────────────── */}
      <section className="border-t border-slate-200 dark:border-slate-900">
        <div className="mx-auto flex max-w-6xl flex-col items-start gap-8 px-6 py-24 sm:flex-row sm:items-end sm:justify-between">
          <div>
            <h2 className="font-[family-name:var(--font-display)] text-3xl font-bold text-slate-900 dark:text-white sm:text-4xl">
              Ready to run the control plane?
            </h2>
            <p className="mt-3 max-w-lg text-slate-500 dark:text-slate-400">
              Sign in to monitor crawls, inspect articles, and search across languages.
            </p>
          </div>
          <Link
            href={primaryHref}
            className="rounded-lg bg-sky-600 px-6 py-3 text-sm font-semibold text-white transition hover:bg-sky-500"
          >
            {primaryLabel}
          </Link>
        </div>
      </section>

      <footer className="border-t border-slate-200 dark:border-slate-900">
        <div className="mx-auto flex max-w-6xl flex-col gap-3 px-6 py-8 text-sm text-slate-500 sm:flex-row sm:items-center sm:justify-between">
          <Brand logoClassName="h-7 w-7" />
          <span>Multilingual news crawling & intelligence platform</span>
        </div>
      </footer>
    </div>
  );
}
