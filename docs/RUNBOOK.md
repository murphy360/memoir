# Runbook

How Memoir runs at **https://dontpanic.ddns.net/memoir**, and what to do when. The services live in the dontpanic
stack (`~/Software/dontpanic/docker-compose.yml`); `deploy/compose.yml` in this repository is the same four services,
validated in CI, and `deploy/Caddyfile` is the Caddy block. Commands below run on dontpanic from
`~/Software/dontpanic` unless they say otherwise.

## What runs where

| Service | Image | What |
|---|---|---|
| `memoir-db` | `postgres:17-alpine` | The database, in `/docker/memoir/postgres`. Only the `memoir` network reaches it |
| `memoir-api` | `ghcr.io/murphy360/memoir-api:main` | The API. Applies migrations on start, under a lock. Caddy sends `/memoir/api/*` here with `/memoir` stripped |
| `memoir-worker` | `ghcr.io/murphy360/memoir-worker:main` | Background jobs. Healthy while its heartbeat is under a minute old (`memoir-cli worker-alive`) |
| `memoir-web` | `ghcr.io/murphy360/memoir-web:main` | The app, built for `/memoir`. Caddy sends every other `/memoir` path here |

| On the host | What | Owner, mode |
|---|---|---|
| `/docker/memoir/memoir.env` | The app's secrets: `MEMOIR_DATABASE_URL`, and optionally `MEMOIR_AI_PROVIDER` | root, 600 |
| `~/Software/dontpanic/.env` | Memoir's own AI keys, `GEMINI_API_KEY_MEMOIR`, `ANTHROPIC_API_KEY_MEMOIR` and `GROK_API_KEY_MEMOIR`. Compose passes them to the API and the worker as `MEMOIR_GEMINI_API_KEY` and so on. (`OPENAI_API_KEY_MEMOIR` is there too, unused: Memoir has no OpenAI adapter) | the owner |
| `/docker/memoir/postgres.env` | `POSTGRES_PASSWORD`, used only when the database is first created | root, 600 |
| `/docker/memoir/postgres` | The database files | the image's postgres user |
| `/docker/memoir/blobs` | Recordings and files, content-addressed | uid 1000 |
| `/media/backups/memoir` | Nightly backups, on the ZFS pool (another disk from `/docker`) | root |

There is no basic auth in front: the app's own login guards every page and API route. `/api/health` is the only
public route, and it shows the database and the worker:

```sh
curl -s https://dontpanic.ddns.net/memoir/api/health
# {"status":"ok","version":"0.1.0","database":"ok","worker":{"status":"ok",...,"age_seconds":4.2}}
curl -s https://dontpanic.ddns.net/memoir/api/memories
# {"error":{"code":"unauthenticated","message":"Please sign in.",...}}   (401 from the app, not Caddy)
```

`docker compose ps memoir-db memoir-api memoir-worker memoir-web` shows all four `(healthy)`.

## First deploy

Once, after the v0.1 pull requests are merged and the images are published. Version 0 keeps running beside the
rewrite at `/memoir-v0` until the owner retires it (the dontpanic pull request moves it).

1. **Move version 0 out of the way.** Its environment file becomes `v0.env`, and its images get their own names,
   so a pull of the rewrite never lands in version 0's containers. The web image is rebuilt for `/memoir-v0`
   (Next.js bakes the base path in at build time):

   ```sh
   sudo mv /docker/memoir/memoir.env /docker/memoir/v0.env
   docker tag ghcr.io/murphy360/memoir-api:main ghcr.io/murphy360/memoir-v0-api:main
   (cd ~/Software/memoir-v0 && docker build --build-arg NEXT_PUBLIC_BASE_PATH=/memoir-v0 \
       -t ghcr.io/murphy360/memoir-v0-web:main frontend)
   ```

2. **Directories and secrets.** One password, in both files:

   ```sh
   sudo install -d -m 700 /docker/memoir/postgres
   sudo install -d -o 1000 -g 1000 /docker/memoir/blobs
   pw="$(openssl rand -hex 24)"
   echo "POSTGRES_PASSWORD=$pw" | sudo tee /docker/memoir/postgres.env >/dev/null
   printf 'MEMOIR_DATABASE_URL=postgresql+psycopg://memoir:%s@memoir-db:5432/memoir\n' "$pw" \
       | sudo tee /docker/memoir/memoir.env >/dev/null
   # The AI keys come from the stack's .env (the table above). To have Claude or Grok read the
   # transcripts and ask the questions instead of Gemini (docs/AI.md):
   #   echo 'MEMOIR_AI_PROVIDER=anthropic' | sudo tee -a /docker/memoir/memoir.env >/dev/null
   sudo chmod 600 /docker/memoir/memoir.env /docker/memoir/postgres.env
   unset pw
   ```

3. **Start it**, with Caddy picking up the new routes:

   ```sh
   docker compose pull memoir-api memoir-worker memoir-web
   docker compose up -d memoir-db memoir-api memoir-worker memoir-web memoir-v0-api memoir-v0-web
   docker compose up -d --force-recreate caddy
   ```

4. **Create the owner** (asks for the password twice; 12 characters or more):

   ```sh
   docker exec -it memoir-api memoir-cli create-owner --email c.murphy360@gmail.com --name Corey \
       --archive "Murphy family"
   ```

5. **Check**: the two `curl` lines above, sign in at https://dontpanic.ddns.net/memoir on a phone, record a few
   seconds, and see it saved.

6. **Schedule the backup** (below), and run it once by hand.

## Deploy a new build

Merging to `main` publishes new images. Then:

