# Deduplication

News content duplicates at four different granularities; each gets a
progressively more expensive detector, and cheaper stages short-circuit the
expensive ones (ADR #4).

## Stage 0 — URL identity (before fetch)

Per-source URL normalization (tracking-param stripping, host/scheme
normalization, slash and fragment rules) feeds a SHA-256 `url_hash` with a
unique index on `crawl_urls`. The same page discovered via sitemap, RSS, and
section links exists exactly once in the frontier. Cost: free (index insert).

## Stage 1 — Exact content hash

`content_hash = SHA-256(normalized(title | author | published_at | body))`,
computed in the cleaning worker after Unicode normalization (NFC — Bangla
matra sequences compare correctly). An identical republish (syndication,
URL variants that normalization missed) is marked `duplicate` and never
reaches LLM/embedding stages. Cost: one indexed lookup.

## Stage 2 — SimHash near-duplicates

64-bit SimHash over word 2-gram shingles of `title + body`
(`newscrawl_crawler_utils.simhash`). Stored as signed `bigint` on
`articles.simhash` with **four 16-bit banded expression indexes** — by the
pigeonhole principle any pair within Hamming distance ≤ 3 shares at least one
exact band, so candidate lookup is four indexed equality probes instead of a
table scan. Candidates are verified with a real Hamming distance check:

- distance ≤ 3 → near-duplicate (minor edits, timestamp updates) → marked
  `duplicate_of`
- distance 4–6 → "gray zone" → escalated to stage 3
- distance > 6 → distinct

## Stage 3 — Semantic (embedding) verification

Only for gray-zone candidates: cosine similarity between BGE-M3 vectors
(computed anyway for search) decides rewrites-of-the-same-story
(similarity ≥ 0.92 → `duplicate_of`). This never runs on unrelated pairs, so
the expensive model comparison stays rare. Cross-language near-duplicates
(BBC English vs BBC Bangla covering the same event) intentionally are **not**
collapsed — they are distinct articles linked via similarity search instead.

## Properties

- Duplicates are *marked* (`articles.duplicate_of`), never deleted — the API
  excludes them by default (`include_duplicates=false`) but they remain
  queryable and reversible.
- Every stage is idempotent; re-running dedup on the same corpus converges.
- Tested in `apps/processor/tests/test_dedup_integration.py` and
  `packages/crawler-utils/tests/test_simhash.py`.
