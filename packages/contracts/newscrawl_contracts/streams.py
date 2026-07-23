"""Redis Stream names and consumer-group constants."""

STREAM_CLEANING = "processing:cleaning"
STREAM_LLM = "processing:llm"
STREAM_EMBEDDING = "processing:embedding"
STREAM_DEAD_LETTER = "processing:dead-letter"

GROUP_PROCESSORS = "processors"

# Sorted set holding delayed retries: member = stream|payload, score = due ts
DELAYED_JOBS_KEY = "processing:delayed"

# Worker heartbeats: hash worker_id → json payload
HEARTBEAT_KEY = "workers:heartbeats"

# Pub/sub channel for control signals (pause/resume/cancel)
CONTROL_CHANNEL = "control:signals"

# Per-domain politeness token bucket key prefix
RATE_LIMIT_PREFIX = "ratelimit:domain:"
