"""Apply official index review events without leaking future membership."""

import csv
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Collection, Iterable, Literal, Mapping

from .universe import SUPPORTED_UNIVERSES


ReviewAction = Literal["add", "remove"]
EVENT_COLUMNS = {
    "universe",
    "symbol",
    "action",
    "announced_on",
    "effective_on",
    "source_url",
}
SNAPSHOT_COLUMNS = {"universe", "symbol", "as_of", "source_url"}
EXPECTED_UNIVERSE_SIZES = {"TW50": 50, "TWMC100": 100}


@dataclass(frozen=True)
class ReviewEvent:
    universe: str
    symbol: str
    action: ReviewAction
    announced_on: date
    effective_on: date
    source_url: str


def load_baseline_snapshot_csv(
    path: str | Path,
) -> tuple[date, dict[str, set[str]]]:
    """Load a dated, sourced full constituent snapshot."""
    with Path(path).open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        if reader.fieldnames is None or set(reader.fieldnames) != SNAPSHOT_COLUMNS:
            raise ValueError(
                "snapshot CSV columns must be exactly: "
                + ", ".join(sorted(SNAPSHOT_COLUMNS))
            )
        rows = list(reader)

    dates: set[date] = set()
    state: dict[str, set[str]] = {}
    for row in rows:
        universe = row["universe"].strip().upper()
        symbol = row["symbol"].strip()
        source_url = row["source_url"].strip()
        if universe not in SUPPORTED_UNIVERSES:
            raise ValueError(f"unsupported universe: {universe}")
        if not symbol or not source_url:
            raise ValueError("symbol and source_url are required")
        try:
            dates.add(date.fromisoformat(row["as_of"]))
        except ValueError as error:
            raise ValueError("dates must use YYYY-MM-DD") from error
        members = state.setdefault(universe, set())
        if symbol in members:
            raise ValueError(f"duplicate snapshot member: {universe}/{symbol}")
        members.add(symbol)

    if len(dates) != 1:
        raise ValueError("snapshot rows must share exactly one as_of date")
    validate_universe_sizes(state)
    return dates.pop(), state


def load_review_events_csv(path: str | Path) -> list[ReviewEvent]:
    """Load auditable index-review deltas from a strict CSV schema."""
    with Path(path).open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        if reader.fieldnames is None or set(reader.fieldnames) != EVENT_COLUMNS:
            raise ValueError(
                "CSV columns must be exactly: " + ", ".join(sorted(EVENT_COLUMNS))
            )
        events = [_parse_event(row) for row in reader]
    if len(events) != len(
        {
            (event.universe, event.symbol, event.action, event.effective_on)
            for event in events
        }
    ):
        raise ValueError("duplicate review event")
    return events


def validate_balanced_reviews(events: Iterable[ReviewEvent]) -> None:
    """Reject incomplete review batches whose add/remove counts do not match."""
    counts: dict[tuple[str, date], dict[str, int]] = {}
    for event in events:
        _validate_event(event)
        bucket = counts.setdefault(
            (event.universe, event.effective_on), {"add": 0, "remove": 0}
        )
        bucket[event.action] += 1
    for (universe, effective_on), bucket in counts.items():
        if bucket["add"] != bucket["remove"]:
            raise ValueError(
                f"unbalanced review for {universe} on {effective_on}: "
                f"{bucket['add']} adds, {bucket['remove']} removes"
            )


def validate_universe_sizes(
    state: Mapping[str, Collection[str]],
    expected_sizes: Mapping[str, int] = EXPECTED_UNIVERSE_SIZES,
) -> None:
    """Reject incomplete or drifted constituent snapshots."""
    unknown = set(state) - set(expected_sizes)
    if unknown:
        raise ValueError(f"unknown universes in state: {sorted(unknown)}")

    for universe, expected_size in expected_sizes.items():
        if universe not in state:
            raise ValueError(f"missing universe in state: {universe}")
        actual_size = len(state[universe])
        if actual_size != expected_size:
            raise ValueError(
                f"{universe} must contain {expected_size} constituents, "
                f"got {actual_size}"
            )


def validate_snapshot_match(
    reconstructed: Mapping[str, Collection[str]],
    observed: Mapping[str, Collection[str]],
) -> None:
    """Require reconstructed membership to exactly match an observed snapshot."""
    validate_universe_sizes(reconstructed)
    validate_universe_sizes(observed)
    for universe in EXPECTED_UNIVERSE_SIZES:
        expected_members = set(observed[universe])
        actual_members = set(reconstructed[universe])
        missing = sorted(expected_members - actual_members)
        unexpected = sorted(actual_members - expected_members)
        if missing or unexpected:
            raise ValueError(
                f"snapshot mismatch for {universe}: "
                f"missing={missing}, unexpected={unexpected}"
            )


def _parse_event(row: dict[str, str]) -> ReviewEvent:
    try:
        event = ReviewEvent(
            universe=row["universe"].strip().upper(),
            symbol=row["symbol"].strip(),
            action=row["action"].strip().lower(),  # type: ignore[arg-type]
            announced_on=date.fromisoformat(row["announced_on"]),
            effective_on=date.fromisoformat(row["effective_on"]),
            source_url=row["source_url"].strip(),
        )
    except ValueError as error:
        raise ValueError("dates must use YYYY-MM-DD") from error
    _validate_event(event)
    return event


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


def reconstruct_membership_timeline(
    baseline_as_of: date,
    baseline: dict[str, set[str]],
    events: Iterable[ReviewEvent],
) -> dict[date, dict[str, set[str]]]:
    """Apply complete event batches and validate membership after every change."""
    validate_universe_sizes(baseline)
    batches: dict[date, list[ReviewEvent]] = {}
    for event in events:
        _validate_event(event)
        if event.effective_on <= baseline_as_of:
            raise ValueError("event effective date must be after baseline snapshot")
        batches.setdefault(event.effective_on, []).append(event)

    state = {universe: set(symbols) for universe, symbols in baseline.items()}
    timeline: dict[date, dict[str, set[str]]] = {}
    for effective_on in sorted(batches):
        batch = batches[effective_on]
        validate_balanced_reviews(batch)
        state = apply_review_events(state, batch, as_of=effective_on)
        validate_universe_sizes(state)
        timeline[effective_on] = {
            universe: set(symbols) for universe, symbols in state.items()
        }
    return timeline


def _validate_event(event: ReviewEvent) -> None:
    if event.universe not in SUPPORTED_UNIVERSES:
        raise ValueError(f"unsupported universe: {event.universe}")
    if not event.symbol or not event.source_url:
        raise ValueError("symbol and source_url are required")
    if event.action not in {"add", "remove"}:
        raise ValueError("action must be add or remove")
    if event.announced_on > event.effective_on:
        raise ValueError("announcement cannot be after effective date")
