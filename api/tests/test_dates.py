"""The date grammar, rule by rule (requirements 3.3)."""

from datetime import date

import pytest

from app.dates.grammar import parse

D = date
DAY, MONTH, YEAR, DECADE, APPROX = "day", "month", "year", "decade", "approximate"

CASES = [
    # 1. ISO dates and datetimes: a single day.
    ("1968-07-16", D(1968, 7, 16), D(1968, 7, 16), DAY, "July 16, 1968"),
    ("1968-07-16T10:30:00", D(1968, 7, 16), D(1968, 7, 16), DAY, "July 16, 1968"),
    ("1968-07-16T10:30:00Z", D(1968, 7, 16), D(1968, 7, 16), DAY, "July 16, 1968"),
    ("1968/07/16", D(1968, 7, 16), D(1968, 7, 16), DAY, "July 16, 1968"),
    # 2. Explicit formats, with or without ordinals; a month alone is the whole month.
    ("7/16/1968", D(1968, 7, 16), D(1968, 7, 16), DAY, "July 16, 1968"),
    ("07/04/1976", D(1976, 7, 4), D(1976, 7, 4), DAY, "July 4, 1976"),
    ("Jul 16, 1968", D(1968, 7, 16), D(1968, 7, 16), DAY, "July 16, 1968"),
    ("July 16 1968", D(1968, 7, 16), D(1968, 7, 16), DAY, "July 16, 1968"),
    ("16 July 1968", D(1968, 7, 16), D(1968, 7, 16), DAY, "July 16, 1968"),
    ("16th July 1968", D(1968, 7, 16), D(1968, 7, 16), DAY, "July 16, 1968"),
    ("July 16th, 1968", D(1968, 7, 16), D(1968, 7, 16), DAY, "July 16, 1968"),
    ("the 1st of May 1945", D(1945, 5, 1), D(1945, 5, 1), DAY, "May 1, 1945"),
    ("May 1st, 1945", D(1945, 5, 1), D(1945, 5, 1), DAY, "May 1, 1945"),
    ("Sept. 3, 2001", D(2001, 9, 3), D(2001, 9, 3), DAY, "September 3, 2001"),
    (
        "on December 25, 1974",
        D(1974, 12, 25),
        D(1974, 12, 25),
        DAY,
        "December 25, 1974",
    ),
    ("Feb 29, 2000", D(2000, 2, 29), D(2000, 2, 29), DAY, "February 29, 2000"),
    ("July 1968", D(1968, 7, 1), D(1968, 7, 31), MONTH, "July 1968"),
    ("Feb 1900", D(1900, 2, 1), D(1900, 2, 28), MONTH, "February 1900"),
    ("february 2000", D(2000, 2, 1), D(2000, 2, 29), MONTH, "February 2000"),
    ("1968-07", D(1968, 7, 1), D(1968, 7, 31), MONTH, "July 1968"),
    ("7/1968", D(1968, 7, 1), D(1968, 7, 31), MONTH, "July 1968"),
    ("in March, 1951", D(1951, 3, 1), D(1951, 3, 31), MONTH, "March 1951"),
    # 3. Day ranges within a month and across months.
    ("July 16 to 18, 1968", D(1968, 7, 16), D(1968, 7, 18), DAY, "July 16 to 18, 1968"),
    ("July 16-18, 1968", D(1968, 7, 16), D(1968, 7, 18), DAY, "July 16 to 18, 1968"),
    ("July 16–18, 1968", D(1968, 7, 16), D(1968, 7, 18), DAY, "July 16 to 18, 1968"),
    (
        "July 16 to August 2, 1968",
        D(1968, 7, 16),
        D(1968, 8, 2),
        DAY,
        "July 16 to August 2, 1968",
    ),
    ("16 to 18 July 1968", D(1968, 7, 16), D(1968, 7, 18), DAY, "July 16 to 18, 1968"),
    ("July 18 to 16, 1968", D(1968, 7, 16), D(1968, 7, 18), DAY, "July 16 to 18, 1968"),
    ("April 10-12, 2026", D(2026, 4, 10), D(2026, 4, 12), DAY, "April 10 to 12, 2026"),
    # 4. Year ranges, with every separator; reversed ranges are put right.
    ("1998 to 2002", D(1998, 1, 1), D(2002, 12, 31), YEAR, "1998 to 2002"),
    ("1998-2002", D(1998, 1, 1), D(2002, 12, 31), YEAR, "1998 to 2002"),
    ("1998 – 2002", D(1998, 1, 1), D(2002, 12, 31), YEAR, "1998 to 2002"),
    ("1998—2002", D(1998, 1, 1), D(2002, 12, 31), YEAR, "1998 to 2002"),
    ("1998 through 2002", D(1998, 1, 1), D(2002, 12, 31), YEAR, "1998 to 2002"),
    ("1998 until 2002", D(1998, 1, 1), D(2002, 12, 31), YEAR, "1998 to 2002"),
    ("from 1998 to 2002", D(1998, 1, 1), D(2002, 12, 31), YEAR, "1998 to 2002"),
    ("between 1998 and 2002", D(1998, 1, 1), D(2002, 12, 31), YEAR, "1998 to 2002"),
    ("2002 to 1998", D(1998, 1, 1), D(2002, 12, 31), YEAR, "2002 to 1998"),
    (
        "July 1968 to March 1969",
        D(1968, 7, 1),
        D(1969, 3, 31),
        MONTH,
        "July 1968 to March 1969",
    ),
    (
        "spring 1968 to fall 1969",
        D(1968, 3, 1),
        D(1969, 11, 30),
        APPROX,
        "Spring 1968 to Fall 1969",
    ),
    ("1990 to 1999-06", D(1990, 1, 1), D(1999, 6, 30), APPROX, "1990 to June 1999"),
    # 5. Seasons, winter crossing into the next year.
    ("summer 1968", D(1968, 6, 1), D(1968, 8, 31), APPROX, "Summer 1968"),
    ("Spring 1968", D(1968, 3, 1), D(1968, 5, 31), APPROX, "Spring 1968"),
    ("fall 1968", D(1968, 9, 1), D(1968, 11, 30), APPROX, "Fall 1968"),
    ("autumn of 1968", D(1968, 9, 1), D(1968, 11, 30), APPROX, "Autumn 1968"),
    ("winter 1999", D(1999, 12, 1), D(2000, 2, 29), APPROX, "Winter 1999"),
    ("winter 1998", D(1998, 12, 1), D(1999, 2, 28), APPROX, "Winter 1998"),
    ("the summer of 1968", D(1968, 6, 1), D(1968, 8, 31), APPROX, "Summer 1968"),
    # 6. Decades.
    ("the 1960s", D(1960, 1, 1), D(1969, 12, 31), DECADE, "the 1960s"),
    ("1960s", D(1960, 1, 1), D(1969, 12, 31), DECADE, "the 1960s"),
    ("the 1960's", D(1960, 1, 1), D(1969, 12, 31), DECADE, "the 1960s"),
    ("the '60s", D(1960, 1, 1), D(1969, 12, 31), DECADE, "the 1960s"),
    ("the 60s", D(1960, 1, 1), D(1969, 12, 31), DECADE, "the 1960s"),
    ("the early 1960s", D(1960, 1, 1), D(1963, 12, 31), DECADE, "the early 1960s"),
    ("mid-1960s", D(1963, 1, 1), D(1966, 12, 31), DECADE, "the mid 1960s"),
    ("the late 1960s", D(1966, 1, 1), D(1969, 12, 31), DECADE, "the late 1960s"),
    ("the 1850s", D(1850, 1, 1), D(1859, 12, 31), DECADE, "the 1850s"),
    ("the 2010s", D(2010, 1, 1), D(2019, 12, 31), DECADE, "the 2010s"),
    # 7. A bare year anywhere in the text; "around" makes it approximate.
    ("1968", D(1968, 1, 1), D(1968, 12, 31), YEAR, "1968"),
    ("Christmas 1974", D(1974, 1, 1), D(1974, 12, 31), YEAR, "1974"),
    ("we moved to Erie in 1968", D(1968, 1, 1), D(1968, 12, 31), YEAR, "1968"),
    ("1850", D(1850, 1, 1), D(1850, 12, 31), YEAR, "1850"),
    ("2099", D(2099, 1, 1), D(2099, 12, 31), YEAR, "2099"),
    ("around 1950", D(1950, 1, 1), D(1950, 12, 31), APPROX, "around 1950"),
    ("circa 1950", D(1950, 1, 1), D(1950, 12, 31), APPROX, "around 1950"),
    ("c. 1950", D(1950, 1, 1), D(1950, 12, 31), APPROX, "around 1950"),
    ("about the 1940s", D(1940, 1, 1), D(1949, 12, 31), APPROX, "around the 1940s"),
    # Nonsense, and years outside 1850 to 2099, give nothing.
    ("sometime", None, None, None, None),
    ("when I was young", None, None, None, None),
    ("", None, None, None, None),
    ("   ", None, None, None, None),
    ("1849", None, None, None, None),
    ("2100", None, None, None, None),
    ("Feb 30, 2000", None, None, None, None),
    ("13/40/1999", None, None, None, None),
    ("the 20s", None, None, None, None),
    ("chapter 12", None, None, None, None),
]


def test_there_are_at_least_sixty_cases():
    assert len(CASES) >= 60


@pytest.mark.parametrize(
    "text,start,end,precision,reading", CASES, ids=[c[0] or "empty" for c in CASES]
)
def test_reading(text, start, end, precision, reading):
    found = parse(text)
    if start is None:
        assert found is None, found
        return
    assert found is not None
    assert (found.start, found.end, found.precision, found.reading) == (
        start,
        end,
        precision,
        reading,
    )
