"use client";

import { useState } from "react";

import { Button, Card, CardTitle, ErrorState, Input } from "@/components/ui";
import { useCreateSource, useUpdateSource } from "@/lib/hooks";
import type { Source, SourceCreatePayload, SourceUpdatePayload } from "@/lib/types";

interface FormState {
  name: string;
  slug: string;
  base_url: string;
  language: string;
  country: string;
  enabled: boolean;
  crawl_enabled: boolean;
  requires_browser: boolean;
  crawl_frequency_minutes: string;
  rate_limit_delay_seconds: string;
  max_concurrency: string;
  robots_policy: string;
  source_weight: string;
  allowed_domains: string;
  article_url_patterns: string;
  section_urls: string;
  sitemap_urls: string;
  rss_urls: string;
  selector_title: string;
  selector_subtitle: string;
  selector_author: string;
  selector_published_at: string;
  selector_category: string;
  selector_body: string;
  selector_images: string;
  selector_tags: string;
  selector_body_probe: string;
}

const EMPTY_STATE: FormState = {
  name: "",
  slug: "",
  base_url: "",
  language: "",
  country: "",
  enabled: true,
  crawl_enabled: true,
  requires_browser: false,
  crawl_frequency_minutes: "60",
  rate_limit_delay_seconds: "2",
  max_concurrency: "2",
  robots_policy: "obey",
  source_weight: "1",
  allowed_domains: "",
  article_url_patterns: "",
  section_urls: "",
  sitemap_urls: "",
  rss_urls: "",
  selector_title: "",
  selector_subtitle: "",
  selector_author: "",
  selector_published_at: "",
  selector_category: "",
  selector_body: "",
  selector_images: "",
  selector_tags: "",
  selector_body_probe: "",
};

const splitCsv = (value: string): string[] =>
  value
    .split(",")
    .map((v) => v.trim())
    .filter(Boolean);

const joinCsv = (values: string[] | undefined): string => (values ?? []).join(", ");

function stateFromSource(source: Source): FormState {
  const selectors = source.selectors;
  return {
    name: source.name,
    slug: source.slug,
    base_url: source.base_url,
    language: source.language,
    country: source.country,
    enabled: source.enabled,
    crawl_enabled: source.crawl_enabled,
    requires_browser: source.requires_browser,
    crawl_frequency_minutes: String(source.crawl_frequency_minutes),
    rate_limit_delay_seconds: String(source.rate_limit_delay_seconds),
    max_concurrency: String(source.max_concurrency),
    robots_policy: source.robots_policy,
    source_weight: String(source.source_weight),
    allowed_domains: joinCsv(source.allowed_domains),
    article_url_patterns: joinCsv(source.article_url_patterns),
    section_urls: joinCsv(source.section_urls),
    sitemap_urls: joinCsv(source.sitemap_urls),
    rss_urls: joinCsv(source.rss_urls),
    selector_title: joinCsv(selectors?.title),
    selector_subtitle: joinCsv(selectors?.subtitle),
    selector_author: joinCsv(selectors?.author),
    selector_published_at: joinCsv(selectors?.published_at),
    selector_category: joinCsv(selectors?.category),
    selector_body: joinCsv(selectors?.body),
    selector_images: joinCsv(selectors?.images),
    selector_tags: joinCsv(selectors?.tags),
    selector_body_probe: selectors?.body_probe ?? "",
  };
}

function payloadFromState(state: FormState): SourceCreatePayload {
  return {
    name: state.name,
    slug: state.slug,
    base_url: state.base_url,
    language: state.language,
    country: state.country,
    enabled: state.enabled,
    crawl_enabled: state.crawl_enabled,
    requires_browser: state.requires_browser,
    crawl_frequency_minutes: Number(state.crawl_frequency_minutes) || 60,
    rate_limit_delay_seconds: Number(state.rate_limit_delay_seconds) || 0,
    max_concurrency: Number(state.max_concurrency) || 1,
    robots_policy: state.robots_policy || "obey",
    extraction_strategy: "selectors",
    source_weight: Number(state.source_weight) || 1,
    allowed_domains: splitCsv(state.allowed_domains),
    article_url_patterns: splitCsv(state.article_url_patterns),
    section_urls: splitCsv(state.section_urls),
    sitemap_urls: splitCsv(state.sitemap_urls),
    rss_urls: splitCsv(state.rss_urls),
    selectors: {
      title: splitCsv(state.selector_title),
      subtitle: splitCsv(state.selector_subtitle),
      author: splitCsv(state.selector_author),
      published_at: splitCsv(state.selector_published_at),
      category: splitCsv(state.selector_category),
      body: splitCsv(state.selector_body),
      images: splitCsv(state.selector_images),
      tags: splitCsv(state.selector_tags),
      body_probe: state.selector_body_probe.trim() || null,
    },
  };
}

