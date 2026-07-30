import tempfile
import unittest
from datetime import date
from pathlib import Path

from beta_backtest.review_events import (
    ReviewEvent,
    apply_review_events,
    load_baseline_snapshot_csv,
    load_review_events_csv,
    reconstruct_membership_timeline,
    validate_balanced_reviews,
    validate_snapshot_match,
    validate_universe_sizes,
)


SOURCE = "https://taiwanindex.com.tw/news/example"


class ReviewEventTests(unittest.TestCase):
    def test_accepts_exact_snapshot_match(self) -> None:
        state = {
            "TW50": {f"T{i:03d}" for i in range(50)},
            "TWMC100": {f"M{i:03d}" for i in range(100)},
        }
        validate_snapshot_match(state, state)

    def test_reports_snapshot_membership_difference(self) -> None:
        observed = {
            "TW50": {f"T{i:03d}" for i in range(50)},
            "TWMC100": {f"M{i:03d}" for i in range(100)},
        }
        reconstructed = {
            "TW50": (observed["TW50"] - {"T000"}) | {"T999"},
            "TWMC100": set(observed["TWMC100"]),
        }
        with self.assertRaisesRegex(
            ValueError, r"missing=\['T000'\].*unexpected=\['T999'\]"
        ):
            validate_snapshot_match(reconstructed, observed)

    def test_reconstructs_and_validates_membership_timeline(self) -> None:
        baseline = {
            "TW50": {f"T{i:03d}" for i in range(50)},
            "TWMC100": {f"M{i:03d}" for i in range(100)},
        }
        timeline = reconstruct_membership_timeline(
            date(2025, 1, 2),
            baseline,
            [
                self.event(symbol="T000", action="remove"),
                self.event(symbol="T999", action="add"),
            ],
        )

        self.assertNotIn("T000", timeline[date(2025, 6, 23)]["TW50"])
        self.assertIn("T999", timeline[date(2025, 6, 23)]["TW50"])

    def test_rejects_event_not_after_baseline(self) -> None:
        baseline = {
            "TW50": {f"T{i:03d}" for i in range(50)},
            "TWMC100": {f"M{i:03d}" for i in range(100)},
        }
        with self.assertRaisesRegex(ValueError, "after baseline"):
            reconstruct_membership_timeline(
                date(2025, 6, 23),
                baseline,
                [self.event(symbol="T000", action="remove")],
            )

    def test_loads_complete_baseline_snapshot(self) -> None:
        rows = [
            "universe,symbol,as_of,source_url",
            *[
                f"TW50,T{i:03d},2025-01-02,{SOURCE}"
                for i in range(50)
            ],
            *[
                f"TWMC100,M{i:03d},2025-01-02,{SOURCE}"
                for i in range(100)
            ],
        ]
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "snapshot.csv"
            path.write_text("\n".join(rows) + "\n", encoding="utf-8")
            as_of, state = load_baseline_snapshot_csv(path)

        self.assertEqual(as_of, date(2025, 1, 2))
        self.assertEqual(len(state["TW50"]), 50)
        self.assertEqual(len(state["TWMC100"]), 100)

    def test_rejects_incomplete_baseline_snapshot(self) -> None:
        rows = [
            "universe,symbol,as_of,source_url",
            *[
                f"TW50,T{i:03d},2025-01-02,{SOURCE}"
                for i in range(49)
            ],
            *[
                f"TWMC100,M{i:03d},2025-01-02,{SOURCE}"
                for i in range(100)
            ],
        ]
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "snapshot.csv"
            path.write_text("\n".join(rows) + "\n", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "TW50 must contain 50"):
                load_baseline_snapshot_csv(path)

    def test_validates_expected_universe_sizes(self) -> None:
        validate_universe_sizes(
            {
                "TW50": {f"T{i:03d}" for i in range(50)},
                "TWMC100": {f"M{i:03d}" for i in range(100)},
            }
        )

    def test_rejects_universe_size_drift(self) -> None:
        with self.assertRaisesRegex(ValueError, "TW50 must contain 50"):
            validate_universe_sizes(
                {
                    "TW50": {f"T{i:03d}" for i in range(49)},
                    "TWMC100": {f"M{i:03d}" for i in range(100)},
                }
            )

    def event(
        self,
        *,
        universe: str = "TW50",
        symbol: str = "2383",
        action: str = "add",
        announced_on: date = date(2025, 6, 6),
        effective_on: date = date(2025, 6, 23),
    ) -> ReviewEvent:
        return ReviewEvent(
            universe=universe,
            symbol=symbol,
            action=action,  # type: ignore[arg-type]
            announced_on=announced_on,
            effective_on=effective_on,
            source_url=SOURCE,
        )

    def test_does_not_apply_announced_but_not_effective_change(self) -> None:
        state = apply_review_events(
            {"TW50": {"3037"}},
            [self.event(symbol="3037", action="remove")],
            as_of=date(2025, 6, 20),
        )
        self.assertEqual(state["TW50"], {"3037"})

    def test_applies_add_and_remove_on_effective_date(self) -> None:
        state = apply_review_events(
            {"TW50": {"3037"}},
            [
                self.event(symbol="3037", action="remove"),
                self.event(symbol="2383", action="add"),
            ],
            as_of=date(2025, 6, 23),
        )
        self.assertEqual(state["TW50"], {"2383"})

    def test_rejects_removal_of_non_member(self) -> None:
        with self.assertRaises(ValueError):
            apply_review_events(
                {"TW50": set()},
                [self.event(action="remove")],
                as_of=date(2025, 6, 23),
            )

    def test_rejects_late_announcement(self) -> None:
        with self.assertRaises(ValueError):
            apply_review_events(
                {"TW50": set()},
                [
                    self.event(
                        announced_on=date(2025, 6, 24),
                        effective_on=date(2025, 6, 23),
                    )
                ],
                as_of=date(2025, 6, 24),
            )

    def test_loads_strict_review_event_csv(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "events.csv"
            path.write_text(
                "universe,symbol,action,announced_on,effective_on,source_url\n"
                "TW50,2383,add,2025-06-06,2025-06-23,"
                "https://taiwanindex.com.tw/news/362\n",
                encoding="utf-8",
            )
            events = load_review_events_csv(path)
        self.assertEqual(events[0].symbol, "2383")

    def test_rejects_duplicate_review_event(self) -> None:
        row = (
            "TW50,2383,add,2025-06-06,2025-06-23,"
            "https://taiwanindex.com.tw/news/362\n"
        )
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "events.csv"
            path.write_text(
                "universe,symbol,action,announced_on,effective_on,source_url\n"
                + row
                + row,
                encoding="utf-8",
            )
            with self.assertRaises(ValueError):
                load_review_events_csv(path)

    def test_accepts_balanced_review_batch(self) -> None:
        validate_balanced_reviews(
            [
                self.event(symbol="2383", action="add"),
                self.event(symbol="3037", action="remove"),
            ]
        )

    def test_rejects_incomplete_review_batch(self) -> None:
        with self.assertRaises(ValueError):
            validate_balanced_reviews([self.event(symbol="2383", action="add")])


if __name__ == "__main__":
    unittest.main()
