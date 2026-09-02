"""app/dates.py — deterministic phrase -> date resolution.

Reference day pinned to Tuesday 2026-09-01 (the day the M3 accuracy probe
used). Sep 2026: Mon=7/14/21/28, Fri=4/11/18/25, Sun=6/13/20/27.
"""

from datetime import date

import pytest

from app.dates import resolve

TODAY = date(2026, 9, 1)  # Tuesday


@pytest.mark.parametrize(
    "phrase, expected",
    [
        # absolute
        ("2026-10-02", date(2026, 10, 2)),
        ("march 15", date(2027, 3, 15)),          # already past this year -> next
        ("december 25", date(2026, 12, 25)),
        ("mid october", date(2026, 10, 15)),
        ("5 october", date(2026, 10, 5)),
        ("the 15th", date(2026, 9, 15)),
        ("the 1st", date(2026, 9, 1)),            # today is the 1st
        ("the 2nd", date(2026, 9, 2)),
        # day offsets
        ("today", date(2026, 9, 1)),
        ("tomorrow", date(2026, 9, 2)),
        ("day after tomorrow", date(2026, 9, 3)),
        ("in two weeks", date(2026, 9, 15)),
        ("in 3 days", date(2026, 9, 4)),
        ("in a month", date(2026, 10, 1)),
        # weekdays — nearest upcoming
        ("friday", date(2026, 9, 4)),
        ("by friday", date(2026, 9, 4)),
        ("next monday", date(2026, 9, 7)),
        ("this friday", date(2026, 9, 4)),
        ("tuesday", date(2026, 9, 8)),            # today is Tue -> next Tue
        ("a week from thursday", date(2026, 9, 10)),
        # weeks / weekends / months
        ("end of next week", date(2026, 9, 13)),
        ("next week", date(2026, 9, 7)),
        ("this weekend", date(2026, 9, 5)),
        ("next weekend", date(2026, 9, 12)),
        ("end of the month", date(2026, 9, 30)),
        ("next month", date(2026, 10, 1)),
        ("end of next month", date(2026, 10, 31)),
        # unparseable
        ("whenever", None),
        ("", None),
        (None, None),
        (42, None),
    ],
)
def test_resolve(phrase, expected):
    assert resolve(phrase, TODAY) == expected


def test_prefix_stripping():
    assert resolve("due by end of next week", TODAY) == date(2026, 9, 13)
    assert resolve("  On   Friday.", TODAY) == date(2026, 9, 4)
