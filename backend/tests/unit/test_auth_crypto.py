from __future__ import annotations

import jwt
import pytest
from app.core.config import AuthSettings
from app.core.errors import ApplicationError
from app.core.ids import uuid7
from app.modules.auth.crypto import AccessTokenCodec, OpaqueTokenCodec, OtpCodec, PasswordCodec
from app.modules.auth.enums import Role
from app.modules.auth.service import AuthService


def test_uuid7_has_expected_version_and_variant() -> None:
    first = uuid7()
    second = uuid7()

    assert first.version == 7
    assert first.variant == "specified in RFC 4122"
    assert abs((first.int >> 80) - (second.int >> 80)) <= 10
    assert first != second


def test_otp_is_fixed_length_and_bound_to_challenge() -> None:
    codec = OtpCodec(AuthSettings())
    challenge_id = uuid7()
    other_challenge_id = uuid7()
    code = codec.generate()
    digest = codec.digest(challenge_id, code)

    assert len(code) == 6
    assert code.isdecimal()
    assert codec.verify(challenge_id, code, digest)
    assert not codec.verify(other_challenge_id, code, digest)
    assert not codec.verify(challenge_id, "000000", digest) or code == "000000"


def test_opaque_refresh_token_digest_is_keyed() -> None:
    first = OpaqueTokenCodec(AuthSettings())
    second_settings = AuthSettings(refresh_token_secret="a-different-secret-with-at-least-32-chars")
    second = OpaqueTokenCodec(second_settings)
    token = first.generate()

    assert len(first.digest(token)) == 32
    assert first.digest(token) == first.digest(token)
    assert first.digest(token) != second.digest(token)


def test_access_token_round_trip_and_signature_validation() -> None:
    codec = AccessTokenCodec(AuthSettings())
    user_id = uuid7()
    session_id = uuid7()
    token = codec.encode(user_id=user_id, session_id=session_id, roles={Role.USER, Role.ADMIN})
    claims = codec.decode(token)

    assert claims.user_id == user_id
    assert claims.session_id == session_id
    assert claims.roles == frozenset({Role.USER, Role.ADMIN})

    other_codec = AccessTokenCodec(
        AuthSettings(jwt={"secret": "a-different-jwt-secret-with-at-least-32-characters"})
    )
    with pytest.raises(jwt.InvalidSignatureError):
        other_codec.decode(token)


def test_password_codec_uses_one_way_verification() -> None:
    codec = PasswordCodec()
    encoded = codec.hash("correct horse battery staple")

    assert "correct horse battery staple" not in encoded
    assert codec.verify(encoded, "correct horse battery staple")
    assert not codec.verify(encoded, "incorrect")
    assert not codec.verify("not-an-argon-hash", "incorrect")


def test_csrf_requires_matching_cookie_and_header() -> None:
    AuthService.verify_csrf("same-token", "same-token")

    with pytest.raises(ApplicationError) as exc_info:
        AuthService.verify_csrf("same-token", "different-token")
    assert exc_info.value.code == "csrf_validation_failed"
