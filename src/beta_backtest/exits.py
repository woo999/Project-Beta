"""Deterministic exit signals for swing-strategy research."""

from dataclasses import dataclass
from datetime import date
from typing import Sequence

from .signals import DailyBar


@dataclass(frozen=True)
class ExitSignal:
    signal_date: date
    reason: str


def swing_exit_signal(
    bars_since_entry: Sequence[DailyBar],
    *,
    invalidation_level: float,
    max_holding_sessions: int = 63,
    trend_lookback: int = 20,
) -> ExitSignal | None:
    """Return an exit signal using information available at the latest close.

    The caller must execute any returned signal no earlier than the next
    tradable session. Stops are evaluated on closing prices so an intraday low
    cannot be paired with an unknowable same-day fill.
    """
    if invalidation_level <= 0:
        raise ValueError("invalidation_level must be positive")
    if max_holding_sessions < 1 or trend_lookback < 1:
        raise ValueError("holding and trend windows must be positive")
    if not bars_since_entry:
        return None

    latest = bars_since_entry[-1]
    if latest.close < invalidation_level:
        return ExitSignal(latest.on_date, "close below frozen invalidation level")

    if len(bars_since_entry) >= max_holding_sessions:
        return ExitSignal(latest.on_date, "maximum holding period reached")

    if len(bars_since_entry) > trend_lookback:
        prior_closes = [bar.close for bar in bars_since_entry[-(trend_lookback + 1):-1]]
        if latest.close < sum(prior_closes) / trend_lookback:
            return ExitSignal(latest.on_date, "close below trailing trend average")

    return None
