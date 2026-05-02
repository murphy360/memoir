# API Surface — Memoir

> Baseline snapshot. When reviewing docs, compare this against `backend/app/main.py`.
> Update this file whenever endpoints are added, removed, or renamed.

## Infrastructure

| Method | Path | Notes |
|--------|------|-------|
| GET | `/api/health` | Liveness check |
| GET | `/` | Root / version info |

## Life Periods

| Method | Path | Notes |
|--------|------|-------|
| GET | `/api/periods` | List all periods |
| POST | `/api/periods` | Create a period |
| PATCH | `/api/periods/{period_id}` | Update period title/dates/summary |
| DELETE | `/api/periods/{period_id}` | Delete period (204) |
| POST | `/api/periods/{period_id}/merge` | Merge another period into this one (204) |
| GET | `/api/periods/{period_id}/events` | List events in a period |
| POST | `/api/periods/{period_id}/analyze` | AI analysis of a period |

## Life Events

| Method | Path | Notes |
|--------|------|-------|
| GET | `/api/events` | List all events |
| POST | `/api/events` | Create an event |
| PATCH | `/api/events/{event_id}` | Update event |
| DELETE | `/api/events/{event_id}` | Delete event |
| POST | `/api/events/{event_id}/merge` | Merge another event into this one |
| GET | `/api/events/{event_id}/assets` | List assets linked to event |
| POST | `/api/events/{event_id}/summarize` | AI-generate event summary |
| POST | `/api/events/{event_id}/research` | AI research suggestions for event |
| POST | `/api/events/{event_id}/apply-research-suggestion` | Accept AI suggestion |
| POST | `/api/events/{event_id}/dismiss-research-suggestion` | Dismiss AI suggestion |

## Assets

| Method | Path | Notes |
|--------|------|-------|
| GET | `/api/assets/unlinked` | Unlinked Assets Inbox |
| POST | `/api/assets` | Upload an asset (multipart) |
| PATCH | `/api/assets/{asset_id}` | Update asset metadata |
| DELETE | `/api/assets/{asset_id}` | Delete asset (204) |
| GET | `/api/assets/{asset_id}/download` | Download asset file |
| POST | `/api/assets/{asset_id}/link-event/{event_id}` | Link asset to an event |

## Memories

| Method | Path | Notes |
|--------|------|-------|
| GET | `/api/memories` | List all memories |
| POST | `/api/memories` | Ingest audio memory |
| POST | `/api/memories/document` | Ingest document memory |
| GET | `/api/memories/{memory_id}/audio` | Stream audio file |
| GET | `/api/memories/{memory_id}/document` | Download document file |
| POST | `/api/memories/{memory_id}/reanalyze` | Re-run Gemini analysis |
| POST | `/api/memories/{memory_id}/research` | AI research suggestions |
| POST | `/api/memories/{memory_id}/apply-research-suggestion` | Accept AI suggestion |
| POST | `/api/memories/{memory_id}/dismiss-research-suggestion` | Dismiss AI suggestion |
| PATCH | `/api/memories/{memory_id}` | Update memory metadata |
| PATCH | `/api/memories/{memory_id}/recorder` | Update recorder person |
| DELETE | `/api/memories/{memory_id}` | Delete memory |

## People Directory

| Method | Path | Notes |
|--------|------|-------|
| GET | `/api/people` | List all people |
| POST | `/api/people` | Create person |
| PATCH | `/api/people/{person_id}` | Update person |
| DELETE | `/api/people/{person_id}` | Delete person |
| POST | `/api/people/{person_id}/merge` | Merge duplicate person into this one |
| POST | `/api/people/{person_id}/split` | Split person into multiple entries |
| POST | `/api/people/{person_id}/aliases` | Add alias |
| DELETE | `/api/people/{person_id}/aliases/{alias}` | Remove alias |

## Places Directory

| Method | Path | Notes |
|--------|------|-------|
| GET | `/api/places` | List all places |
| POST | `/api/places` | Create place |
| PATCH | `/api/places/{place_id}` | Update place |
| DELETE | `/api/places/{place_id}` | Delete place |

## Questions

| Method | Path | Notes |
|--------|------|-------|
| GET | `/api/questions` | List pending questions |
| POST | `/api/questions/{question_id}/answer` | Answer a question |
| POST | `/api/questions/{question_id}/dismiss` | Dismiss a question |

## Settings

| Method | Path | Notes |
|--------|------|-------|
| GET | `/api/settings` | Get all settings |
| PUT | `/api/settings/{key}` | Update a setting value |
