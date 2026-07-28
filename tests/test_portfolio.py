import unittest

from beta_backtest.portfolio import Candidate, equal_weight_top_candidates


class PortfolioTests(unittest.TestCase):
    def test_enforces_the_five_stock_limit(self) -> None:
        candidates = [
            Candidate(symbol=f"S{number}", score=float(number))
            for number in range(10)
        ]
        allocations = equal_weight_top_candidates(candidates, max_positions=5)
        self.assertEqual(len(allocations), 5)
        self.assertAlmostEqual(sum(item.weight for item in allocations), 1.0)
        self.assertEqual([item.symbol for item in allocations], ["S9", "S8", "S7", "S6", "S5"])

    def test_rejects_duplicate_symbols(self) -> None:
        with self.assertRaises(ValueError):
            equal_weight_top_candidates(
                [Candidate("2330", 1), Candidate("2330", 0.5)]
            )


if __name__ == "__main__":
    unittest.main()
