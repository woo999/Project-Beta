"""Trading-cost model for long-only Taiwan equity research."""

from dataclasses import dataclass


@dataclass(frozen=True)
class CostAssumptions:
    """Explicit, reproducible assumptions for one simulated trade."""

    brokerage_rate: float
    slippage_rate: float
    stock_sell_tax_rate: float = 0.003


def round_trip_cost(
    entry_value: float,
    exit_value: float,
    assumptions: CostAssumptions,
) -> float:
    """Return costs for a long stock round trip.

    Brokerage and slippage are charged on both sides.  The stock transaction tax
    is charged only on the sell side.  This project models swing trades, so it
    deliberately does not apply the intraday-trading tax concession.
    """
    if entry_value <= 0 or exit_value <= 0:
        raise ValueError("entry_value and exit_value must be positive")
    if min(
        assumptions.brokerage_rate,
        assumptions.slippage_rate,
        assumptions.stock_sell_tax_rate,
    ) < 0:
        raise ValueError("cost rates must be non-negative")

    traded_value = entry_value + exit_value
    brokerage = traded_value * assumptions.brokerage_rate
    slippage = traded_value * assumptions.slippage_rate
    sell_tax = exit_value * assumptions.stock_sell_tax_rate
    return brokerage + slippage + sell_tax
