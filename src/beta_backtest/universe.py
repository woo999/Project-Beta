"""Load and validate point-in-time constituent membership records."""

import csv
from dataclasses import dataclass
from datetime import date
from pathlib import Path

from .point_in_time import UniverseMembership


REQUIRED_COLUMNS = {
    "symbol",
    "effective_from",
    "effective_to",
    "announced_on",
    "source_url",
}


@dataclass(frozen=True)
class MembershipEvidence:
    membership: UniverseMembership
    announced_on: date
    source_url: str


def load_membership_csv(path: str | Path) -> list[MembershipEvidence]:
    """Load an auditable constituent-history CSV and reject malformed records."""
    with Path(path).open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        if reader.fieldnames is None or set(reader.fieldnames) != REQUIRED_COLUMNS:
            raise ValueError(
                "CSV columns must be exactly: " + ", ".join(sorted(REQUIRED_COLUMNS))
            )
        records = [_parse_record(row) for row in reader]
    _validate_non_overlapping(records)
    return records


def _parse_record(row: dict[str, str]) -> MembershipEvidence:
    try:
        effective_from = date.fromisoformat(row["effective_from"])
        effective_to = (
            date.fromisoformat(row["effective_to"]) if row["effective_to"] else None
        )
        announced_on = date.fromisoformat(row["announced_on"])
    except ValueError as error:
        raise ValueError("dates must use YYYY-MM-DD") from error
    if not row["symbol"] or not row["source_url"]:
        raise ValueError("symbol and source_url are required")
    if announced_on > effective_from:
        raise ValueError("announced_on cannot be after effective_from")
    if effective_to is not None and effective_to < effective_from:
        raise ValueError("effective_to cannot precede effective_from")
    return MembershipEvidence(
        membership=UniverseMembership(
            symbol=row["symbol"],
            effective_from=effective_from,
            effective_to=effective_to,
        ),
        announced_on=announced_on,
        source_url=row["source_url"],
    )


def _validate_non_overlapping(records: list[MembershipEvidence]) -> None:
    by_symbol: dict[str, list[UniverseMembership]] = {}
    for record in records:
        by_symbol.setdefault(record.membership.symbol, []).append(record.membership)
    for symbol, memberships in by_symbol.items():
        ordered = sorted(memberships, key=lambda item: item.effective_from)
        for previous, current in zip(ordered, ordered[1:]):
            if previous.effective_to is None or current.effective_from <= previous.effective_to:
                raise ValueError(f"overlapping membership periods for {symbol}")
