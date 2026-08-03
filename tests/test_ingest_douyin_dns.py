"""Tests for the Douyin-only Fake-IP DNS fallback."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest
import requests

from zhiji_backend.ingest.douyin_dns import (
    DOH_ENDPOINT,
    DOH_TIMEOUT,
    resolve_douyin_host,
)


class DoHResponse:
    def __init__(self, payload: dict, *, status_code: int = 200):
        self.payload = payload
        self.status_code = status_code

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise requests.HTTPError(f"HTTP {self.status_code}")

    def json(self) -> dict:
        return self.payload


def test_public_system_answer_bypasses_doh():
    doh_get = MagicMock(side_effect=AssertionError("DoH must not run"))
    answers = ["127.0.0.1", "93.184.216.34"]

    result = resolve_douyin_host(
        "cdn.example",
        443,
        system_resolver=lambda _host, _port: answers,
        doh_get=doh_get,
    )

    assert result == answers
    doh_get.assert_not_called()


@pytest.mark.parametrize(
    "answers",
    [
        [],
        ["127.0.0.1"],
        ["10.0.0.2"],
        ["169.254.1.2"],
        ["::1"],
        ["fd00::1"],
        ["fe80::1"],
        ["198.18.0.1", "10.0.0.2"],
        ["not-an-ip"],
    ],
)
def test_non_fake_private_or_invalid_answers_do_not_trigger_doh(answers):
    doh_get = MagicMock(side_effect=AssertionError("DoH must not run"))

    result = resolve_douyin_host(
        "internal.example",
        443,
        system_resolver=lambda _host, _port: answers,
        doh_get=doh_get,
    )

    assert result == answers
    doh_get.assert_not_called()


def test_all_fake_ip_answers_query_fixed_doh_for_a_and_aaaa():
    responses = {
        "A": DoHResponse(
            {
                "Status": 0,
                "Answer": [
                    {"type": 1, "data": "93.184.216.34"},
                    {"type": 5, "data": "ignored.example."},
                ],
            }
        ),
        "AAAA": DoHResponse(
            {
                "Status": 0,
                "Answer": [
                    {
                        "type": 28,
                        "data": "2606:2800:220:1:248:1893:25c8:1946",
                    }
                ],
            }
        ),
    }
    calls = []

    def doh_get(url, **kwargs):
        calls.append((url, kwargs))
        return responses[kwargs["params"]["type"]]

    result = resolve_douyin_host(
        "dynamic.cdn.example",
        443,
        system_resolver=lambda _host, _port: ["198.18.40.216"],
        doh_get=doh_get,
    )

    assert result == [
        "93.184.216.34",
        "2606:2800:220:1:248:1893:25c8:1946",
    ]
    assert [call[0] for call in calls] == [DOH_ENDPOINT, DOH_ENDPOINT]
    assert [call[1]["params"] for call in calls] == [
        {"name": "dynamic.cdn.example", "type": "A"},
        {"name": "dynamic.cdn.example", "type": "AAAA"},
    ]
    assert all(call[1]["allow_redirects"] is False for call in calls)
    assert all(call[1]["headers"] == {"Accept": "application/dns-json"} for call in calls)
    assert all(call[1]["timeout"] == DOH_TIMEOUT for call in calls)
    assert all("cookies" not in call[1] and "session" not in call[1] for call in calls)


def test_empty_record_family_is_allowed_when_other_family_has_public_answer():
    responses = iter(
        [
            DoHResponse({"Status": 0, "Answer": []}),
            DoHResponse(
                {
                    "Status": 0,
                    "Answer": [
                        {
                            "type": 28,
                            "data": "2606:2800:220:1:248:1893:25c8:1946",
                        }
                    ],
                }
            ),
        ]
    )

    result = resolve_douyin_host(
        "cdn.example",
        443,
        system_resolver=lambda _host, _port: ["198.18.0.1"],
        doh_get=lambda *_args, **_kwargs: next(responses),
    )

    assert result == ["2606:2800:220:1:248:1893:25c8:1946"]


@pytest.mark.parametrize(
    "payload",
    [
        {"Status": 2, "Answer": [{"type": 1, "data": "93.184.216.34"}]},
        {"Status": 0, "Answer": []},
        {"Status": 0, "Answer": [{"type": 1, "data": "not-an-ip"}]},
        {"Status": 0, "Answer": [{"type": 1, "data": "127.0.0.1"}]},
        {"Status": 0, "Answer": [{"type": 1, "data": "10.0.0.2"}]},
    ],
)
def test_doh_invalid_or_non_public_answers_fail_closed(payload):
    with pytest.raises(ValueError, match="抖音媒体公网 DNS"):
        resolve_douyin_host(
            "cdn.example",
            443,
            system_resolver=lambda _host, _port: ["198.18.0.1"],
            doh_get=lambda *_args, **_kwargs: DoHResponse(payload),
        )


@pytest.mark.parametrize(
    "error",
    [requests.Timeout("timeout"), requests.ConnectionError("down")],
)
def test_doh_network_errors_fail_closed(error):
    with pytest.raises(ValueError, match="抖音媒体公网 DNS"):
        resolve_douyin_host(
            "cdn.example",
            443,
            system_resolver=lambda _host, _port: ["198.18.0.1"],
            doh_get=MagicMock(side_effect=error),
        )


def test_doh_redirect_response_fails_closed():
    with pytest.raises(ValueError, match="抖音媒体公网 DNS"):
        resolve_douyin_host(
            "cdn.example",
            443,
            system_resolver=lambda _host, _port: ["198.18.0.1"],
            doh_get=lambda *_args, **_kwargs: DoHResponse({}, status_code=302),
        )
