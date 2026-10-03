"""Read a date the way a family says it: "July 16, 1968", "summer 1968", "the early
1960s", "1998 to 2002", "around 1950". Pure functions, no database.

`parse(text)` returns a `Reading` (start, end, precision, a plain reading of what it
understood) or None. The most specific reading wins: a day range before a single day, so
"July 16 to August 2, 1968" is never read as August 2 alone. Years run 1850 to 2099.
"""

import calendar
import re
from dataclasses import dataclass
from datetime import date

from app.domain.common import Precision

YEAR = r"(18[5-9]\d|19\d\d|20\d\d)"
MONTH_NAMES = {
    name: n
    for n in range(1, 13)
    for name in (calendar.month_name[n].lower(), calendar.month_abbr[n].lower())
}
MONTH_NAMES["sept"] = 9
MONTH = r"(" + "|".join(sorted(MONTH_NAMES, key=len, reverse=True)) + r")\.?"
SEP = r"\s*(?:-|to|through|thru|until|till|and)\s*"
SEASONS = {"spring": (3, 5), "summer": (6, 8), "fall": (9, 11), "autumn": (9, 11)}
NOW = re.compile(r"^(now|present|today|the present( day)?)$")
FUZZY = re.compile(r"^(around|about|circa|c\.?|approximately|approx\.?|maybe)\s+")


class Impossible(Exception):
    """Text shaped like a day that cannot exist (February 30): read as nothing, not as a
    year, so the person is asked rather than quietly misfiled."""


@dataclass(frozen=True)
class Reading:
    start: date
    end: date
    precision: Precision
    reading: str


def _month_end(year: int, month: int) -> date:
    return date(year, month, calendar.monthrange(year, month)[1])


def _day(y: int, m: int, d: int) -> date | None:
    try:
        return date(y, m, d)
    except ValueError:
        return None


def _fmt_day(d: date) -> str:
    return f"{calendar.month_name[d.month]} {d.day}, {d.year}"


def normalise(text: str) -> str:
    t = text.lower().replace("–", "-").replace("—", "-")
    t = re.sub(r"\b(\d{1,2})(st|nd|rd|th)\b", r"\1", t)
    t = re.sub(r"\b(between|from|in|on|during|the year)\s+", " ", t)
    return re.sub(r"\s+", " ", t).strip(" .,")


def _month(name: str) -> int:
    return MONTH_NAMES[name.rstrip(".")]


def _ordered(a: date, b: date) -> tuple[date, date]:
    return (a, b) if a <= b else (b, a)


# ---------------------------------------------------------------- the rules, in order


def day_range(t: str) -> Reading | None:
    """July 16 to 18, 1968; July 16 to August 2, 1968; 16 to 18 July 1968."""
    m = re.search(rf"\b{MONTH} (\d{{1,2}}){SEP}{MONTH} (\d{{1,2}}),? {YEAR}\b", t)
    if m:
        y = int(m.group(5))
        a, b = (
            _day(y, _month(m.group(1)), int(m.group(2))),
            _day(y, _month(m.group(3)), int(m.group(4))),
        )
        return _days(a, b)
    m = re.search(rf"\b{MONTH} (\d{{1,2}}){SEP}(\d{{1,2}}),? {YEAR}\b", t)
    if m:
        y, mo = int(m.group(4)), _month(m.group(1))
        return _days(_day(y, mo, int(m.group(2))), _day(y, mo, int(m.group(3))))
    m = re.search(rf"\b(\d{{1,2}}){SEP}(\d{{1,2}}) {MONTH},? {YEAR}\b", t)
    if m:
        y, mo = int(m.group(4)), _month(m.group(3))
        return _days(_day(y, mo, int(m.group(1))), _day(y, mo, int(m.group(2))))
    return None


def _days(a: date | None, b: date | None) -> Reading | None:
    if a is None or b is None:
        return None
    a, b = _ordered(a, b)
    if a.month == b.month:
        text = f"{calendar.month_name[a.month]} {a.day} to {b.day}, {a.year}"
    else:
        text = f"{calendar.month_name[a.month]} {a.day} to {_fmt_day(b)}"
    return Reading(a, b, Precision.DAY, text)


def single_day(t: str) -> Reading | None:
    """1968-07-16 (and ISO datetimes); 7/16/1968; 1968/07/16; July 16, 1968; 16 July
    1968.
    """
    patterns = (
        (rf"\b{YEAR}-(\d{{1,2}})-(\d{{1,2}})(?:t[\d:.]+z?)?\b", (1, 2, 3)),
        (rf"\b{YEAR}/(\d{{1,2}})/(\d{{1,2}})\b", (1, 2, 3)),
        (rf"\b(\d{{1,2}})/(\d{{1,2}})/{YEAR}\b", (3, 1, 2)),
        (rf"\b{MONTH} (\d{{1,2}}),? {YEAR}\b", (3, 1, 2)),
        (rf"\b(\d{{1,2}}) {MONTH},? {YEAR}\b", (3, 2, 1)),
        (rf"\b(\d{{1,2}}) of {MONTH},? {YEAR}\b", (3, 2, 1)),
    )
    for pattern, (yi, mi, di) in patterns:
        m = re.search(pattern, t)
        if not m:
            continue
        month = m.group(mi)
        mo = int(month) if month.isdigit() else _month(month)
        d = _day(int(m.group(yi)), mo, int(m.group(di))) if 1 <= mo <= 12 else None
        if d is None:
            raise Impossible(m.group(0))
        return Reading(d, d, Precision.DAY, _fmt_day(d))
    return None


