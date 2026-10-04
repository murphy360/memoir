"""A throwaway PostgreSQL for the tests, from the server binaries in the test image.

Set MEMOIR_TEST_DATABASE_URL to use a database you already run instead.
"""

import glob
import os
import shutil
import subprocess
import tempfile
import time
from pathlib import Path


def _bin(name: str) -> str:
    found = shutil.which(name) or next(
        iter(sorted(glob.glob(f"/usr/lib/postgresql/*/bin/{name}"), reverse=True)), None
    )
    if not found:
        raise RuntimeError(f"{name} not found: run the tests in the api test image")
    return found


class TempPostgres:
    """initdb into a temporary directory and start on a Unix socket only."""

    def __init__(self):
        self.dir = Path(tempfile.mkdtemp(prefix="memoir-pg-"))
        self.data = self.dir / "data"

    def start(self) -> str:
        subprocess.run(
            [_bin("initdb"), "-D", str(self.data), "-U", "postgres", "-A", "trust"],
            check=True,
            capture_output=True,
        )
        opts = (
            f"-k {self.dir} -c listen_addresses='' -c fsync=off -c full_page_writes=off"
        )
        subprocess.run(
            [
                _bin("pg_ctl"),
                "-D",
                str(self.data),
                "-o",
                opts,
                "-w",
                "-l",
                str(self.dir / "log"),
                "start",
            ],
            check=True,
            capture_output=True,
        )
        for _ in range(50):
            if any(self.dir.glob(".s.PGSQL.*")):
                break
            time.sleep(0.1)
        subprocess.run(
            [_bin("createdb"), "-h", str(self.dir), "-U", "postgres", "memoir_test"],
            check=True,
            capture_output=True,
        )
        return f"postgresql+psycopg://postgres@/memoir_test?host={self.dir}"

    def stop(self) -> None:
        subprocess.run(
            [_bin("pg_ctl"), "-D", str(self.data), "-m", "immediate", "stop"],
            capture_output=True,
        )
        shutil.rmtree(self.dir, ignore_errors=True)


def database_url() -> tuple[str, TempPostgres | None]:
    url = os.environ.get("MEMOIR_TEST_DATABASE_URL")
    if url:
        return url, None
    pg = TempPostgres()
    return pg.start(), pg
