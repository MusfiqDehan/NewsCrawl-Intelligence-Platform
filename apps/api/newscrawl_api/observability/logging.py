"""Structured JSON logging shared by every plane (api, crawler, processor).

Every log line carries: timestamp, level, service, worker_id (when bound),
event, plus any bound context (crawl_job_id, url, source, duration, error).
"""

import logging
import sys

import structlog


def configure_logging(
    service: str, level: str = "INFO", *, json_output: bool | None = None
) -> None:
    """Configure stdlib + structlog. JSON in containers/prod, pretty on a TTY."""
    if json_output is None:
        json_output = not sys.stderr.isatty()

    shared_processors: list[structlog.typing.Processor] = [
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_log_level,
        structlog.processors.TimeStamper(fmt="iso", utc=True),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.UnicodeDecoder(),
    ]

    renderer: structlog.typing.Processor
    if json_output:
        shared_processors.append(structlog.processors.format_exc_info)
        renderer = structlog.processors.JSONRenderer()
    else:
        renderer = structlog.dev.ConsoleRenderer()

    structlog.configure(
        processors=[*shared_processors, renderer],
        wrapper_class=structlog.make_filtering_bound_logger(
            getattr(logging, level.upper(), logging.INFO)
        ),
        logger_factory=structlog.PrintLoggerFactory(sys.stderr),
        cache_logger_on_first_use=True,
    )
    structlog.contextvars.bind_contextvars(service=service)

    logging.basicConfig(stream=sys.stderr, level=getattr(logging, level.upper(), logging.INFO))
    # Quieten noisy third-party loggers; our structured logs carry the signal.
    for noisy in ("uvicorn.access", "botocore", "boto3", "urllib3"):
        logging.getLogger(noisy).setLevel(logging.WARNING)


def get_logger(name: str | None = None) -> structlog.typing.FilteringBoundLogger:
    logger: structlog.typing.FilteringBoundLogger = (
        structlog.get_logger(name) if name else structlog.get_logger()
    )
    return logger
