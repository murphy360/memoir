# Working on memoir

Instructions for any Claude session in this repository. Built from murphy360/standards (templates/CLAUDE.md); keep
the shared parts as they are and add what is particular to this project under "This project".

## How work arrives
The owner hands out work as a ticket (or "the next ticket in the milestone"). The milestone's description carries the
RUN ORDER: take the first open ticket in it that is not assigned to the owner and is not an epic. Read the whole
ticket, including its "For the implementer" section. If a decision the owner reserved is unclear, ask in one comment
on the ticket and take the next one; never guess. Say on the ticket, in one comment, that you started and which branch.

## Where and how to work
- Never change the branch of the main checkout: the owner may be using it. Work in a scratch worktree:
  `git worktree add -b <type>/<short-name> /tmp/<project>-wt/<short-name> origin/main`
  (types: feat/, fix/, docs/, ci/, deploy/). Remove the worktree when the PR is open.
- Tests run in the project's Docker image, not on the host. Build it under your own tag so parallel sessions never
  overwrite each other's images.
- Never touch the owner's running services, stacks or devices unless the ticket says so.

## Definition of done: one pull request
1. The change, small and readable, in the files the ticket names.
2. A unit test for every new behaviour, green in Docker; the PR body pastes the last lines of the output.
3. The documentation in the same PR: the spec for the area, the user-facing manual, and a training or how-to line
   where the project has them. Write for the reader, not the developer.
4. The commit: the first line says what changed in plain words; the body says why; `Closes #N`; a `Note:` line for
   anything the deployer must do.
5. The PR body: what and why, `Closes #N`, the tests and their output, the docs touched, any known issue with its
   ticket. Open it with `gh pr create --base main`, then comment the link on the ticket.
6. Never merge, never push to main, never enable auto-merge, unless the owner has said so for this session.

## Standards every project keeps (murphy360/standards)
- CI calls the shared workflows at a pinned version tag: standards-check, python-lint (ruff at its defaults, 88
  columns, `ruff format`), shell-lint, actionlint, test-docker, image.
- The code rules (`code_rules.py`): complexity 15, 15 branches and 60 statements per function, 800 lines per file
  (1200 for a test). Every file is clean: formatted, no finding, no `# noqa`, under the size limit. CI checks every
  file on every run, and a finding anywhere fails it; each finding is printed with its line, rule and fix. A change
  that would take a file over the limit splits it in the same PR. There is no baseline and no flag that skips the
  rules. Run `code_rules.py --all` before a push. A PR that only re-formats is labelled `format-only`, and
  `code_rules.py --format-only` proves it changed no code.
- Every third-party action is pinned to a commit SHA; Dependabot (`.github/dependabot.yml`) keeps them and the
  dependencies current, one grouped PR per ecosystem per week.
- Times are UTC. Secrets never go in the repository, a ticket or a log.
- Prose in docs and tickets: short sentences, one idea per sentence, no em-dashes.

## This project

Memoir is a voice-first family memory archive, rewritten from the ground up. `docs/REQUIREMENTS.md` is what
it must do; the GitHub milestones (v0.1 to v0.5, each with a RUN ORDER) are the order to build it in. Version
0 lives at murphy360/memoir-v0 and is reference only. Stories recorded per month is the number every
milestone is judged by: when a choice trades a feature for getting a parent recording sooner, take the
recording.

- **Three processes, two directories.** `api/` is one Python 3.12 package (FastAPI, SQLAlchemy 2, Alembic,
  PostgreSQL 17) run as two processes: the API (`memoir-cli serve`, which migrates first) and the job worker
  (`memoir-cli worker`). `web/` is a Vite plus React single-page app in TypeScript, served by nginx under
  `/memoir/`. `docs/ARCHITECTURE.md` says where code goes.
- **Tests and lint, in Docker:** `make test TAG=<you>` and `make lint TAG=<you>` (images tagged with your
  name, so parallel sessions never collide). The API tests start a throwaway PostgreSQL inside the test
  image (`api/tests/pg.py`); nothing else is needed. The web tests stub the network.
- **Run it locally:** `make up`, then http://localhost:8080/memoir/ (the API answers on :8010 too).
- **The API contract.** The web client is typed from `web/src/api/openapi.json`. After changing a route or a
  schema, run `make openapi` and commit the file; a test fails while it is stale.
- **Every route has a role check** from `api/app/accounts/deps.py` (`require_role(...)`, `require_executor`);
  only health, login and the invitation-accept routes are open. `tests/test_roles.py` fails when a route
  forgets. Tables people edit use the `Audited` mixin. `docs/ACCOUNTS.md` has the rules.
- **Errors** are always `{"error": {"code", "message", "field"}}` (`api/app/core/errors.py`). Raise
  `ApiError` from routes and services.
- **Background work is a job** (`api/app/jobs/`): register a handler with `@handler("area.kind")`, enqueue
  with an idempotency key, report progress with `ctx.progress(...)`. Never call an external provider
  inside a request.
- **Files are blobs** (`api/app/blobs/store.py`): content-addressed, verified on read. Never write files
  anywhere else.
- **Lint for the web** is node-lint pinned to murphy360/standards#2 until it is released. TypeScript stays on
  5.x (typescript-eslint and openapi-typescript); Dependabot ignores its major.
- **Deployed** from the dontpanic stack (`~/Software/dontpanic`) at `https://dontpanic.ddns.net/memoir` once
  ticket #10 lands. Data in `/docker/memoir`. Never touch it unless a ticket says so.
- **Privacy.** This holds a family's stories, photos and faces. Logs carry ids and durations, never
  transcripts, file contents or keys.
