---
name: pre-code-review
description: "Check code health before making any change. Use before every feature, fix, or refactor to avoid god files, spaghetti code, and duplicate logic. Identifies: files already too large to safely grow; logic that belongs in an existing service; patterns already established in the codebase that should be reused. Produces: a placement recommendation and a warning if the target file is a god file candidate."
argument-hint: "Describe the change you are about to make (e.g. 'add a new Gemini summarization call for periods')"
---

# Pre-Code Review — Avoid God Files and Spaghetti Code

## When to Use
- Before writing any new function, route, or module
- Before adding logic to an existing file
- When unsure where a new piece of code should live
- When a file "already has some related code" and it's tempting to just add there

## Current File Size Baseline

These are the known large files in this project. **Do not grow them without justification.**

| File | Lines (baseline) | Status |
|------|-----------------|--------|
| `backend/app/main.py` | ~1500 | ⚠️ God file — route handlers only, no business logic |
| `backend/app/services/gemini_client.py` | ~837 | ⚠️ At risk — split by concern if growing further |
| `backend/app/services/periods.py` | ~416 | Watch — consolidate helpers before adding more |
| `backend/app/services/memory_analysis.py` | ~188 | Healthy |
| `backend/app/services/directory.py` | ~154 | Healthy |
| `backend/app/services/image_metadata.py` | ~154 | Healthy |
| `backend/app/services/life_hierarchy.py` | ~143 | Healthy |
| `backend/app/schemas.py` | ~198 | Healthy |
| `backend/app/models.py` | ~256 | Healthy |

Update the Lines column after significant changes.

## Procedure

### 1. Understand the change
Read the argument (or ask the user): what entity or feature does this change affect? What layer does it touch — data model, business logic, AI/Gemini, or API surface?

### 2. Check where similar logic already lives
Before writing anything, search for related patterns:
- Is there already a service file for this domain? (e.g. periods, directory, questions)
- Is there a helper in `services/periods.py` that does something adjacent?
- Is there a Gemini call pattern in `gemini_client.py` that should be followed or extended?
- Is there a Pydantic schema that should be extended rather than duplicated?

### 3. Determine the correct home for new code

Use this routing table:

| Type of code | Where it belongs |
|---|---|
| SQLAlchemy model / table definition | `models.py` |
| Pydantic request/response shape | `schemas.py` |
| FastAPI route handler (thin — validate input, call service, return response) | `main.py` |
| Business logic, DB queries, data transformation | `services/<domain>.py` |
| Gemini API calls, prompt construction, response parsing | `services/gemini_client.py` |
| Audio file I/O | `services/audio_storage.py` |
| Document file I/O | `services/document_storage.py` |
| Image EXIF / metadata extraction | `services/image_metadata.py` |
| Period/Event/Asset hierarchy operations | `services/periods.py` |
| People / places normalization and linking | `services/directory.py` |
| Memory → hierarchy sync | `services/life_hierarchy.py` |
| Question generation and seeding | `services/questions.py` |
| Memory audio analysis pipeline | `services/memory_ingest.py` |

### 4. Flag god file risk

Raise a warning if the proposed change would:
- Add **business logic directly to `main.py`** (route handlers must stay thin — call a service function, do not inline DB queries or Gemini calls)
- Add more than ~50 lines to any file already over 400 lines without extracting something first
- Add a second responsibility to a file (e.g. adding period summarization logic to `directory.py`)
- Duplicate a pattern that already exists elsewhere (e.g. writing a new Gemini caller instead of adding a function to `gemini_client.py`)

### 5. Recommend a plan
Output a short placement plan before any code is written:
- Which file(s) will be touched
- What new function(s) will be added and where
- Whether any existing function should be extended instead
- Whether a new service file should be created (only if a genuinely new domain is being introduced)

### 6. Proceed (or pause)
If the plan looks clean, proceed with the change.
If the plan requires splitting an existing file or extracting logic first, do that extraction **before** adding new code.

## God File Rules — Non-Negotiable

1. **`main.py` contains route handlers only.** No inline DB queries, no Gemini calls, no file I/O. Extract to a service.
2. **One service file per domain.** Don't let `periods.py` absorb directory logic or vice versa.
3. **No copy-pasted patterns.** If a second route needs the same DB lookup, extract it to a shared helper in the appropriate service.
4. **New Gemini prompt?** It goes in `gemini_client.py` as a named function, not inline in a route or service.
5. **New file only for new domains.** Don't create `services/period_summarization.py` when `services/periods.py` exists — add to it. Do create a new file when a wholly new concern appears (e.g. `services/export.py` for a future export feature).

## Quality Checklist
- [ ] No business logic added directly to `main.py`
- [ ] New code placed in the correct service file per the routing table
- [ ] No logic duplicated that already exists in another service
- [ ] Any file that was already over 400 lines was not grown without extracting something first
- [ ] Gemini calls are named functions in `gemini_client.py`, not inline
- [ ] Baseline line counts updated in this file if a file grew significantly
