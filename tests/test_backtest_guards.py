import unittest
from datetime import date

from beta_backtest.costs import CostAssumptions, round_trip_cost
from beta_backtest.point_in_time import (
    BacktestGuardError,
    UniverseMembership,
    validate_execution,
)


class CostModelTests(unittest.TestCase):
    def test_swing_trade_uses_full_stock_sell_tax(self) -> None:
        costs = round_trip_cost(
            entry_value=100_000,
            exit_value=110_000,
            assumptions=CostAssumptions(
                brokerage_rate=0.001,
                slippage_rate=0.0005,
            ),
        )
        self.assertEqual(costs, 210 + 105 + 330)


class PointInTimeGuardTests(unittest.TestCase):
    def setUp(self) -> None:
        self.membership = UniverseMembership(
            symbol="TEST",
            effective_from=date(2024, 1, 2),
            effective_to=date(2024, 12, 31),
        )

    def test_next_day_execution_is_allowed(self) -> None:
        validate_execution(
            signal_date=date(2024, 3, 1),
            execution_date=date(2024, 3, 4),
            membership=self.membership,
        )

    def test_same_day_execution_is_rejected(self) -> None:
        with self.assertRaises(BacktestGuardError):
            validate_execution(
                signal_date=date(2024, 3, 1),
                execution_date=date(2024, 3, 1),
                membership=self.membership,
            )

    def test_current_constituent_cannot_be_backfilled(self) -> None:
        future_membership = UniverseMembership(
            symbol="LATE",
            effective_from=date(2024, 6, 1),
        )
        with self.assertRaises(BacktestGuardError):
            validate_execution(
                signal_date=date(2024, 5, 31),
                execution_date=date(2024, 6, 3),
                membership=future_membership,
            )


if __name__ == "__main__":
    unittest.main()
