# Browser checks

`smoke.py` signs in and opens every page of the shell in both postures (phone 390 px, wide 1280 px), reloads each
to prove the deep link holds, checks there is one `main` landmark, and tabs through the navigation by keyboard. It
runs against a running stack:

```bash
make up
docker compose exec memoir-api memoir-cli create-owner --email owner@example.org --name Owner
MEMOIR_PASSWORD='the owner password' make smoke
```

Screenshots of both postures land in `e2e/out/`.
