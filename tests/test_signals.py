import unittest
from datetime import date, timedelta

from beta_backtest.signals import DailyBar, breakout_pullback_holds, momentum_return


def bar(day: int, high: float, low: float, close: float) -> DailyBar:
    return DailyBar(date(2024, 1, 1) + timedelta(days=day), high, low, close)


class BreakoutPullbackTests(unittest.TestCase):
    def test_confirms_only_after_pullback_holds(self) -> None:
        history = [bar(day, 100, 95, 98) for day in range(55)]
        history += [
            bar(55, 106, 101, 103),
            bar(56, 104, 99, 101),
        ]
        signal = breakout_pullback_holds(
            history, breakout_lookback=55, pullback_window=15, tolerance=0.02
        )
        self.assertIsNotNone(signal)
        self.assertEqual(signal.breakout_level, 100)

    def test_rejects_a_break_of_the_pullback_tolerance(self) -> None:
        history = [bar(day, 100, 95, 98) for day in range(55)]
        history += [
            bar(55, 106, 101, 103),
            bar(56, 104, 97, 101),
        ]
        self.assertIsNone(
            breakout_pullback_holds(
                history, breakout_lookback=55, pullback_window=15, tolerance=0.02
            )
        )


class MomentumTests(unittest.TestCase):
    def test_uses_only_trailing_closes(self) -> None:
        self.assertAlmostEqual(
            momentum_return([100, 110, 121], lookback=2),
            0.21,
        )

    def test_requires_a_complete_lookback(self) -> None:
        self.assertIsNone(momentum_return([100, 110], lookback=2))


if __name__ == "__main__":
    unittest.main()
