from __future__ import annotations

import asyncio
import io
import json
import logging
import os
import stat
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from zhiji_backend.security.redaction import (
    MAX_REDACTED_TEXT_LENGTH,
    REDACTED,
    RedactingFormatter,
    SecureTimedRotatingFileHandler,
    classify_task_error,
    redact_text,
    sanitize_task_error,
)


@pytest.mark.parametrize(
    ("text", "secret"),
    [
        ("Authorization: Bearer bearer-secret-123", "bearer-secret-123"),
        ("X-API-Key=header-key-456", "header-key-456"),
        ("OPENAI_API_KEY=sk-openai-secret", "sk-openai-secret"),
        ('{"api_key":"json-provider-secret"}', "json-provider-secret"),
        ('{"Authorization":"Bearer json-bearer-secret"}', "json-bearer-secret"),
        ("api_key: provider-secret", "provider-secret"),
        ("Cookie: session=cookie-secret; theme=dark", "cookie-secret"),
        ("signature=signature-secret", "signature-secret"),
        ("access_token=access-secret", "access-secret"),
        (
            "https://example.test/callback?token=query-secret&safe=value",
            "query-secret",
        ),
        (
            "https://storage.test/file?X-Amz-Signature=aws-signature-secret",
            "aws-signature-secret",
        ),
        (
            "https://example.test/callback?%74oken=encoded-query-secret",
            "encoded-query-secret",
        ),
        (
            "https://storage.test/file?X-Amz-Security-Token=aws-token-secret",
            "aws-token-secret",
        ),
        ("https://user:user-password@example.test/private", "user-password"),
        ("failed reading /Users/alice/.zhiji/.env", "/Users/alice/.zhiji/.env"),
        ("prompt=plaintext private prompt", "plaintext private prompt"),
        ("response_body=plaintext model response", "plaintext model response"),
    ],
)
def test_redact_text_removes_common_secret_forms(text, secret):
    redacted = redact_text(text)

    assert secret not in redacted
    assert REDACTED in redacted


def test_redact_text_is_deterministic_and_preserves_non_sensitive_query_values():
    text = "GET https://example.test/items?token=secret&limit=20"

    assert redact_text(text) == redact_text(text)
    assert "limit=20" in redact_text(text)


def test_redact_text_scrubs_json_dumped_message_content_and_preserves_roles():
    messages = [
        {"role": "system", "content": "system prompt secret"},
        {"role": "user", "content": "user prompt secret"},
    ]

    redacted = redact_text(json.dumps(messages))

    assert "system prompt secret" not in redacted
    assert "user prompt secret" not in redacted
    assert '"role":"system"' in redacted
    assert '"role":"user"' in redacted
    assert redacted.count(REDACTED) == 2


def test_redact_text_scrubs_prefixed_json_exception_without_losing_adjacent_fields():
    payload = {
        "input": "private request input",
        "output": "private provider output",
        "completion": "private completion",
        "status": 503,
        "request_id": "req-visible-123",
    }
    error = RuntimeError(f"ProviderError payload={json.dumps(payload)} retryable=True")

    redacted = redact_text(error)

    for secret in (
        "private request input",
        "private provider output",
        "private completion",
    ):
        assert secret not in redacted
    assert "req-visible-123" in redacted
    assert '"status":503' in redacted
    assert "retryable=True" in redacted


def test_redact_text_scrubs_python_repr_payload_and_nested_message_content():
    payload = {
        "body": "private response body",
        "messages": [{"role": "user", "content": "nested message secret"}],
        "model": "model-visible",
        "usage": {"total_tokens": 42},
    }

    redacted = redact_text(f"provider failed: {payload!r}; attempt=2")

    assert "private response body" not in redacted
    assert "nested message secret" not in redacted
    assert "model-visible" in redacted
    assert "total_tokens" in redacted
    assert "42" in redacted
    assert "attempt=2" in redacted


