import pytest

from app.accounts.passwords import check_rules, hash_password, verify_password
from app.core.errors import ApiError


def test_hashes_are_argon2id_and_verify():
    h = hash_password("a perfectly fine phrase")
    assert h.startswith("$argon2id$")
    assert verify_password(h, "a perfectly fine phrase")
    assert not verify_password(h, "a perfectly fine phrasE")
    assert not verify_password("not a hash", "anything")


@pytest.mark.parametrize(
    "password", ["short", "aaaaaaaaaaaaaaaa", "Password1234", "x" * 257]
)
def test_weak_passwords_are_refused(password):
    with pytest.raises(ApiError) as e:
        check_rules(password)
    assert e.value.code == "weak_password"


def test_the_email_is_not_a_password():
    with pytest.raises(ApiError):
        check_rules("owner@example.org", "Owner@Example.org")


def test_no_composition_rules():
    check_rules("all lower case words here")
