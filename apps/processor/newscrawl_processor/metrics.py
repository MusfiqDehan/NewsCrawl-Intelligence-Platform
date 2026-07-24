"""Prometheus metrics for the processing plane.

Each worker entrypoint starts its own exporter (one process = one port):
cleaning 9102, LLM 9103, embedding 9104 — override with PROCESSOR_METRICS_PORT.
"""

import os
import time
from collections.abc import Iterator
from contextlib import contextmanager

from prometheus_client import Counter, Histogram, start_http_server

MESSAGES = Counter(
    "newscrawl_processor_messages_total",
    "Messages handled by processing workers",
    ["worker", "outcome"],
)
PROCESSING_DURATION = Histogram(
    "newscrawl_processor_duration_seconds",
    "Per-message processing time",
    ["worker"],
    buckets=(0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0, 30.0, 60.0),
)
LLM_TOKENS = Counter(
    "newscrawl_llm_tokens_total",
    "LLM tokens consumed",
    ["provider", "kind"],
)
LLM_COST = Counter(
    "newscrawl_llm_cost_usd_total",
    "Estimated LLM spend in USD",
    ["provider"],
)
EMBEDDINGS = Counter(
    "newscrawl_embeddings_total",
    "Embedding vectors written",
    ["kind"],
)
DUPLICATES = Counter(
    "newscrawl_duplicates_total",
    "Articles marked as duplicates",
    ["method"],
)

_DEFAULT_PORTS = {"cleaning": 9102, "llm": 9103, "embedding": 9104, "retention": 9105}


def start_metrics_server(worker: str) -> int:
    """Start the exporter for this worker process; returns the bound port."""
    port = int(os.environ.get("PROCESSOR_METRICS_PORT", _DEFAULT_PORTS.get(worker, 9102)))
    start_http_server(port)
    return port


@contextmanager
def track_duration(worker: str) -> Iterator[None]:
    started = time.perf_counter()
    try:
        yield
    finally:
        PROCESSING_DURATION.labels(worker=worker).observe(time.perf_counter() - started)
