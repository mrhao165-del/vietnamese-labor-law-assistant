"""Structured logging setup with bounded request metadata."""

from __future__ import annotations

import logging

import structlog

from .settings import Settings


def configure_logging(settings: Settings) -> None:
    """Configure stdlib and structlog processors once at application startup."""
    logging.basicConfig(level=getattr(logging, settings.log_level.upper(), logging.INFO))
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
        cache_logger_on_first_use=True,
    )


def question_preview(question: str, limit: int = 240) -> str:
    """Return a bounded question excerpt suitable for structured logs."""
    return question[:limit]
