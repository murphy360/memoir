---
name: annotate-code
description: "Add or update in-code documentation after a code change. Use at the end of every feature, fix, or refactor to annotate what was changed. Covers: Python docstrings and inline comments in models/schemas/services; Pydantic Field descriptions that surface in FastAPI /docs; TypeScript JSDoc in memoirApi.ts and types.ts. Does NOT rewrite logic or add error handling — annotation only."
argument-hint: "Optional: file or area changed (e.g. 'models.py', 'services/periods.py', 'memoirApi.ts')"
---

# Annotate Code After a Change

## When to Use
- Immediately after adding, modifying, or deleting any backend model, schema, service function, or API route
- After adding or changing a frontend type, hook, or API helper
- When a code review or diff shows logic with no explanation of *why*
- When invoked explicitly: "annotate the code", "add docs", "document what I just changed"

## Scope — What to Annotate

### Backend (`backend/app/`)

| File | What to add |
|------|-------------|
| `models.py` | Column-level `# comments` on non-obvious fields (e.g. `date_precision`, `recorder_name`, join table semantics) |
| `schemas.py` | `Field(description="...")` on Pydantic fields — these appear in the FastAPI `/docs` UI automatically |
| `services/*.py` | Module-level docstring at the top of each file stating what the service owns; function docstrings for non-trivial functions |
| `main.py` | Route-level comments only for unusual behavior (e.g. soft-delete, side effects, cascade logic) |

### Frontend (`frontend/`)

| File | What to add |
|------|-------------|
| `app/types.ts` | TSDoc `/** */` comment on non-obvious type fields, especially optional ones |
| `app/lib/memoirApi.ts` | JSDoc `/** */` on each function noting: what endpoint it calls, key request/response shape |
| `app/hooks/*.ts` | JSDoc on the hook noting: what state it manages, what side effects it triggers |

## Procedure

### 1. Identify changed files
Look at what was just modified. If an argument was provided, start there. Otherwise check recent edits from the conversation.

### 2. Read each changed file
For each file in scope, read the full changed section before writing annotations.

### 3. Apply annotations — rules

**Do:**
- Annotate *what a thing is for* and *why a design choice was made* — not what the code literally does
- Use `Field(description="...")` on every Pydantic schema field that isn't self-evident from its name
- Add a module docstring to any `services/` file that lacks one
- Document nullable/optional fields with what `None` means in context

**Do not:**
- Add docstrings or comments to code you did not change in this session
- Restate the type annotation in prose (`# string field` on a `name: str` is noise)
- Add TODO comments unless the user asked for them
- Add error handling or logging under the guise of documentation

### 4. Verify FastAPI /docs surface
If `schemas.py` was changed, confirm that `Field(description=...)` was added to any new or modified fields. These descriptions appear verbatim in the auto-generated API docs at `/docs`.

### 5. Confirm
Briefly state which files were annotated and what was added. Note any areas skipped and why.

## Quality Checklist
- [ ] Every new Pydantic field in `schemas.py` has a `Field(description=...)`
- [ ] Every new `services/*.py` module has a module-level docstring
- [ ] Non-obvious model columns have an inline `#` comment
- [ ] New `memoirApi.ts` functions have a JSDoc noting the endpoint called
- [ ] No annotations added to code that was not changed in this session
