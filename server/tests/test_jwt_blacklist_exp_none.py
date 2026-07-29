"""Focused regression: blacklist guard for tokens whose payload has no exp.

`JWTAuth.logout` / `refresh_access_token` must skip blacklisting when the
decoded payload carries a jti but no exp claim (`TokenBlacklist.add` requires a
datetime and would crash on None). Tokens with exp keep being blacklisted.
"""

from __future__ import annotations

import jwt as pyjwt
import pytest

from security.jwt_auth import JWTAuth, Role, TokenPayload

SECRET = "exp-none-regression-secret"


@pytest.fixture()
def auth(tmp_path, monkeypatch):
    monkeypatch.setenv("JWT_SECRET_KEY", SECRET)
    return JWTAuth(secret_key=SECRET, db_path=str(tmp_path / "jwt_exp_none.db"))


def _encode_without_exp(auth: JWTAuth, user_id: str, jti: str, permissions: list[str] | None = None) -> str:
    """Build a token whose payload has jti but no exp claim."""
    payload = TokenPayload(
        user_id=user_id,
        username="exp-none-user",
        role=Role.USER,
        permissions=permissions or [],
        exp=None,
        jti=jti,
    )
    assert "exp" not in payload.to_dict()
    return pyjwt.encode(payload.to_dict(), auth.secret_key, algorithm=auth.algorithm)


def test_logout_access_token_without_exp_does_not_crash_or_blacklist(auth):
    uid = auth.register_user("exp-none-user", "password123")
    token = _encode_without_exp(auth, uid, jti="jti-access-no-exp")

    auth.logout(token)

    assert not auth.blacklist.contains("jti-access-no-exp")


def test_logout_refresh_token_without_exp_does_not_crash_or_blacklist(auth):
    uid = auth.register_user("exp-none-user", "password123")
    access = _encode_without_exp(auth, uid, jti="jti-access-no-exp")
    refresh = _encode_without_exp(auth, uid, jti="jti-refresh-no-exp")

    auth.logout(access, refresh_token=refresh)

    assert not auth.blacklist.contains("jti-refresh-no-exp")


def test_refresh_access_token_without_exp_rotates_without_crash(auth):
    uid = auth.register_user("exp-none-user", "password123")
    refresh = _encode_without_exp(auth, uid, jti="jti-refresh-rotate")

    pair = auth.refresh_access_token(refresh)

    assert pair.access_token
    assert not auth.blacklist.contains("jti-refresh-rotate")


def test_logout_token_with_exp_still_blacklists(auth):
    """Guard must not weaken the normal path: exp-bearing tokens get revoked."""
    uid = auth.register_user("exp-none-user", "password123")
    pair = auth.create_token_pair(user_id=uid)
    payload = auth.verify_token(pair.access_token)
    assert payload.jti and payload.exp

    auth.logout(pair.access_token)

    assert auth.blacklist.contains(payload.jti)