def test_redact_text_bounds_large_serialized_payload_output():
    payload = {
        "content": "private" * (MAX_REDACTED_TEXT_LENGTH * 2),
        "request_id": "req-visible-bounded",
    }

    redacted = redact_text(f"failure payload={json.dumps(payload)}")

    assert "private" not in redacted
    assert "req-visible-bounded" in redacted
    assert len(redacted) <= MAX_REDACTED_TEXT_LENGTH


def test_formatter_redacts_structured_args_without_mutating_record():
    formatter = RedactingFormatter("%(message)s")
    record = logging.LogRecord(
        "test",
        logging.ERROR,
        __file__,
        1,
        "request failed: %s",
        ({"Authorization": "Bearer structured-secret", "status": 503},),
        None,
    )

    rendered = formatter.format(record)

    assert "structured-secret" not in rendered
    assert REDACTED in rendered
    assert record.args["Authorization"] == "Bearer structured-secret"


def test_formatter_redacts_provider_specific_structured_key():
    formatter = RedactingFormatter("%(message)s")
    record = logging.LogRecord(
        "test",
        logging.ERROR,
        __file__,
        1,
        "request failed: %s",
        ({"OPENAI_API_KEY": "structured-provider-secret"},),
        None,
    )

    rendered = formatter.format(record)

    assert "structured-provider-secret" not in rendered
    assert REDACTED in rendered


def test_formatter_redacts_exception_text_and_traceback():
    formatter = RedactingFormatter("%(message)s")
    try:
        raise RuntimeError("api_key=traceback-secret at /Users/alice/.zhiji/.env")
    except RuntimeError:
        record = logging.LogRecord(
            "test", logging.ERROR, __file__, 1, "provider failed", (), os.sys.exc_info()
        )

    rendered = formatter.format(record)

    assert "traceback-secret" not in rendered
    assert "/Users/alice/.zhiji/.env" not in rendered
    assert REDACTED in rendered


def test_console_and_file_output_never_contain_plaintext(tmp_path):
    stream = io.StringIO()
    console = logging.StreamHandler(stream)
    console.setFormatter(RedactingFormatter("%(message)s"))
    log_path = tmp_path / "ki.log"
    file_handler = SecureTimedRotatingFileHandler(log_path, when="midnight", backupCount=30)
    file_handler.setFormatter(RedactingFormatter("%(message)s"))
    logger = logging.Logger("redaction-output", level=logging.DEBUG)
    logger.addHandler(console)
    logger.addHandler(file_handler)

    try:
        logger.error("Authorization: Bearer %s", "plaintext-handler-secret")
    finally:
        file_handler.close()

    assert "plaintext-handler-secret" not in stream.getvalue()
    assert "plaintext-handler-secret" not in log_path.read_text(encoding="utf-8")


def test_secure_log_handler_uses_0600_for_initial_and_rotated_files(tmp_path):
    log_path = tmp_path / "ki.log"
    handler = SecureTimedRotatingFileHandler(log_path, when="midnight", backupCount=30)
    handler.setFormatter(RedactingFormatter("%(message)s"))
    record = logging.LogRecord("test", logging.INFO, __file__, 1, "before", (), None)

    handler.emit(record)
    handler.doRollover()
    handler.emit(logging.LogRecord("test", logging.INFO, __file__, 1, "after", (), None))
    handler.close()

    files = list(tmp_path.glob("ki.log*"))
    assert len(files) == 2
    assert all(stat.S_IMODE(path.stat().st_mode) == 0o600 for path in files)


def test_secure_log_handler_hardens_existing_regular_log_files(tmp_path):
    current = tmp_path / "ki.log"
    rotated = tmp_path / "ki.log.2026-07-20"
    current.write_text("current", encoding="utf-8")
    rotated.write_text("rotated", encoding="utf-8")
    current.chmod(0o644)
    rotated.chmod(0o666)

    handler = SecureTimedRotatingFileHandler(current, when="midnight", backupCount=30)
    handler.close()

    assert stat.S_IMODE(current.stat().st_mode) == 0o600
    assert stat.S_IMODE(rotated.stat().st_mode) == 0o600


