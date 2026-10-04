# The timeline and where memories go

How a memory finds its place in someone's life. Requirements sections 5.3 to 5.5 and 6.4 are the spec;
`api/app/placement/` is the code.

## Whose timeline

Every person has a timeline: their periods (chapters), and the events they took part in, placed in one of their own
periods. A signed-in user's own person is made from their name the first time they need one (`GET /api/me/person`),
so `/timeline` always has someone to show. `/people/{id}/timeline` shows anyone's.

The timeline loads chapter by chapter: `GET /api/people/{id}/timeline` gives the periods in order with how many events
and epics each holds; opening a chapter loads its events (`GET /api/people/{id}/events?period_id=`). Which chapters
are open is kept in the address (`?open=3,4`), so a reload or a shared link shows the same thing. A person with 200
events loads in well under a second.

## The suggestion

For a memory with a date, Memoir suggests, best first (`api/app/placement/suggest.py`):

1. **The closest event** on the storyteller's own timeline, inside the period whose dates cover the memory (the
   narrowest one, when several do). Close means overlapping, or within 31 days. A heavier event wins a tie.
2. **A new event in that period**, when no event is close.
3. **Events of the people the memory mentions** at that time ("Mary's Move to Erie").
4. **Something new**: a period for the memory's decade ("The 1960s") and an event in it.

A memory without a date has no suggestion: it waits to be placed by hand.

The storyteller is the memory's storyteller, or else the person of the account that recorded it.

## Auto-filing

A quick memory (one tap from home) is filed where the suggestion says, as soon as extraction has read its date,
when the archive's "file quick memories automatically" setting is on (the default). It happens **once** per memory.
Periods and events made for it are marked "created for this memory". They are ordinary rows from then on: no job
ever makes them again, so deleting one sticks, and the memory goes back to the inbox. Other recordings are never
filed without a person choosing.

## Saved to

After a recording, and on every memory, a line says where it is in the storyteller's words: **Saved to The 1960s,
Fishing at Presque Isle**, with **Change**. Change opens the placement step: the suggestions, recent and nearby
events, and **Somewhere new** (what happened, when, and the decade a tap away). Choosing places it at once. A period
of the same name in the person's life is reused, never twinned.

## Waiting to be placed

The inbox (`/inbox`, `GET /api/inbox`) lists memories with no live event: never placed, or their event was deleted.
Each shows Memoir's suggestion as a one-tap **Place in ...** (`POST /api/inbox/{id}/accept`); one without a date
offers Place it. The list empties as memories are placed.
