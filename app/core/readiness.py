"""Family readiness score (0-100) with a transparent breakdown.

Each category has a maximum. Every open gap deducts points by severity, capped at the
category maximum. "What if I fix it?" is answered by recomputing without that gap.
"""

from __future__ import annotations

from pydantic import BaseModel

from app.core.gaps import Gap

CATEGORIES: dict[str, tuple[str, int]] = {
    "nominees": ("Nominees are recorded and valid", 35),
    "guardianship": ("Minors have guardians", 15),
    "documents": ("Papers can be found", 20),
    "knowledge": ("More than one person knows", 20),
    "deadlines": ("No deadlines slipping", 10),
    "liabilities": ("Loans are covered (information only)", 0),
}
PENALTY = {"critical": 15, "high": 8, "medium": 4, "low": 2, "info": 0}


class CategoryScore(BaseModel):
    category: str
    label: str
    max_points: int
    lost: int
    earned: int
    gap_keys: list[str]


class GapImpact(BaseModel):
    key: str
    points_if_fixed: int


class Readiness(BaseModel):
    score: int
    band: str
    categories: list[CategoryScore]
    impacts: list[GapImpact]
    explanation: str


def _score(gaps: list[Gap]) -> tuple[int, list[CategoryScore]]:
    cats = []
    for cat, (label, mx) in CATEGORIES.items():
        mine = [g for g in gaps if g.category == cat]
        lost = min(mx, sum(PENALTY[g.severity] for g in mine))
        cats.append(CategoryScore(category=cat, label=label, max_points=mx, lost=lost, earned=mx - lost,
                                  gap_keys=[g.key for g in mine]))
    return sum(c.earned for c in cats), cats


def band(score: int) -> str:
    if score >= 85:
        return "Well prepared"
    if score >= 65:
        return "Mostly prepared"
    if score >= 40:
        return "Some important gaps"
    return "At risk"


def readiness(gaps: list[Gap]) -> Readiness:
    score, cats = _score(gaps)
    impacts = []
    for g in gaps:
        without, _ = _score([x for x in gaps if x.key != g.key])
        impacts.append(GapImpact(key=g.key, points_if_fixed=without - score))
    impacts.sort(key=lambda i: (-i.points_if_fixed, i.key))
    return Readiness(
        score=score, band=band(score), categories=cats, impacts=impacts,
        explanation="Start at 100. Each open gap deducts points by severity (critical 15, high 8, medium 4, "
                    "low 2, info 0), capped per category. Fixing a gap gives back the points shown.",
    )