def test_secure_log_handler_rejects_symlink_target(tmp_path):
    target = tmp_path / "outside.log"
    target.write_text("do not touch", encoding="utf-8")
    log_path = tmp_path / "ki.log"
    log_path.symlink_to(target)

    with pytest.raises(OSError, match="symlink"):
        SecureTimedRotatingFileHandler(log_path, when="midnight", backupCount=30)

    assert target.read_text(encoding="utf-8") == "do not touch"


def test_log_api_reredacts_historical_messages(tmp_path, monkeypatch):
    from zhiji_backend.main import app
    from zhiji_backend.routes import log_routes

    log_path = tmp_path / "ki.log"
    log_path.write_text(
        "2026-07-21 10:00:00 [ERROR  ] worker:42 | api_key=historical-secret\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(log_routes, "LOG_FILE", log_path)

    response = TestClient(app).get("/api/logs?limit=10")

    assert response.status_code == 200
    assert response.json()["entries"][0]["message"] == f"api_key={REDACTED}"
    assert "historical-secret" not in response.text


def test_log_api_reredacts_historical_serialized_payloads(tmp_path, monkeypatch):
    from zhiji_backend.main import app
    from zhiji_backend.routes import log_routes

    json_payload = json.dumps(
        {
            "messages": [{"role": "user", "content": "historical json secret"}],
            "request_id": "req-historical-json",
        }
    )
    repr_payload = repr(
        {
            "output": "historical repr secret",
            "status": 502,
            "model": "model-historical-visible",
        }
    )
    log_path = tmp_path / "ki.log"
    log_path.write_text(
        "2026-07-21 10:00:00 [ERROR  ] worker:42 | provider failed "
        f"payload={json_payload}\n"
        "2026-07-21 10:00:01 [ERROR  ] worker:43 | provider failed "
        f"payload={repr_payload}\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(log_routes, "LOG_FILE", log_path)

    response = TestClient(app).get("/api/logs?limit=10")

    assert response.status_code == 200
    assert "historical json secret" not in response.text
    assert "historical repr secret" not in response.text
    assert "req-historical-json" in response.text
    assert "model-historical-visible" in response.text


@pytest.mark.parametrize(
    ("error", "code", "message"),
    [
        (TimeoutError("provider timed out"), "timeout", "任务处理超时，请稍后重试。"),
        ("cancelled during server shutdown", "cancelled", "任务已取消。"),
        (asyncio.CancelledError(), "cancelled", "任务已取消。"),
        ("unsupported file format .exe", "unsupported_input", "不支持的输入格式。"),
        ("Unknown ingest type: binary", "unsupported_input", "不支持的输入格式。"),
        ("provider unavailable: 503", "provider_unavailable", "服务暂时不可用，请稍后重试。"),
        (RuntimeError("unexpected"), "task_failed", "任务处理失败，请稍后重试。"),
    ],
)
def test_task_error_sanitizer_returns_stable_categories(error, code, message):
    assert classify_task_error(error) == code
    assert sanitize_task_error(error) == message


def test_task_error_sanitizer_strips_diagnostics_and_is_bounded():
    raw = (
        "stderr SQL SELECT * FROM secrets prompt=private api_key=key-secret "
        "https://user:pass@example.test/path?token=query-secret "
        "/Users/alice/private/file.txt " + "x" * 500
    )

    sanitized = sanitize_task_error(raw)

    assert sanitized == "任务处理失败，请稍后重试。"
    assert len(sanitized) <= 200
    for secret in ("SELECT", "private", "key-secret", "query-secret", "/Users/alice"):
        assert secret not in sanitized
