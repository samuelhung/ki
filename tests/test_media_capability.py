from __future__ import annotations

from urllib.parse import parse_qs, urlsplit

import pytest

from zhiji_backend import media_capability
from zhiji_backend.media_capability import (
    MAX_CLOCK_SKEW_SECONDS,
    MEDIA_URL_TTL_SECONDS,
    create_video_url,
    verify_video_capability,
)

NOW = 1_800_000_000
TOKEN = "secret-token"
FILENAME = "evt-ingest-1.mp4"


def _signed_values(filename: str = FILENAME) -> tuple[str, str, str]:
    url = create_video_url(filename, api_token=TOKEN, now=NOW)
    assert url is not None
    query = parse_qs(urlsplit(url).query)
    return url, query["expires"][0], query["signature"][0]


def test_create_video_url_is_scoped_and_verifiable() -> None:
    url, expires, signature = _signed_values()
    parts = urlsplit(url)

    assert parts.path == "/media/videos/evt-ingest-1.mp4"
    assert expires == str(NOW + MEDIA_URL_TTL_SECONDS)
    assert "secret-token" not in url
    assert verify_video_capability(
        FILENAME,
        expires=expires,
        signature=signature,
        api_token=TOKEN,
        now=NOW,
    )


@pytest.mark.parametrize("extension", ["mp4", "mov", "avi", "mkv", "webm", "mts", "ts", "flv"])
def test_create_video_url_accepts_existing_ingest_video_extensions(extension: str) -> None:
    assert create_video_url(f"evt-1.{extension}", api_token=TOKEN, now=NOW)


@pytest.mark.parametrize(
    ("filename", "expires_transform", "signature_transform", "token", "now"),
    [
        ("evt-ingest-2.mp4", lambda value: value, lambda value: value, TOKEN, NOW),
        (FILENAME, lambda value: str(int(value) + 1), lambda value: value, TOKEN, NOW),
        (FILENAME, lambda value: value, lambda value: "0" * len(value), TOKEN, NOW),
        (FILENAME, lambda value: value, lambda value: value, "wrong-token", NOW),
        (FILENAME, lambda value: value, lambda value: value, TOKEN, NOW + MEDIA_URL_TTL_SECONDS + 1),
    ],
)
def test_verify_video_capability_rejects_tampering_and_expiry(
    filename: str,
    expires_transform,
    signature_transform,
    token: str,
    now: int,
) -> None:
    _, expires, signature = _signed_values()

    assert not verify_video_capability(
        filename,
        expires=expires_transform(expires),
        signature=signature_transform(signature),
        api_token=token,
        now=now,
    )


@pytest.mark.parametrize("expires", ["", "not-a-number", "+1800001800", "1800001800.0"])
def test_verify_video_capability_rejects_non_decimal_expiry(expires: str) -> None:
    _, _, signature = _signed_values()

    assert not verify_video_capability(
        FILENAME,
        expires=expires,
        signature=signature,
        api_token=TOKEN,
        now=NOW,
    )


def test_verify_video_capability_rejects_expiry_beyond_allowed_window() -> None:
    far_expiry = str(NOW + MEDIA_URL_TTL_SECONDS + MAX_CLOCK_SKEW_SECONDS + 1)
    _, _, signature = _signed_values()

    assert not verify_video_capability(
        FILENAME,
        expires=far_expiry,
        signature=signature,
        api_token=TOKEN,
        now=NOW,
    )


@pytest.mark.parametrize(
    "filename",
    ["../evt.mp4", "folder/evt.mp4", "evt.mp3", "evt.pdf", "evt.exe", "evt"],
)
def test_create_video_url_rejects_unsafe_or_non_video_filenames(filename: str) -> None:
    assert create_video_url(filename, api_token=TOKEN, now=NOW) is None


def test_empty_token_never_creates_or_verifies_a_capability() -> None:
    _, expires, signature = _signed_values()

    assert create_video_url(FILENAME, api_token="", now=NOW) is None
    assert not verify_video_capability(
        FILENAME,
        expires=expires,
        signature=signature,
        api_token="",
        now=NOW,
    )


def test_valid_verification_uses_constant_time_comparison(monkeypatch) -> None:
    _, expires, signature = _signed_values()
    calls: list[tuple[str, str]] = []

    def compare_digest(candidate: str, expected: str) -> bool:
        calls.append((candidate, expected))
        return candidate == expected

    monkeypatch.setattr(media_capability.hmac, "compare_digest", compare_digest)

    assert verify_video_capability(
        FILENAME,
        expires=expires,
        signature=signature,
        api_token=TOKEN,
        now=NOW,
    )
    assert calls == [(signature, signature)]
