# AI

What Memoir asks an AI to do, how, and what it costs. Requirements section 6 is the spec.

## Providers

Text and audio AI goes through one small interface (`api/app/ai/provider.py`): `transcribe(audio, prompt, model)`,
`structured(prompt, schema, model)` and `text(prompt, model)`. Each answers with the text (or parsed JSON) and its
token counts.

| Provider | Where | Notes |
|---|---|---|
| Gemini | `api/app/ai/gemini.py` | The REST API, with the key in the `x-goog-api-key` header, never in a URL. Structured answers use Gemini's `responseSchema`. Audio up to 12 MB goes inline in one request |
| Anthropic | `api/app/ai/anthropic.py` | Claude over the Messages API, with the key in the `x-api-key` header. Structured answers are one forced tool call whose input schema is the schema asked for. Claude often sends a list field as a JSON string, sometimes the whole answer inside its own field; `unpack` decodes those against the schema. Text only: it cannot transcribe |
| Grok | `api/app/ai/grok.py` | xAI's OpenAI-compatible chat completions, with the key in the `Authorization` header. Structured answers use `response_format` with the schema. Text only: it cannot transcribe |
| OpenAI | `api/app/ai/openai.py` | Chat completions for the text tasks (`response_format` with the schema, no temperature: GPT-5 models take only their default) and `/audio/transcriptions` for recordings, as a named file with the transcription prompt. It hears audio, so it can **transcribe** |
| Fake | `api/app/ai/fake.py` | Scripted answers for the tests; records every request; no network |

`registry.provider(settings, task)` picks the provider for each task (`api/app/ai/registry.py`):

| Task | Provider |
|---|---|
| Transcription | `MEMOIR_AI_TRANSCRIBE_PROVIDER`, else the first with a key of those that hear audio: Gemini, OpenAI. Neither: transcription is off |
| Extraction | `MEMOIR_AI_EXTRACT_PROVIDER`, else `MEMOIR_AI_PROVIDER`, else the first with a key: Gemini, Anthropic, Grok, OpenAI |
| Questions | `MEMOIR_AI_QUESTIONS_PROVIDER`, else the same as extraction |

A choice whose key is missing falls back to the first provider with a key. With no key at all, AI is off. The owner
can also turn transcription, extraction and questions off per archive (`/api/settings`). Either way the memory is
kept with its recording and says "AI is off"; `POST /api/memories/{id}/transcribe` runs it later.
`GET /api/ai/status` says, for each task, which provider and model will do it.

Every provider's failures read the same way: "Anthropic answered 400: Your credit balance is too low." A refusal
that waiting cannot fix (400, 401, 402, 403, 404, 413, 422) fails at once; anything else is retried.

Photo work (metadata, faces, descriptions) is not here: it belongs to the photo-analysis service.

## Settings

| Variable | Default | What |
|---|---|---|
| `MEMOIR_GEMINI_API_KEY` | none | Gemini, for every task. On dontpanic, from the stack's `GEMINI_API_KEY_MEMOIR` |
| `MEMOIR_GEMINI_MODEL` | `gemini-2.5-flash` | The model for every task |
| `MEMOIR_GEMINI_TRANSCRIBE_MODEL`, `MEMOIR_GEMINI_EXTRACT_MODEL` | empty | A different model for one task |
| `MEMOIR_ANTHROPIC_API_KEY` | none | Claude for extraction and questions. On dontpanic, from the stack's `ANTHROPIC_API_KEY_MEMOIR` |
| `MEMOIR_ANTHROPIC_MODEL` | `claude-sonnet-5` | |
| `MEMOIR_GROK_API_KEY` | none | Grok for extraction and questions. On dontpanic, from the stack's `GROK_API_KEY_MEMOIR` |
| `MEMOIR_GROK_MODEL` | `grok-4.7` | |
| `MEMOIR_OPENAI_API_KEY` | none | OpenAI for every task, transcription included. On dontpanic, from the stack's `OPENAI_API_KEY_MEMOIR` |
| `MEMOIR_OPENAI_MODEL` | `gpt-5.5` | Extraction and questions |
| `MEMOIR_OPENAI_TRANSCRIBE_MODEL` | `gpt-transcribe` | Transcription. It reports usage in seconds of audio, so its cost rows show no tokens; `gpt-4o-transcribe` reports tokens |
| `MEMOIR_AI_TRANSCRIBE_PROVIDER` | empty | `gemini` or `openai` for transcription; empty means the first with a key |
| `MEMOIR_AI_PROVIDER` | empty | `gemini`, `anthropic`, `grok` or `openai` for the text tasks; empty means the first with a key |
| `MEMOIR_AI_EXTRACT_PROVIDER`, `MEMOIR_AI_QUESTIONS_PROVIDER` | empty | One task's own provider |
| `MEMOIR_ANTHROPIC_BASE_URL`, `MEMOIR_GROK_BASE_URL`, `MEMOIR_OPENAI_BASE_URL` | the providers' own | Change only for a stand-in, like `MEMOIR_GEMINI_BASE_URL` |
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
refusal that waiting cannot fix (400, 401, 402, 403, 404, 413 or 422: a bad request, a refused key, no credit, no
such model) fails at once, with the provider's own sentence, for example "Gemini answered 402: Your prepayment
credits are depleted". The recording is safe in every case. Questions that cannot be written leave the memory as it is:
the app stops waiting for them.

## Costs

Every call, success or failure, writes a row in `ai_calls`: task, provider, model, prompt version, input and output
tokens, duration, and the error if any. `GET /api/ai/usage?days=30` (owner) totals them by task and model.
