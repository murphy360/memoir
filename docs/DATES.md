# Dates

Families do not say "1968-07-16". They say "the summer we moved to Erie", "the early sixties", "Christmas 1974".
Memoir keeps the words as typed and reads them into a range it can sort by. Requirements section 3.3 is the spec;
`api/app/dates/grammar.py` is the code, and `api/tests/test_dates.py` is the table of what it reads.

## What it reads

The most specific reading wins. In order:

| Kind | Examples | Reads as |
|---|---|---|
| A day range | July 16 to 18, 1968; July 16-18, 1968; July 16 to August 2, 1968; 16 to 18 July 1968 | Those days (precision `day`) |
| A day | 1968-07-16 (and ISO datetimes); 7/16/1968; 1968/07/16; July 16, 1968; 16 July 1968; 16th July 1968; the 1st of May 1945 | That day (`day`) |
| Two dates joined | 1998 to 2002; 1998-2002; 1998 through 2002; between 1998 and 2002; July 1968 to March 1969; spring 1968 to fall 1969; 1990 to now | From the start of one to the end of the other (their shared precision, else `approximate`). Reversed ranges are put right |
| A month | July 1968; 1968-07; 7/1968 | The whole month (`month`) |
| A season | summer 1968; the summer of 1968; autumn of 1968 | Spring March to May, summer June to August, fall or autumn September to November, winter December to the end of the next February (`approximate`) |
| A decade | the 1960s; the '60s; the 60s; the early, mid or late 1960s | The decade, or its first, middle or last four years (`decade`) |
| A year | 1968; Christmas 1974; we moved to Erie in 1968 | The whole year (`year`) |

"Around", "about", "circa" or "c." in front makes any reading `approximate` ("around 1950").

Years run from 1850 to 2099. Anything else reads as nothing: "sometime", "the 20s" (which century?), and a day that
cannot exist ("February 30, 2000"), which is not quietly read as the year 2000.

## Seeing it before saving

`POST /api/dates/parse` with `{"text": "summer 1968"}` answers what Memoir read:

```json
{"ok": true, "start": "1968-06-01", "end": "1968-08-31", "precision": "approximate", "reading": "Summer 1968"}
```

or, when it cannot read the text, `{"ok": false, "message": "Could not read this date.", "examples": [...]}`. The
web app's `DateField` shows "Reads as Summer 1968" under the field as you type, or a warning with examples and a
"Save it as written anyway" choice.

## Saving

Events, memories, assets (the capture date), periods and epics (a start and an end), and people (birth and death)
read their dates when saved. A date Memoir cannot read is refused (`422 unreadable_date`, with examples) unless the
request says `"keep_text_only": true`; then the words are kept and the item stays undated, sorting after every dated
one. A period or epic may end "now" (or "present", "today"): it runs to today.

## Whose date it is

Every date records where it came from (`date_source`, `capture_source`, `dates_source`, `birth_source`,
`death_source`): `manual` when a person typed it, otherwise what set it (`transcript`, `exif`, `research`). A job
sets a date with `set_by_job`, which changes nothing when the date is `manual`. Fixing a date by hand is final.
