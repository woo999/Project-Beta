import tempfile
import unittest
from pathlib import Path

from beta_backtest.universe import load_membership_csv


HEADER = "symbol,effective_from,effective_to,announced_on,source_url\n"


class UniverseImportTests(unittest.TestCase):
    def write_csv(self, body: str) -> Path:
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        path = Path(directory.name) / "universe.csv"
        path.write_text(HEADER + body, encoding="utf-8")
        return path

    def test_loads_auditable_membership(self) -> None:
        path = self.write_csv(
            "2330,2024-01-02,2024-06-30,2023-12-15,https://example.test/review\n"
        )
        records = load_membership_csv(path)
        self.assertEqual(records[0].membership.symbol, "2330")

    def test_rejects_announcements_made_after_effective_date(self) -> None:
        path = self.write_csv(
            "2330,2024-01-02,,2024-01-03,https://example.test/review\n"
        )
        with self.assertRaises(ValueError):
            load_membership_csv(path)

    def test_rejects_overlapping_periods_for_the_same_symbol(self) -> None:
        path = self.write_csv(
            "2330,2024-01-02,2024-06-30,2023-12-15,https://example.test/one\n"
            "2330,2024-06-01,,2024-05-15,https://example.test/two\n"
        )
        with self.assertRaises(ValueError):
            load_membership_csv(path)


if __name__ == "__main__":
    unittest.main()
