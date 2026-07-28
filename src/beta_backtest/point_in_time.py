"""Reject signals that would use unavailable information."""

from dataclasses import dataclass
from datetime import date


class BacktestGuardError(ValueError):
    """Raised when a proposed trade violates a point-in-time rule."""


@dataclass(frozen=True)
class UniverseMembership:
    symbol: str
    effective_from: date
    effective_to: date | None = None

    def contains(self, on_date: date) -> bool:
        return self.effective_from <= on_date and (
            self.effective_to is None or on_date <= self.effective_to
        )


def validate_execution(
    *,
    signal_date: date,
    execution_date: date,
    membership: UniverseMembership,
) -> None:
    """Validate the minimum timing rules for a proposed simulated trade.

    Signals are observed after the signal-date close. A same-day fill is
    therefore prohibited. The selected stock must already belong to the
    historical universe on the signal date and on the simulated execution date.
    """
    if execution_date <= signal_date:
        raise BacktestGuardError(
            "execution must occur after the signal-date close"
        )
    if not membership.contains(signal_date):
        raise BacktestGuardError(
            "symbol was not in the historical universe on the signal date"
        )
    if not membership.contains(execution_date):
        raise BacktestGuardError(
            "symbol was not in the historical universe on the execution date"
        )
