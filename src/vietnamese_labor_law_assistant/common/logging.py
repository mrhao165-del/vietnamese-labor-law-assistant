"""Structured logging setup with bounded request metadata."""

from __future__ import annotations

import logging
from typing import TextIO

import structlog

from .settings import Settings


def configure_logging(settings: Settings, stream: TextIO | None = None) -> None:
    """Configure stdlib and structlog processors once at application startup."""
    logging.basicConfig(
        level=getattr(logging, settings.log_level.upper(), logging.INFO),
        stream=stream,
    )
    renderer = (
        structlog.processors.JSONRenderer()
        if settings.log_format == "json"
        else structlog.dev.ConsoleRenderer()
    )
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso", utc=True),
            renderer,
        ],
        wrapper_class=structlog.make_filtering_bound_logger(
            getattr(logging, settings.log_level.upper(), logging.INFO)
        ),
        logger_factory=structlog.PrintLoggerFactory(file=stream),
        cache_logger_on_first_use=True,
    )


def question_preview(question: str, limit: int = 240) -> str:
    """Return a bounded question excerpt suitable for structured logs."""
    return question[:limit]
