from __future__ import annotations

import sys
import unittest
from pathlib import Path


COMPONENT_DIR = Path(__file__).resolve().parents[1] / "custom_components" / "casacop"
sys.path.insert(0, str(COMPONENT_DIR))

from media_id import (  # noqa: E402
    build_recording_identifier,
    candidate_archive_days,
    parse_recording_identifier,
)


class MediaIdentifierTests(unittest.TestCase):
    def test_candidate_days_are_newest_first_without_archive_search(self) -> None:
        import datetime as dt

        self.assertEqual(
            candidate_archive_days(dt.date(2026, 9, 12), 2),
            [dt.date(2026, 9, 12), dt.date(2026, 9, 11), dt.date(2026, 9, 10)],
        )

    def test_round_trip_path_identifier(self) -> None:
        identifier = build_recording_identifier(
            "entry-id", 0, 1, 1789167562, 1789167600, 0, "2026-09-12"
        )

        self.assertEqual(
            identifier,
            "FILE|entry-id|0|1|0/2026-09-12/1789167562-1789167600",
        )
        self.assertEqual(
            parse_recording_identifier(identifier),
            ("entry-id", 0, 1, 1789167562, 1789167600, 0),
        )

    def test_legacy_identifier_remains_playable(self) -> None:
        self.assertEqual(
            parse_recording_identifier("FILE|entry-id|0|1|1789167562|1789167600|0"),
            ("entry-id", 0, 1, 1789167562, 1789167600, 0),
        )

    def test_unrelated_identifier_is_rejected(self) -> None:
        with self.assertRaises(ValueError):
            parse_recording_identifier("DAY|entry-id|0|2026|9|12")


if __name__ == "__main__":
    unittest.main()
