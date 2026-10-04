"""Password hashing (argon2id) and the password rules.

The rules are the ones that matter: at least 12 characters, no composition rules,
and not one of the passwords everyone guesses first. A bundled breach list is left
for later.
"""

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError

from app.core.errors import ApiError

MIN_LENGTH = 12
MAX_LENGTH = 256
_hasher = PasswordHasher()

# Long passwords that still top every breach list. Compared after lower-casing.
_COMMON = {
    "123456789012",
    "1234567890123",
    "12345678901234",
    "qwertyuiop12",
    "qwertyuiopasdf",
    "passwordpassword",
    "password1234",
    "password12345",
    "iloveyou1234",
    "letmein12345",
    "abcdefghijkl",
    "abc123456789",
}


def check_rules(password: str, email: str = "") -> None:
    """Raise a 422 with a plain message when the password breaks a rule."""
    if len(password) < MIN_LENGTH:
        raise ApiError(422, "weak_password", "Use at least 12 characters.", "password")
    if len(password) > MAX_LENGTH:
        raise ApiError(422, "weak_password", "Use at most 256 characters.", "password")
    lowered = password.lower()
    if len(set(password)) == 1 or lowered in _COMMON:
        raise ApiError(
            422,
            "weak_password",
            "That password is one of the first ones anyone would guess.",
            "password",
        )
    if email and lowered == email.lower():
        raise ApiError(
            422, "weak_password", "Your password cannot be your email.", "password"
        )


def hash_password(password: str) -> str:
    return _hasher.hash(password)


def verify_password(stored_hash: str, password: str) -> bool:
    try:
        return _hasher.verify(stored_hash, password)
    except (VerificationError, InvalidHashError):
        return False


# A real hash to check against when the email is unknown, so timing does not tell.
DUMMY_HASH = hash_password("memoir-timing-equaliser")