function Field({
  label,
  hint,
  children,
}: {
  label: string;
  hint?: string;
  children: React.ReactNode;
}) {
  return (
    <div>
      <label className="mb-1 block text-xs text-slate-500">
        {label}
        {hint && <span className="ml-1 text-slate-600">({hint})</span>}
      </label>
      {children}
    </div>
  );
}

export function SourceForm({
  source,
  onClose,
}: {
  source?: Source;
  onClose: () => void;
}) {
  const [state, setState] = useState<FormState>(
    source ? stateFromSource(source) : EMPTY_STATE,
  );
  const createSource = useCreateSource();
  const updateSource = useUpdateSource();
  const mutation = source ? updateSource : createSource;
  const set = <K extends keyof FormState>(key: K, value: FormState[K]) =>
    setState((prev) => ({ ...prev, [key]: value }));

  return (
    <form
      className="nc-scale-in mb-4 space-y-4"
      onSubmit={async (e) => {
        e.preventDefault();
        if (source) {
          const update: SourceUpdatePayload = payloadFromState(state);
          delete update.slug;
          await updateSource.mutateAsync({ id: source.id, ...update });
        } else {
          await createSource.mutateAsync(payloadFromState(state));
        }
        onClose();
      }}
    >
      <Card>
        <CardTitle>Basics</CardTitle>
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 md:grid-cols-4">
          <Field label="Name">
            <Input
              value={state.name}
              onChange={(e) => set("name", e.target.value)}
              required
            />
          </Field>
          <Field label="Slug" hint={source ? "immutable" : "a-z, 0-9, -"}>
            <Input
              value={state.slug}
              onChange={(e) => set("slug", e.target.value)}
              pattern="^[a-z0-9-]+$"
              disabled={Boolean(source)}
              required
            />
          </Field>
          <Field label="Base URL">
            <Input
              value={state.base_url}
              onChange={(e) => set("base_url", e.target.value)}
              placeholder="https://example.com"
              required
            />
          </Field>
          <Field label="Language">
            <Input
              value={state.language}
              onChange={(e) => set("language", e.target.value)}
              placeholder="bn / en"
              required
            />
          </Field>
          <Field label="Country">
            <Input
              value={state.country}
              onChange={(e) => set("country", e.target.value)}
              placeholder="BD"
              required
            />
          </Field>
          <label className="flex items-center gap-2 self-end pb-1.5 text-sm text-slate-600 dark:text-slate-300">
            <input
              type="checkbox"
              className="accent-sky-600"
              checked={state.enabled}
              onChange={(e) => set("enabled", e.target.checked)}
            />
            Enabled
          </label>
          <label className="flex items-center gap-2 self-end pb-1.5 text-sm text-slate-600 dark:text-slate-300">
            <input
              type="checkbox"
              className="accent-sky-600"
              checked={state.crawl_enabled}
              onChange={(e) => set("crawl_enabled", e.target.checked)}
            />
            Crawl enabled
          </label>
          <label className="flex items-center gap-2 self-end pb-1.5 text-sm text-slate-600 dark:text-slate-300">
            <input
              type="checkbox"
              className="accent-sky-600"
              checked={state.requires_browser}
              onChange={(e) => set("requires_browser", e.target.checked)}
            />
            Requires browser
          </label>
        </div>
      </Card>

      <Card>
        <CardTitle>Discovery &amp; crawl behavior</CardTitle>
        <div className="grid grid-cols-1 gap-3 md:grid-cols-2">
          <Field label="Allowed domains" hint="comma-separated">
            <Input
              value={state.allowed_domains}
              onChange={(e) => set("allowed_domains", e.target.value)}
              placeholder="example.com"
              className="w-full"
            />
          </Field>
          <Field label="Article URL patterns" hint="regex, comma-separated">
            <Input
              value={state.article_url_patterns}
              onChange={(e) => set("article_url_patterns", e.target.value)}
              className="w-full"
            />
          </Field>
          <Field label="Section URLs" hint="comma-separated">
            <Input
              value={state.section_urls}
              onChange={(e) => set("section_urls", e.target.value)}
              className="w-full"
            />
          </Field>
          <Field label="Sitemap URLs" hint="comma-separated">
            <Input
              value={state.sitemap_urls}
              onChange={(e) => set("sitemap_urls", e.target.value)}
              className="w-full"
            />
          </Field>
          <Field label="RSS URLs" hint="comma-separated">
            <Input
              value={state.rss_urls}
              onChange={(e) => set("rss_urls", e.target.value)}
              className="w-full"
            />
          </Field>
        </div>
        <div className="mt-3 grid grid-cols-1 gap-3 sm:grid-cols-2 md:grid-cols-4">
          <Field label="Crawl frequency" hint="minutes">
            <Input
              type="number"
              min={1}
              value={state.crawl_frequency_minutes}
              onChange={(e) => set("crawl_frequency_minutes", e.target.value)}
            />
          </Field>
          <Field label="Rate limit delay" hint="seconds">
            <Input
              type="number"
              min={0}
              step="0.1"
              value={state.rate_limit_delay_seconds}
              onChange={(e) => set("rate_limit_delay_seconds", e.target.value)}
            />
          </Field>
          <Field label="Max concurrency">
            <Input
              type="number"
              min={1}
              max={32}
              value={state.max_concurrency}
              onChange={(e) => set("max_concurrency", e.target.value)}
            />
          </Field>
          <Field label="Source weight">
            <Input
              type="number"
              min={0}
              step="0.1"
              value={state.source_weight}
              onChange={(e) => set("source_weight", e.target.value)}
            />
          </Field>
        </div>
      </Card>

      <Card>
        <CardTitle>Extraction selectors</CardTitle>
        <p className="mb-3 text-xs text-slate-500">
          CSS selectors tried in order, comma-separated. JSON-LD metadata is tried
          first when present — these are the fallback/primary extraction rules.
        </p>
        <div className="grid grid-cols-1 gap-3 md:grid-cols-2">
          <Field label="Title">
            <Input
              value={state.selector_title}
              onChange={(e) => set("selector_title", e.target.value)}
              placeholder="h1::text"
              className="w-full"
            />
          </Field>
          <Field label="Subtitle">
            <Input
              value={state.selector_subtitle}
              onChange={(e) => set("selector_subtitle", e.target.value)}
              className="w-full"
            />
          </Field>
          <Field label="Author">
            <Input
              value={state.selector_author}
              onChange={(e) => set("selector_author", e.target.value)}
              className="w-full"
            />
          </Field>
          <Field label="Published at">
            <Input
              value={state.selector_published_at}
              onChange={(e) => set("selector_published_at", e.target.value)}
              placeholder="time::attr(datetime)"
              className="w-full"
            />
          </Field>
          <Field label="Category">
            <Input
              value={state.selector_category}
              onChange={(e) => set("selector_category", e.target.value)}
              className="w-full"
            />
          </Field>
          <Field label="Body">
            <Input
              value={state.selector_body}
              onChange={(e) => set("selector_body", e.target.value)}
              placeholder="article p"
              className="w-full"
            />
          </Field>
          <Field label="Images">
            <Input
              value={state.selector_images}
              onChange={(e) => set("selector_images", e.target.value)}
              className="w-full"
            />
          </Field>
          <Field label="Tags">
            <Input
              value={state.selector_tags}
              onChange={(e) => set("selector_tags", e.target.value)}
              className="w-full"
            />
          </Field>
          <Field label="Body probe" hint="rendered-page check, single selector">
            <Input
              value={state.selector_body_probe}
              onChange={(e) => set("selector_body_probe", e.target.value)}
              className="w-full"
            />
          </Field>
        </div>
      </Card>

      <div className="flex items-center gap-3">
        <Button type="submit" disabled={mutation.isPending}>
          {mutation.isPending ? "Saving…" : source ? "Save changes" : "Create source"}
        </Button>
        <Button type="button" variant="ghost" onClick={onClose}>
          Cancel
        </Button>
        {mutation.isError && <ErrorState message={(mutation.error as Error).message} />}
      </div>
    </form>
  );
}
