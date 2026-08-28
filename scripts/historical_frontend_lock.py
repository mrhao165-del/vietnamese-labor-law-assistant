"""Git adapter for the immutable v1.0.0 frontend dependency-lock bytes."""

from __future__ import annotations

import subprocess
from pathlib import Path

from vietnamese_labor_law_assistant.evaluation.week12_portfolio import (
    HISTORICAL_FRONTEND_LOCK_PATH,
    HISTORICAL_FRONTEND_LOCK_REF,
    VersionedChecksumSource,
)


def read_historical_frontend_lock_source(root: Path) -> dict[str, VersionedChecksumSource]:
    """Read the exact tagged blob; evaluation code owns its allowlist and revision policy."""

    object_name = f"{HISTORICAL_FRONTEND_LOCK_REF}:{HISTORICAL_FRONTEND_LOCK_PATH}"
    try:
        result = subprocess.run(
            ["git", "cat-file", "blob", object_name],
            cwd=root,
            check=True,
            capture_output=True,
        )
    except (FileNotFoundError, subprocess.CalledProcessError) as exc:
        raise ValueError(f"historical checksum source is unavailable: {object_name}") from exc
    return {
        HISTORICAL_FRONTEND_LOCK_PATH: VersionedChecksumSource(
            revision=HISTORICAL_FRONTEND_LOCK_REF,
            content=result.stdout,
        )
    }
