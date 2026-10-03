"""The content-addressed store: a file's name is the SHA-256 of its bytes.

Files live at `<root>/<first two hex digits>/<sha256>`, so no directory holds more
than a few thousand files. Writing is atomic (a temporary file, then a rename),
storing the same bytes twice keeps one file, and reading checks the hash, so a
corrupted file is refused rather than served.
"""

import hashlib
import os
import tempfile
from collections.abc import Iterable
from pathlib import Path

from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.blobs.models import Blob
from app.core.db import utcnow

CHUNK = 1024 * 1024


class BlobError(Exception):
    """A blob that does not match its hash, or one that is missing."""


class BlobStore:
    def __init__(self, root: Path):
        self.root = Path(root)

    def path(self, sha256: str) -> Path:
        return self.root / sha256[:2] / sha256

    def put(
        self,
        session: Session,
        chunks: Iterable[bytes],
        content_type: str,
        *,
        expected_sha256: str | None = None,
    ) -> Blob:
        """Store the bytes and record the blob, then commit.

        Bytes already stored return the existing blob.
        """
        tmp_dir = self.root / "tmp"
        tmp_dir.mkdir(parents=True, exist_ok=True)
        digest, size = hashlib.sha256(), 0
        fd, tmp_name = tempfile.mkstemp(dir=tmp_dir)
        try:
            with os.fdopen(fd, "wb") as out:
                for chunk in chunks:
                    digest.update(chunk)
                    size += len(chunk)
                    out.write(chunk)
                out.flush()
                os.fsync(out.fileno())
            sha = digest.hexdigest()
            if expected_sha256 and expected_sha256 != sha:
                raise BlobError(f"upload does not match its hash: got {sha}")
            final = self.path(sha)
            final.parent.mkdir(parents=True, exist_ok=True)
            if final.exists():
                os.unlink(tmp_name)
            else:
                os.replace(tmp_name, final)
        except BaseException:
            if os.path.exists(tmp_name):
                os.unlink(tmp_name)
            raise
        stmt = insert(Blob).values(
            sha256=sha, size_bytes=size, content_type=content_type, created_at=utcnow()
        )
        session.execute(stmt.on_conflict_do_nothing(index_elements=["sha256"]))
        session.commit()
        return session.get(Blob, sha)

    def put_bytes(self, session: Session, data: bytes, content_type: str) -> Blob:
        return self.put(session, [data], content_type)

    def read(self, sha256: str) -> Iterable[bytes]:
        """The blob's bytes in chunks, after checking them against the hash."""
        self.verify(sha256)
        with self.path(sha256).open("rb") as f:
            while chunk := f.read(CHUNK):
                yield chunk

    def verify(self, sha256: str) -> None:
        path = self.path(sha256)
        if not path.is_file():
            raise BlobError(f"blob {sha256} is missing")
        digest = hashlib.sha256()
        with path.open("rb") as f:
            while chunk := f.read(CHUNK):
                digest.update(chunk)
        if digest.hexdigest() != sha256:
            raise BlobError(f"blob {sha256} is corrupt on disk")