def two_sided(t: str) -> Reading | None:
    """Any two readable dates joined by to, through, until or a dash: "1998 to 2002",
    "July 1968 to March 1969", "spring 1968 to fall 1969", "1990 to now"."""
    for m in re.finditer(SEP, t):
        left, right = t[: m.start()].strip(), t[m.end() :].strip()
        a = single(left)
        b = (
            Reading(date.today(), date.today(), Precision.DAY, "now")
            if NOW.match(right)
            else single(right)
        )
        if a and b:
            start, end = min(a.start, b.start), max(a.end, b.end)
            precision = (
                a.precision if a.precision == b.precision else Precision.APPROXIMATE
            )
            return Reading(start, end, precision, f"{a.reading} to {b.reading}")
    return None


def month(t: str) -> Reading | None:
    """July 1968; 1968-07; 7/1968."""
    m = re.search(rf"\b{MONTH},? {YEAR}\b", t)
    if m:
        y, mo = int(m.group(2)), _month(m.group(1))
    else:
        m = re.search(rf"\b{YEAR}-(\d{{1,2}})\b", t) or re.search(
            rf"\b(\d{{1,2}})/{YEAR}\b", t
        )
        if not m:
            return None
        a, b = m.group(1), m.group(2)
        y, mo = (int(a), int(b)) if len(a) == 4 else (int(b), int(a))
        if not 1 <= mo <= 12:
            return None
    text = f"{calendar.month_name[mo]} {y}"
    return Reading(date(y, mo, 1), _month_end(y, mo), Precision.MONTH, text)


def season(t: str) -> Reading | None:
    """Spring is March to May, summer June to August, fall September to November, winter
    December to the end of the following February."""
    m = re.search(rf"\b(spring|summer|fall|autumn|winter),? (?:of )?{YEAR}\b", t)
    if not m:
        return None
    name, y = m.group(1), int(m.group(2))
    if name == "winter":
        start, end = date(y, 12, 1), _month_end(y + 1, 2)
    else:
        first, last = SEASONS[name]
        start, end = date(y, first, 1), _month_end(y, last)
    return Reading(start, end, Precision.APPROXIMATE, f"{name.title()} {y}")


def decade(t: str) -> Reading | None:
    """The 1960s; the '60s; the early, mid or late 1960s."""
    m = re.search(
        r"\b(?:(early|mid|middle|late)[- ])?(?:the )?(18[5-9]|19\d|20\d)0'?s\b", t
    )
    if m:
        start_year = int(m.group(2)) * 10
    else:
        m = re.search(r"\b(?:(early|mid|middle|late)[- ])?(?:the )?'?([3-9])0'?s\b", t)
        if not m:
            return None
        start_year = 1900 + int(m.group(2)) * 10
    part = m.group(1)
    first, last = {
        "early": (0, 3),
        "mid": (3, 6),
        "middle": (3, 6),
        "late": (6, 9),
    }.get(part, (0, 9))
    label = f"the {part + ' ' if part else ''}{start_year}s".replace("middle", "mid")
    return Reading(
        date(start_year + first, 1, 1),
        date(start_year + last, 12, 31),
        Precision.DECADE,
        label,
    )


def year(t: str) -> Reading | None:
    m = re.search(rf"\b{YEAR}\b", t)
    if not m:
        return None
    y = int(m.group(1))
    return Reading(date(y, 1, 1), date(y, 12, 31), Precision.YEAR, str(y))


SINGLE = (day_range, single_day, month, season, decade, year)


def single(t: str) -> Reading | None:
    for rule in SINGLE:
        found = rule(t)
        if found:
            return found
    return None


def parse(text: str | None) -> Reading | None:
    """What the text says, or None when it says no date this grammar can read."""
    if not text or not text.strip():
        return None
    t = normalise(text)
    fuzzy = FUZZY.match(t)
    if fuzzy:
        t = t[fuzzy.end() :]
    try:
        found = day_range(t) or single_day(t) or two_sided(t) or single(t)
    except Impossible:
        return None
    if found and fuzzy:
        return Reading(
            found.start, found.end, Precision.APPROXIMATE, f"around {found.reading}"
        )
    return found


EXAMPLES = (
    "July 16, 1968",
    "16 July 1968",
    "7/16/1968",
    "July 1968",
    "July 16 to 18, 1968",
    "summer 1968",
    "the 1960s",
    "the early 1960s",
    "1998 to 2002",
    "around 1950",
    "1968",
)
