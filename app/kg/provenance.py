"""Provenance attached to every graph fact."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Literal

from pydantic import BaseModel, Field

Method = Literal["rule", "model", "human"]


class Provenance(BaseModel):
    source: str = Field(description="Where the fact came from, e.g. 'seed:family_a', 'onboarding', 'api'")
    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    method: Method = "human"


def human(source: str, confidence: float = 1.0) -> Provenance:
    return Provenance(source=source, method="human", confidence=confidence)


def rule(source: str, confidence: float = 1.0) -> Provenance:
    return Provenance(source=source, method="rule", confidence=confidence)
