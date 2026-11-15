# Working on memoir

<!-- standards:shared:begin (do not edit down to the end marker: tools/sync_templates.py rewrites this text) -->

For every agent session in this repository, from murphy360/standards (templates/AGENTS.md). See also "This project".

## How work arrives

The owner hands out work as a ticket (or "the next ticket in the milestone"). The milestone's description carries the
RUN ORDER: take the first open ticket in it that is not assigned to the owner and is not an epic. Read the whole
ticket, including its "For the implementer" section; a ticket has the sections of `.github/ISSUE_TEMPLATE/ticket.md`.
If a decision the owner reserved is unclear, ask in one comment on the ticket and take the next one; never guess. Say
on the ticket, in one comment, that you started and which branch.

## Where and how to work

- Never change the branch of the main checkout: the owner may be using it. Work in a scratch worktree:
  `git worktree add -b <type>/<short-name> /tmp/<project>-wt/<short-name> origin/main`
  (types: feat/, fix/, docs/, ci/, deploy/). Remove the worktree when the PR is open.
- Sign in to GitHub as this agent's own GitHub App, never with the owner's login (murphy360/standards,
  "Agent identities"). Cut a version only when the owner says so in this session.
- Never `git stash`: a checkout's worktrees share one stash stack, so sessions collide. Commit what you need to keep.
- Never `git reset --soft` or `--hard` onto a base that moved on: merge the base in, so the history stays as it was.
- Before a push, run `git diff --stat origin/<base>...HEAD` and check it lists only this ticket's files.
- Tests run in the project's Docker image, not on the host. Build it under your own tag so parallel sessions never
  overwrite each other's images.
- Never touch the owner's running services, stacks or devices unless the ticket says so.
- Where the project has `.claude/settings.json`, Claude Code refuses the git and gh commands these rules forbid.

## Definition of done: one pull request

1. The change, small and readable, in the files the ticket names.
2. A unit test for every new behaviour, green in Docker. CI's run is the record: the PR body pastes no output.
3. The documentation in the same PR: the spec for the area, the user-facing manual, and a training or how-to line
   where the project has them. Write for the reader, not the developer.
4. The commit: the first line says what changed in plain words; the body says why; `Closes #N`; a `Note:` line for
   anything the deployer must do.
5. Open the pull request as a **draft** with `gh pr create --draft --base main` (a draft still runs CI), and comment
   the link on the ticket. Push to it as often as needed while you work. Once the tests and the lint are green
   locally, mark it ready **once**, with `gh pr ready`. After that, push again only to fix a CI failure or a review
   comment, and batch the fixes into one push.
6. The PR body: what and why, `Closes #N`, docs touched, any known issue with its ticket.
7. Queue it when it is ready: the owner wants finished pull requests merged. Add the project's merge label
   (for example `queue`) so its merge train tests and merges it; where a project has no train, squash-merge once the
   required checks are green. Never push to main, never enable auto-merge, never merge around the checks with an
   admin bypass. Leave the merge to the owner only when the ticket reserves it or a decision in it.

## Standards every project keeps (murphy360/standards)

- Before a push, run `pre-commit run --all-files`. It is the one command: what passes here passes the lint in CI,
  and a secret is caught before the commit. Install no linter, only `pip install pre-commit && pre-commit install`.
- The rules are in one place, and each finding prints its fix: https://github.com/murphy360/standards#the-rules
- Times are UTC. Secrets never go in the repository, a ticket or a log.
- A test fixture is made up, never a saved response from a real account, and holds no personal data: no real person's
  name, address, email, phone number, birth date, account or record number, location, health, school or money record.
- Prose in docs and tickets: short sentences, one idea per sentence, no em-dashes.

<!-- standards:shared:end -->

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
- **The data model** is `docs/DATA_MODEL.md`: change it in the same PR as any migration. Domain entities
  live in `api/app/domain/`, one module each; lists use `pagination.paginate`, memories go through
  `memories.visible_to`, deletes are soft.
- **Dates** are read by `api/app/dates/` (`docs/DATES.md`): save them with `set_point` or `set_range`, and
  from a job only with `set_by_job`, which never overwrites a date a person typed.
- **The web app** has two postures (phone captures, wide reviews) over one route list; `docs/FRONTEND.md`
  says where state lives and the component rules (under 300 lines, a dozen props, a section per page).
  `make smoke` checks it in a real browser against `make up`.
- **Recordings** go through `api/app/capture/` and the browser's upload queue
  (`web/src/features/record/uploads.ts`); `docs/CAPTURE.md` is the whole path. A job that needs a new handler
  module adds it to `api/app/jobs/catalog.py` so the worker loads it.
- **AI** goes through `api/app/ai/` (`docs/AI.md`): Gemini, Anthropic, Grok and OpenAI behind one interface,
  chosen per task by `registry.provider(settings, task)` (only Gemini and OpenAI hear audio). Prompts are
  versioned constants beside the task, every call is wrapped in `costs.recorded` (one `ai_calls` row each),
  tests use `FakeAI` via `registry.use`. No key means AI is off and nothing fails.
- **Placement** (`api/app/placement/`, `docs/TIMELINE.md`): the suggestion is a pure function of the dates
  and the storyteller's timeline; auto-filing runs once per quick memory or answer; what it makes is labelled
  and never remade by a job.
- **Questions** (`api/app/questions/`, `docs/INTERVIEWER.md`): de-duplicated as they are written, never when
  read; a question Memoir writes is skipped if the text was ever asked, so dismissing is permanent. An answer
  inherits its question's scope at upload (`capture/service.py`).
- **Errors** are always `{"error": {"code", "message", "field"}}` (`api/app/core/errors.py`). Raise
  `ApiError` from routes and services.
- **Background work is a job** (`api/app/jobs/`): register a handler with `@handler("area.kind")`, enqueue
  with an idempotency key, report progress with `ctx.progress(...)`. Never call an external provider
  inside a request.
- **Files are blobs** (`api/app/blobs/store.py`): content-addressed, verified on read. Never write files
  anywhere else.
- **Lint for the web** is node-lint, a second step of CI's `checks` job, in `web/`. TypeScript stays on
  5.x (typescript-eslint and openapi-typescript); Dependabot ignores its major.
- **Deployed** from the dontpanic stack (`~/Software/dontpanic`) at `https://dontpanic.ddns.net/memoir`;
  `deploy/compose.yml` is the reference copy of its services (CI validates it) and `docs/RUNBOOK.md` is how
  to deploy, back up, restore and rotate secrets. Data in `/docker/memoir`. Never touch it unless a ticket
  says so.
- **Privacy.** This holds a family's stories, photos and faces. Logs carry ids and durations, never
  transcripts, file contents or keys.
