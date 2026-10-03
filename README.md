# memoir

A voice-first family memory archive. A person tells a story; Memoir writes it down, works out when and where it
happened and who was there, files it on their life timeline, and asks the next good question. Photos and documents
attach to the events they show. Every person in the family has a timeline, and the timelines braid together.

This is the ground-up rewrite. Version 0 lives at [murphy360/memoir-v0](https://github.com/murphy360/memoir-v0).

- **What we are building:** [docs/REQUIREMENTS.md](docs/REQUIREMENTS.md).
- **In what order:** the GitHub milestones, each with a RUN ORDER in its description. Stories recorded per month is
  the number every milestone is judged by.
- **How it is put together:** [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md).
- **Photo work** (metadata, faces, deep research) comes from
  [murphy360/photo-analysis](https://github.com/murphy360/photo-analysis).

## Run it

Docker is the only requirement.

```bash
make up        # builds and starts the database, API, worker and web app
```

Then make the first account, the owner (it asks for a password; everyone else joins by invitation):

```bash
docker compose exec memoir-api memoir-cli create-owner --email you@example.org --name "Your name"
```

Open http://localhost:8080/memoir/ and sign in. *People with access* invites the rest of the family
([docs/ACCOUNTS.md](docs/ACCOUNTS.md)). The API answers
on http://localhost:8010/api/health too (set `MEMOIR_WEB_PORT` or `MEMOIR_API_PORT` if a port is taken). `make down` stops everything; the data stays in Docker volumes.

## Recording

Memoir records in the browser: Chrome, Edge and Firefox on desktop and Android, and Safari on macOS and iOS (14.5 or
later). The first recording asks for the microphone. Recordings are kept on the device until the server has them,
so a dropped connection or a closed tab loses nothing ([docs/CAPTURE.md](docs/CAPTURE.md)).

## What "Saved to" means

After a recording, Memoir says where it put the memory: **Saved to The 1960s, Fishing at Presque Isle** is the
chapter of your life and the moment in it. If that is wrong, tap **Change** and pick the right one. A memory Memoir
cannot date waits under **Waiting to be placed** until someone places it ([docs/TIMELINE.md](docs/TIMELINE.md)).

## Questions

When a memory is saved, Memoir asks about it: "You said your brother drove. Which brother?" One tap on **Record
your answer** records the answer, and the next question follows. **Questions for you** lists every question
waiting; **Don't ask this again** dismisses one for good ([docs/INTERVIEWER.md](docs/INTERVIEWER.md)).

## AI

Set `MEMOIR_GEMINI_API_KEY` for the API and the worker to have recordings transcribed, read for dates, people and
places, and followed by questions. `MEMOIR_ANTHROPIC_API_KEY` (Claude) and `MEMOIR_GROK_API_KEY` (Grok) can do the
reading and the questions too; only Gemini transcribes. `MEMOIR_AI_PROVIDER` picks among them. Without a key Memoir
still records and keeps everything, and says "AI is off" ([docs/AI.md](docs/AI.md)).

## Deploy

Production runs in the dontpanic stack at https://dontpanic.ddns.net/memoir. [docs/RUNBOOK.md](docs/RUNBOOK.md)
covers the first deploy, new builds, nightly backups, restores, secrets and people. `deploy/` holds the reference
compose file, the Caddy block and the backup and restore scripts.

## Develop

Everything runs in the project's images. Pass your own `TAG` so parallel sessions never share an image.

| Command | What it does |
|---|---|
| `make test TAG=me` | API tests (with a throwaway PostgreSQL inside the image) and web typecheck plus tests |
| `make lint TAG=me` | ruff, formatting and the complexity limits for `api/`; ESLint and Prettier for `web/` |
| `make format TAG=me` | `ruff format` and `prettier --write` |
| `make openapi TAG=me` | regenerate `web/src/api/openapi.json` after an API change; commit it |

CI (`.github/workflows/ci.yml`) runs the same checks with the shared workflows of
[murphy360/standards](https://github.com/murphy360/standards), and publishes three images from `main`:
`ghcr.io/murphy360/memoir-api`, `memoir-worker` and `memoir-web`. Every file is clean: there is no lint baseline.
