# The interviewer

Requirements sections 6.5, 8 and 16 are the spec. The AI does not only write down what was said: it asks. This
document covers the turn-based loop that ships in v0.1. The live conversation (browser and telephone) is added in
v0.2.

## The loop

1. The storyteller records a memory: one tap from home, or from a question.
2. The recording is normalised, transcribed and read (`docs/AI.md`). When extraction is done, the job
   `questions.generate` asks the AI for two or three follow-up questions about what was just said.
3. The record screen says "Thinking of a question about what you said…" while that happens, then shows the
   question with one button: **Record your answer**.
4. That button opens the record screen already recording, with "Answering: *the question*" on screen. Stop
   saves the answer, the question is answered, and the next question follows.

The storyteller touches nothing but Record and Stop. The loop ends when they stop answering, or when there is
nothing left to ask ("No more questions for now. Thank you, every word is saved.").

## Where questions come from

| Source | When | For whom |
|---|---|---|
| **Follow-ups** (`api/app/questions/generate.py`, prompt `questions-1`) | After each memory is extracted, when the archive's AI questions setting is on | The memory's storyteller |
| **Seeds** (`api/app/questions/interviewer.py`) | The first time an archive that never had a question asks for one: "What should we call you?", "Where and when were you born?", "Tell me about your parents." | Anyone |
| **People** (`POST /api/questions`) | A family member types one | Anyone |

The follow-up prompt gives the AI the transcript, the storyteller's name, the date (the memory's, or its event's),
the people and places named, the event, and the questions already waiting. Each question comes back with what it is
about. It is scoped from that:

| The AI says it is about | Scope | Needs |
|---|---|---|
| this moment | the memory's **event** | The memory is placed |
| that time of life | the storyteller's **period** for that event | The memory is placed in a period |
| a person | that **person** | The name is one of the memory's mentions, and only one person answers to it |
| anything else | **general** | |

When the target is not known the question is general, and still carries the memory it came from.

## Style rules

Written into the prompt, and enforced where code can:

- **One question at a time.** Anything after the first question mark is cut off.
- **Short.** More than 25 words, or 200 characters, and the question is dropped.
- **Never leading.** It does not suggest an answer or assume a feeling.
- **Never corrects the storyteller.** Discrepancies are for the archivist, later.
- No yes-or-no questions. It may echo what was said: "You said your brother drove. Which brother?"

## De-duplication

Compared text is the question without case, extra spaces or the closing mark (`normalize` in
`api/app/domain/questions.py`), checked **as it is written**, never when it is read:

- A pending question's text is unique in the archive, whatever made it. A unique index backs this, so two writers
  racing on the same text get one row.
- A question Memoir writes itself is skipped when the same text was **ever** asked: pending, answered, dismissed or
  deleted. That is what makes dismissing permanent.
- A question a person types is compared with pending questions only. It may ask again what was answered before.

## Next

`GET /api/questions/next` gives the one question to ask now; `GET /api/questions/for-you` the list, in the same
order:

1. Questions from the **most recently recorded memory** first: what was just said.
2. Then by scope: the event, its period, a person, then general.
3. Then the oldest.

A user sees questions for their own person and questions for anyone. Questions from a memory they may not see (an
"only me" memory of someone else's) are never shown to them.

After a recording, `?after_memory_id=` adds `waiting: true` while that memory's own questions may still come: until
its question job has finished, unless transcription or extraction failed or AI is off, and for at most three
minutes after the recording. The app asks again every three seconds while it is waiting.

## Answering

Recording from a question (`?question=9` on the record screen) links the memory to it:

- The question is **answered** the moment the recording is finished uploading, with the memory that answered it.
  The memory page shows "Answering: *the question*".
- The answer goes **where the question points**: an event question puts the memory on that event at once; a person
  question mentions that person; a period question suggests a new event in that period first, even for a memory
  with no date, and auto-filing puts it there once extraction has given it a title.
- Otherwise the answer **joins the story the question came from**: a follow-up to a memory on "Driving to Erie"
  puts its answer on that event too, at once. A person question does both. So a five-question loop about one
  story stays on that story, and none of it waits in "Waiting to be placed".
- A recording started from somewhere explicit (an event's page, say) keeps that place instead.
- Answers are also auto-filed like quick memories (`docs/TIMELINE.md`), so a seed question's answer with a date
  in it lands on the timeline too.

## Dismissing

**Don't ask this again** dismisses a question for good: it leaves every list, is never written again by Memoir,
and cannot be made pending again (`PATCH /api/questions/{id}` only moves a pending question, to answered or
dismissed).

## Where it shows

| Where | What |
|---|---|
| Home, phone | Record a memory, then "A question for you" with Record your answer |
| Home, wide screen | The same question above the review workspace |
| Record screen, after Stop | The next question, about what was just said |
| Questions for you (`/questions`) | Every waiting question, next first, each with Record your answer and Don't ask this again |
| A memory | The question it answered, and the questions it raised that are still waiting |

## Not yet

- The live conversation, by browser and by telephone (v0.2).
- Questions from the archive's gaps: unnamed faces, undated photos, thin decades (v0.2 and v0.3).
- A weekly nudge by email or text (v0.2).