```sh
docker compose pull memoir-api memoir-worker memoir-web
docker compose up -d memoir-api memoir-worker memoir-web
```

The API applies any new migrations as it starts (under a lock, so the worker waits); the worker starts once the API
is healthy. A pull request's commit message says in a `Note:` line if a deploy needs anything more.

To go back, run the previous image: `docker images ghcr.io/murphy360/memoir-api` lists them, and
`docker compose up -d` with the old image's digest in place of `:main` runs it. A migration has run by then, so
going back past a migration means restoring last night's backup.

## Backups

`install/memoir-backup.sh` in the dontpanic repository (the same as `deploy/backup.sh` here) writes:

- `db/memoir-YYYY-MM-DD.dump`: `pg_dump` in custom format. Kept 30 days (`MEMOIR_BACKUP_KEEP_DAYS`).
- `blobs/`: every blob, copied with `rsync` and never deleted, so a file a purge removed stays recoverable.

The database is dumped first and the blobs copied after. A blob is written before the row that names it, so every
file the dump refers to is in the copy. Schedule it in root's crontab (`sudo crontab -e`):

```
15 3 * * * /home/murphy360/Software/dontpanic/install/memoir-backup.sh >>/var/log/memoir-backup.log 2>&1
```

`MEMOIR_BACKUP_TARGET` changes where backups go (default `/media/backups/memoir`).

## Restore

1. Stop what writes: `docker compose stop memoir-api memoir-worker`.
2. Restore the dump and the blobs. `restore.sh` refuses a database that already holds Memoir unless told to
   replace it:

   ```sh
   sudo MEMOIR_RESTORE_OVERWRITE=yes ~/Software/memoir/deploy/restore.sh \
       /media/backups/memoir/db/memoir-2026-10-03.dump /media/backups/memoir/blobs memoir-db /docker/memoir/blobs
   ```

3. Start again: `docker compose up -d memoir-api memoir-worker`, then check health.

To restore onto a fresh machine, do the first deploy's steps 2 and 3 with `memoir-db` only, restore, then start the
rest. Skip creating the owner: the owner comes back with the data.

## Restore drill

| Date | Where | What was checked | Result |
|---|---|---|---|
| 2026-10-03 | Locally, two scratch compose projects on bind mounts under `/tmp`, the same images | Six recorded memories (audio, transcripts, questions, a placed event): `backup.sh`, then `restore.sh` into a new empty database and blob directory, then the app started on them | Same counts (6 memories, 9 questions, 12 blobs, 1 event, 1 user). The owner signed in. A restored recording played, and its SHA-256 matched its blob. A second restore was refused. Health ok with the worker seen |

Repeat it on dontpanic after the first deploy, against a scratch database, and add a row:

```sh
docker run -d --name memoir-drill-db -e POSTGRES_USER=memoir -e POSTGRES_DB=memoir \
    -e POSTGRES_PASSWORD=drill postgres:17-alpine
sudo ~/Software/memoir/deploy/restore.sh /media/backups/memoir/db/memoir-$(date +%F).dump \
    /media/backups/memoir/blobs memoir-drill-db /tmp/memoir-drill-blobs
docker exec memoir-drill-db psql -U memoir -d memoir -c "SELECT count(*) FROM memories"
docker rm -f memoir-drill-db && sudo rm -r /tmp/memoir-drill-blobs
```

## Rotate a secret

- **An AI key.** Edit `GEMINI_API_KEY_MEMOIR`, `ANTHROPIC_API_KEY_MEMOIR` or `GROK_API_KEY_MEMOIR` in the stack's
  `.env`, then `docker compose up -d --force-recreate memoir-api memoir-worker`. A key is only ever in that file
  and in a request header; it is never logged.
- **The database password.** Change it in the database, then in both files, then recreate the API and the worker:

  ```sh
  pw="$(openssl rand -hex 24)"
  docker exec memoir-db psql -U memoir -d memoir -c "ALTER USER memoir PASSWORD '$pw'"
  # Put $pw in POSTGRES_PASSWORD (postgres.env) and in MEMOIR_DATABASE_URL (memoir.env).
  docker compose up -d --force-recreate memoir-api memoir-worker
  unset pw
  ```

- **Everyone's sessions.** A user signs out everywhere from their account page; the owner removing a user ends
  theirs.

## People

- **Add someone.** The owner opens *People with access* and creates an invitation link (single use, 7 days), then
  sends it. There is no open sign-up.
- **Someone forgot their password.** The owner sets a temporary one on *People with access*; they choose their own
  at the next sign-in.
- **The owner forgot theirs.** From the host:

  ```sh
  docker exec -it memoir-api memoir-cli reset-password --email c.murphy360@gmail.com
  ```

  It sets a temporary password, signs out every session, and asks for a new one at the next sign-in.

## When something is wrong

| Symptom | Look at |
|---|---|
| `/api/health` says the worker is `stale` | `docker compose logs --tail 100 memoir-worker`. A long transcription keeps it fresh, so stale means stopped or stuck. `docker compose restart memoir-worker` is safe: a job it held is picked up again |
| Recordings say "AI is off" | `GEMINI_API_KEY_MEMOIR` in the stack's `.env` (only Gemini transcribes), and the owner's AI settings. `/api/ai/status` says which provider does each task |
| Recordings say transcription failed with "402" | The Gemini project is out of prepaid credit. Top it up, then **Try again** on each memory |
| 502 from Caddy | `docker compose ps`: which `memoir-*` service is not healthy, then its logs |
| Disk filling | `du -sh /docker/memoir/*`. Recordings are kept forever by design. Soft-deleted rows purge after 30 days |
