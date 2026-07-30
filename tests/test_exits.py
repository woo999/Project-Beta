import unittest
from datetime import date, timedelta

from beta_backtest.exits import swing_exit_signal
from beta_backtest.signals import DailyBar


def bars(closes):
    start = date(2026, 1, 1)
    return [
        DailyBar(start + timedelta(days=index), close, close, close)
        for index, close in enumerate(closes)
    ]


class SwingExitTests(unittest.TestCase):
    def test_exits_on_close_below_frozen_invalidation(self):
        signal = swing_exit_signal(bars([100, 98]), invalidation_level=99)
        self.assertEqual(signal.reason, "close below frozen invalidation level")

    def test_does_not_use_intraday_low_as_same_day_stop_fill(self):
        series = [
            DailyBar(date(2026, 1, 1), 101, 95, 100),
            DailyBar(date(2026, 1, 2), 102, 94, 101),
        ]
        self.assertIsNone(swing_exit_signal(series, invalidation_level=99))

    def test_exits_at_frozen_maximum_holding_period(self):
        signal = swing_exit_signal(
            bars([100] * 5),
            invalidation_level=90,
            max_holding_sessions=5,
        )
        self.assertEqual(signal.reason, "maximum holding period reached")

    def test_trend_exit_uses_only_prior_completed_closes(self):
        signal = swing_exit_signal(
            bars([100, 102, 104, 99]),
            invalidation_level=90,
            max_holding_sessions=10,
            trend_lookback=3,
        )
        self.assertEqual(signal.reason, "close below trailing trend average")


if __name__ == "__main__":
    unittest.main()
