"""Deterministic position limits for paper and historical portfolios."""

from dataclasses import dataclass
from typing import Sequence


@dataclass(frozen=True)
class Candidate:
    symbol: str
    score: float


@dataclass(frozen=True)
class Allocation:
    symbol: str
    weight: float
    score: float


def equal_weight_top_candidates(
    candidates: Sequence[Candidate], *, max_positions: int = 5
) -> list[Allocation]:
    """Select at most max_positions unique candidates with equal weights."""
    if max_positions < 1:
        raise ValueError("max_positions must be positive")
    if len({candidate.symbol for candidate in candidates}) != len(candidates):
        raise ValueError("candidates must contain unique symbols")

    selected = sorted(candidates, key=lambda item: (-item.score, item.symbol))[
        :max_positions
    ]
    if not selected:
        return []
    weight = 1 / len(selected)
    return [
        Allocation(symbol=item.symbol, weight=weight, score=item.score)
        for item in selected
    ]
