# AI

What Memoir asks an AI to do, how, and what it costs. Requirements section 6 is the spec.

## Providers

Text and audio AI goes through one small interface (`api/app/ai/provider.py`): `transcribe(audio, prompt, model)`,
`structured(prompt, schema, model)` and `text(prompt, model)`. Each answers with the text (or parsed JSON) and its
token counts.

| Provider | Where | Notes |
|---|---|---|
| Gemini | `api/app/ai/gemini.py` | The REST API, with the key in the `x-goog-api-key` header, never in a URL. Structured answers use Gemini's `responseSchema`. Audio up to 12 MB goes inline in one request |
| Fake | `api/app/ai/fake.py` | Scripted answers for the tests; records every request; no network |

`registry.provider(settings)` gives Gemini when `MEMOIR_GEMINI_API_KEY` is set, and **nothing** when it is not: AI is
off. The owner can also turn transcription, extraction and questions off per archive (`/api/settings`). Either way the
memory is kept with its recording and says "AI is off"; `POST /api/memories/{id}/transcribe` runs it later.
`GET /api/ai/status` tells the app whether AI is on.

Photo work (metadata, faces, descriptions) is not here: it belongs to the photo-analysis service.

## Settings

| Variable | Default | What |
|---|---|---|
| `MEMOIR_GEMINI_API_KEY` | none | No key, no AI |
| `MEMOIR_GEMINI_MODEL` | `gemini-2.5-flash` | The model for every task |
| `MEMOIR_GEMINI_TRANSCRIBE_MODEL`, `MEMOIR_GEMINI_EXTRACT_MODEL` | empty | A different model for one task |
| `MEMOIR_AI_TIMEOUT_SECONDS` | 180 | Per request |
| `MEMOIR_GEMINI_BASE_URL` | `https://generativelanguage.googleapis.com` | Where Gemini is reached. Change it only to point an end-to-end run at a stand-in |

## Tasks

Prompts are named constants beside the code that uses them, with a version (`PROMPT_VERSION`) recorded on every
call. Change the version when the prompt changes.

| Task | Job | Prompt | What it does |
|---|---|---|---|
| Transcription | `analysis.transcribe` | `transcribe-1` (`api/app/analysis/transcribe.py`) | The words, exactly as spoken; `Speaker 1:` and so on when more than one person talks; `[unclear]` for words it cannot make out. Runs after normalisation, on the MP3 (or the original). Audio bigger than the provider takes in one request is cut into MP3 segments with ffmpeg, sized from the limit, and transcribed in order. A transcript a person edited is never replaced |
| Extraction | `analysis.extract` | `extract-1` (`api/app/analysis/extract.py`) | One structured call: the date as said, its precision, the storyteller's name, the people and places named, a 4 to 10 word title, a one-paragraph description, the tone (positive, negative, reflective, neutral, mixed) and relationship effects for the braid. Runs after transcription |
| Questions | `questions.generate` | `questions-1` (`api/app/questions/generate.py`) | Two or three short follow-up questions about the memory, each with what it is about (the event, the period, a person, general). Runs after extraction. See `INTERVIEWER.md` |

How extraction's answer is used:

- The **date** goes through the date grammar as a `transcript` date: it never replaces a date a person typed.
- The **title** and **description** fill only empty fields.
- **Names** resolve through the directory, aliases included. An alias for several people ("the kids") names them
  all. A name nobody has yet becomes a person (or place) marked `needs_review`, never a silent guess. An ambiguous
  storyteller ("Mom", when two people answer to it) is left for a person, and noted.
- Mentioned people join the memory's event as unconfirmed participants.
- Relationship effects, the model and the prompt version are kept on the memory (`extracted`) as proposals.

## Failures

A network blip or a busy provider is retried by the job worker with a doubling backoff; after the last attempt the
memory shows "transcription failed" (or "needs details") with the provider's reason and a Try again button. A
refusal that waiting cannot fix (Gemini answers 400, 401, 402, 403 or 404: a bad request, a refused key, no credit,
no such model) fails at once, with Gemini's own sentence, for example "Gemini answered 402: Your prepayment credits
are depleted". The recording is safe in every case. Questions that cannot be written leave the memory as it is:
the app stops waiting for them.

## Costs

Every call, success or failure, writes a row in `ai_calls`: task, provider, model, prompt version, input and output
tokens, duration, and the error if any. `GET /api/ai/usage?days=30` (owner) totals them by task and model.
