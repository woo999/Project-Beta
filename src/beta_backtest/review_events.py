"""Apply official index review events without leaking future membership."""

from dataclasses import dataclass
from datetime import date
from typing import Iterable, Literal

from .universe import SUPPORTED_UNIVERSES


ReviewAction = Literal["add", "remove"]


@dataclass(frozen=True)
class ReviewEvent:
    universe: str
    symbol: str
    action: ReviewAction
    announced_on: date
    effective_on: date
    source_url: str


def apply_review_events(
    baseline: dict[str, set[str]],
    events: Iterable[ReviewEvent],
    as_of: date,
) -> dict[str, set[str]]:
    """Return memberships known and effective as of ``as_of``.

    Events announced after ``as_of`` are invisible. Events announced on time but
    not yet effective are also excluded. Inputs are copied so the baseline remains
    an immutable audit anchor.
    """
    state = {universe: set(symbols) for universe, symbols in baseline.items()}
    for universe in SUPPORTED_UNIVERSES:
        state.setdefault(universe, set())

    ordered = sorted(events, key=lambda item: (item.effective_on, item.announced_on))
    for event in ordered:
        _validate_event(event)
        if event.announced_on > as_of or event.effective_on > as_of:
            continue
        members = state[event.universe]
        if event.action == "add":
            if event.symbol in members:
                raise ValueError(
                    f"duplicate add for {event.universe}/{event.symbol}"
                )
            members.add(event.symbol)
        else:
            if event.symbol not in members:
                raise ValueError(
                    f"remove of non-member {event.universe}/{event.symbol}"
                )
            members.remove(event.symbol)
    return state


def _validate_event(event: ReviewEvent) -> None:
    if event.universe not in SUPPORTED_UNIVERSES:
        raise ValueError(f"unsupported universe: {event.universe}")
    if not event.symbol or not event.source_url:
        raise ValueError("symbol and source_url are required")
    if event.action not in {"add", "remove"}:
        raise ValueError("action must be add or remove")
    if event.announced_on > event.effective_on:
        raise ValueError("announcement cannot be after effective date")
