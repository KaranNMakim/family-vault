"""Runtime settings, read from environment variables (all optional for the demo)."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

DEFAULT_AS_OF = "2026-11-01"


@dataclass(frozen=True)
class Settings:
    data_dir: Path = field(default_factory=lambda: Path(os.getenv("VAULT_DATA_DIR", ROOT / "data")))
    as_of: date = field(default_factory=lambda: date.fromisoformat(os.getenv("VAULT_AS_OF", DEFAULT_AS_OF)))
    llm_mode: str = field(default_factory=lambda: os.getenv("LLM_MODE", "mock"))
    llm_model: str = field(default_factory=lambda: os.getenv("ANTHROPIC_MODEL", "claude-sonnet-5-5"))
    # Days of look-ahead for "maturing / expiring soon" checks.
    expiry_window_days: int = field(default_factory=lambda: int(os.getenv("VAULT_EXPIRY_WINDOW_DAYS", "60")))
    # Emergency-access default waiting period (hours, simulated clock).
    emergency_wait_hours: int = field(default_factory=lambda: int(os.getenv("VAULT_EMERGENCY_WAIT_HOURS", "72")))
    cors_origins: tuple[str, ...] = ("http://localhost:3000", "http://127.0.0.1:3000")

    @property
    def vault_dir(self) -> Path:
        return self.data_dir / "vaults"

    @property
    def seed_dir(self) -> Path:
        return self.data_dir / "seed"


def get_settings() -> Settings:
    return Settings()
