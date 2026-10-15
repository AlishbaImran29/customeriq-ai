"""Password hashing, tokens and the password policy (no database needed)."""

import pytest

from app.core import security


@pytest.fixture(autouse=True)
def fast_hashing(monkeypatch):
    monkeypatch.setattr(security, "SCRYPT_N", 2**10)
    monkeypatch.setattr(security, "SCRYPT_P", 1)


def test_hash_and_verify_round_trip():
    stored = security.hash_password("correct horse battery")
    assert stored.startswith("scrypt$") and "correct horse" not in stored
    assert security.verify_password("correct horse battery", stored)
    assert not security.verify_password("correct horse batterY", stored)


def test_same_password_gets_different_hashes():
    assert security.hash_password("correct horse battery") != security.hash_password("correct horse battery")


def test_old_hashes_keep_working_after_the_cost_changes(monkeypatch):
    stored = security.hash_password("correct horse battery")
    monkeypatch.setattr(security, "SCRYPT_N", 2**11)  # cost is stored inside the hash
    assert security.verify_password("correct horse battery", stored)


@pytest.mark.parametrize("stored", ["", "garbage", "scrypt$1$2$3", "bcrypt$a$b$c$d$e", "scrypt$x$8$1$AA==$AA=="])
def test_malformed_hashes_fail_safely(stored):
    assert security.verify_password("anything", stored) is False


def test_tokens_are_random_and_hashed_for_storage():
    a, b = security.new_session_token(), security.new_session_token()
    assert a != b and len(a) >= 40
    assert security.hash_token(a) == security.hash_token(a) != security.hash_token(b)
    assert a not in security.hash_token(a) and len(security.hash_token(a)) == 64


@pytest.mark.parametrize("password, email, fragment", [
    ("short1", "", "at least 10"),
    ("1234567890", "", "too easy"),
    ("aaaaaaaaaaaa", "", "too easy"),
    ("Password123", "", "too easy"),  # capital letters don't hide a common password
    ("password123", "", "too easy"),
    ("Tr0ub4dor&3xyz", "", None),
    ("maryjane-rocks-2026", "maryjane@example.com", "email name"),
    ("x" * 129, "", "at most 128"),
    ("blue tractor sings loudly", "owner@example.com", None),
])
def test_password_policy(password, email, fragment):
    problem = security.password_problem(password, email)
    if fragment is None:
        assert problem is None
    else:
        assert problem is not None and fragment in problem


@pytest.mark.parametrize("email, valid", [
    ("a@b.co", True), ("first.last+tag@example.com", True),
    ("no-at-sign", False), ("two@@example.com", False), ("spaces in@example.com", False), ("a@b", False),
])
def test_email_validation(email, valid):
    assert security.is_valid_email(email) is valid


def test_email_is_normalised():
    assert security.normalise_email("  Owner@Example.COM ") == "owner@example.com"
