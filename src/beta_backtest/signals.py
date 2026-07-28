"""Deterministic prototype signals for Beta research hypotheses."""

from dataclasses import dataclass
from datetime import date
from typing import Sequence


@dataclass(frozen=True)
class DailyBar:
    on_date: date
    high: float
    low: float
    close: float


@dataclass(frozen=True)
class BreakoutPullbackSignal:
    signal_date: date
    breakout_level: float
    reason: str


def breakout_pullback_holds(
    bars: Sequence[DailyBar],
    *,
    breakout_lookback: int = 55,
    pullback_window: int = 15,
    tolerance: float = 0.02,
) -> BreakoutPullbackSignal | None:
    """Return a confirmed pullback signal using only supplied daily bars.

    The last bar is the signal-date close. A prior bar must first close above
    the previous breakout-lookback highs. The final bar must occur within the
    pullback window, trade no more than tolerance below that breakout level,
    and close back at or above the level.
    """
    if breakout_lookback < 1 or pullback_window < 1:
        raise ValueError("lookbacks must be positive")
    if not 0 <= tolerance < 1:
        raise ValueError("tolerance must be in [0, 1)")
    if len(bars) < breakout_lookback + 2:
        return None

    latest = bars[-1]
    first_breakout_index = len(bars) - pullback_window - 1
    first_breakout_index = max(first_breakout_index, breakout_lookback)
    for index in range(first_breakout_index, len(bars) - 1):
        prior_high = max(bar.high for bar in bars[index - breakout_lookback:index])
        breakout_bar = bars[index]
        if breakout_bar.close <= prior_high:
            continue
        if latest.low < prior_high * (1 - tolerance):
            continue
        if latest.close < prior_high:
            continue
        return BreakoutPullbackSignal(
            signal_date=latest.on_date,
            breakout_level=prior_high,
            reason="breakout pullback held and recovered at close",
        )
    return None


def momentum_return(closes: Sequence[float], *, lookback: int) -> float | None:
    """Return trailing close-to-close momentum with no forward observations."""
    if lookback < 1:
        raise ValueError("lookback must be positive")
    if len(closes) <= lookback:
        return None
    start = closes[-(lookback + 1)]
    end = closes[-1]
    if start <= 0 or end <= 0:
        raise ValueError("close values must be positive")
    return end / start - 1
