import hashlib

import pytest

from app.blobs.store import BlobError, BlobStore


@pytest.fixture
def store(tmp_path):
    return BlobStore(tmp_path)


def test_storing_the_same_bytes_twice_keeps_one_blob(store, session):
    a = store.put_bytes(session, b"hello", "text/plain")
    b = store.put_bytes(session, b"hello", "text/plain")
    assert a.sha256 == b.sha256 == hashlib.sha256(b"hello").hexdigest()
    assert a.size_bytes == 5
    assert len(list(store.root.glob("??/*"))) == 1


def test_a_blob_reads_back_in_chunks(store, session):
    data = bytes(range(256)) * 10_000
    blob = store.put(session, [data[:1000], data[1000:]], "application/octet-stream")
    assert b"".join(store.read(blob.sha256)) == data


def test_an_upload_that_does_not_match_its_hash_is_refused(store, session):
    with pytest.raises(BlobError, match="does not match"):
        store.put(session, [b"abc"], "text/plain", expected_sha256="0" * 64)
    assert not list(store.root.glob("??/*"))
    assert not list((store.root / "tmp").iterdir())


def test_a_file_corrupted_on_disk_is_refused(store, session):
    blob = store.put_bytes(session, b"original", "text/plain")
    store.path(blob.sha256).write_bytes(b"tampered")
    with pytest.raises(BlobError, match="corrupt"):
        b"".join(store.read(blob.sha256))


def test_a_missing_file_is_refused(store, session):
    blob = store.put_bytes(session, b"here", "text/plain")
    store.path(blob.sha256).unlink()
    with pytest.raises(BlobError, match="missing"):
        store.verify(blob.sha256)
