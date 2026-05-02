---
name: review-design-docs
description: "Review and update project design documentation. Use when: design docs are stale; architecture has drifted from docs; adding a new feature that affects the data model, API surface, or component hierarchy; after a refactor; when onboarding notes in /memories/repo/ need refreshing. Produces: updated docs/, relationship-overview.md, and /memories/repo/ notes that accurately reflect the current codebase."
argument-hint: "Optional: focus area (e.g. 'data model', 'API endpoints', 'frontend components')"
---

# Review and Update Project Design Documentation

## When to Use
- After adding or removing models, schemas, or API endpoints
- After a significant frontend or backend refactor
- When `docs/` or `/memories/repo/` notes feel out of date or contradict the code
- Before onboarding a new contributor or writing a feature spec
- When explicitly asked to "sync the docs" or "update design docs"

## Scope of Documentation

| Artifact | Location | What it covers |
|---|---|---|
| Relationship overview | `docs/relationship-overview.md` | Core data hierarchy (Periods → Events → Assets) |
| README | `README.md` | Project overview, stack, setup steps |
| Repo memory | `/memories/repo/*.md` | Per-session codebase facts, build commands, migration lessons |

## Procedure

### 1. Gather current state from code
Read the canonical source-of-truth files in parallel:
- `backend/app/models.py` — SQLAlchemy models (tables, columns, relationships)
- `backend/app/schemas.py` — Pydantic shapes exposed to the API
- `backend/app/main.py` — registered routes and their HTTP methods
- `backend/app/services/` — business logic that affects the conceptual model
- `frontend/app/types.ts` — TypeScript types mirroring backend schemas
- `frontend/app/lib/memoirApi.ts` — API calls actually used by the frontend

### 2. Read existing documentation
Load all current doc files:
- `docs/relationship-overview.md`
- `README.md`
- `/memories/repo/memoir-architecture.md`
- `/memories/repo/period-event-asset-bootstrap.md`

### 3. Compare and identify gaps
Check for each category:

**Data model drift**
- Does `docs/relationship-overview.md` list all entities in `models.py`?
- Are relationships (one-to-many, many-to-many join tables) correctly described?
- Are new columns (e.g. flexible date precision, referenced people/locations) reflected?

**API surface drift**
- Diff the live routes in `main.py` against the baseline in [references/api-surface.md](./references/api-surface.md).
- Update that file whenever endpoints are added, removed, or renamed.
- Does the README or any doc list the current API endpoints?

**Frontend drift**
- Do TypeScript types in `types.ts` align with the Pydantic schemas?
- Are new hooks or components referenced in docs if they affect the UX model?

**Build/ops drift**
- Is the quick-validation command in `/memories/repo/memoir-architecture.md` still correct?
- Does `README.md` reflect any new environment variables or Docker service names?

### 4. Update documentation

**Principle: edit in place, minimal prose.**
- Prefer bullet points and short tables over paragraphs
- Do not invent new doc files — update existing ones
- Do not document internal implementation details; focus on the *conceptual model* and *interface boundaries*

**Order of edits:**
1. `docs/relationship-overview.md` — keep it the single source of truth for the data hierarchy
2. `/memories/repo/memoir-architecture.md` — update facts, commands, and migration lessons
3. `/memories/repo/period-event-asset-bootstrap.md` — add any new bootstrap endpoints or schema additions
4. `README.md` — update only if setup steps or stack info changed

### 5. Validate
- Confirm no factual contradictions remain between docs and code
- Confirm build/quick-validation command still works if it was changed
- Summarize what changed and what (if anything) was left unchanged intentionally

## Suggested Missing Documentation

The following docs do not yet exist and are candidates to create when the project matures:

| Doc | Path | What it would cover |
|-----|------|---------------------|
| Data model diagram | `docs/data-model.md` | Entity-relationship table for all SQLAlchemy models with column names and foreign keys |
| Environment variables | `docs/environment.md` | All `.env` keys, their purpose, required vs optional, and safe defaults |
| AI/Gemini integration | `docs/ai-integration.md` | Which endpoints call Gemini, what prompts are used, token cost considerations |
| Frontend component map | `docs/frontend-components.md` | What each component renders, which hooks it consumes, which API endpoints it calls |
| Ingest pipeline | `docs/ingest-pipeline.md` | Step-by-step flow from audio/document upload → Gemini analysis → DB write → hierarchy sync |

Create these only when the relevant subsystem is stable enough not to need frequent rewrites.

## Quality Checklist
- [ ] All entities in `models.py` are named (not necessarily fully described) in `relationship-overview.md`
- [ ] API endpoint list in memory matches routes registered in `main.py`
- [ ] `README.md` setup steps can be followed without referring to the code
- [ ] `/memories/repo/` notes contain no contradictions with each other
- [ ] No doc claims a table column or relationship that no longer exists in the schema
