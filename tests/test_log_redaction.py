from __future__ import annotations

import asyncio
import builtins
import errno
import importlib
import io
import json
import logging
import os
import stat
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from zhiji_backend.security import redaction as redaction_module
from zhiji_backend.security.redaction import (
    MAX_REDACTED_TEXT_LENGTH,
    REDACTED,
    RedactingFormatter,
    SecureTimedRotatingFileHandler,
    classify_task_error,
    redact_text,
    sanitize_task_error,
)


def _log_handlers_module():
    try:
        return importlib.import_module("zhiji_backend.security.log_handlers")
    except ModuleNotFoundError as error:
        if error.name != "zhiji_backend.security.log_handlers":
            raise
        pytest.fail("zhiji_backend.security.log_handlers has not been extracted")


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


def test_redact_text_exact_compound_output_is_stable():
    text = (
        "POST https://user:pw@example.test/v1?token=query-secret&limit=20 "
        'Authorization: Bearer bearer-secret prompt={"role":"user","content":"private"}'
    )

    assert redact_text(text) == (
        "POST https://[REDACTED]@example.test/v1?token=[REDACTED]&limit=20 "
        "Authorization: [REDACTED] prompt=[REDACTED]"
    )


def test_redact_text_scrubs_json_dumped_message_content_and_preserves_roles():
    messages = [
        {"role": "system", "content": "system prompt secret"},
        {"role": "user", "content": "user prompt secret"},
    ]

    redacted = redact_text(json.dumps(messages))

    assert "system prompt secret" not in redacted
    assert "user prompt secret" not in redacted
    assert '"role": "system"' in redacted
    assert '"role": "user"' in redacted
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
    assert '"status": 503' in redacted
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
    assert "req-visible-bounded" not in redacted
    assert "[TRUNCATED]" in redacted
    assert len(redacted) <= MAX_REDACTED_TEXT_LENGTH


@pytest.mark.parametrize(
    ("key", "value", "secret"),
    [
        (
            "messages",
            "[{'role': 'user', 'content': 'late messages secret'}]",
            "late messages secret",
        ),
        ("content", repr("late content secret"), "late content secret"),
        ("body", repr("late body secret"), "late body secret"),
        ("input", repr("late input secret"), "late input secret"),
        ("output", repr("late output secret"), "late output secret"),
        ("completion", repr("late completion secret"), "late completion secret"),
    ],
)
def test_redact_text_has_no_delimiter_attempt_bypass(key, value, secret):
    malformed_prefix = "[broken " * 80
    text = f"{malformed_prefix}{key}={value}; status=503"

    redacted = redact_text(text)

    assert secret not in redacted
    assert REDACTED in redacted
    assert "status=503" in redacted


def test_redact_text_bounds_input_before_structural_scanning(monkeypatch):
    observed_lengths = []
    original = redaction_module._balanced_structure_end

    def observe_length(text, start):
        observed_lengths.append(len(text))
        return original(text, start)

    monkeypatch.setattr(redaction_module, "_balanced_structure_end", observe_length)
    text = "content=[" + ("malformed" * 200_000)

    redacted = redact_text(text)

    assert observed_lengths == [redaction_module.MAX_REDACTION_INPUT_LENGTH]
    assert "malformed" not in redacted
    assert "[TRUNCATED]" in redacted
    assert len(redacted) <= MAX_REDACTED_TEXT_LENGTH


def test_unquoted_sensitive_value_scans_trailing_whitespace_once(monkeypatch):
    class CountingPattern:
        def __init__(self, delegate):
            self.delegate = delegate
            self.match_calls = 0

        def search(self, *args, **kwargs):
            return self.delegate.search(*args, **kwargs)

        def match(self, *args, **kwargs):
            self.match_calls += 1
            return self.delegate.match(*args, **kwargs)

    pattern = CountingPattern(redaction_module._KEY_ASSIGNMENT_RE)
    monkeypatch.setattr(redaction_module, "_KEY_ASSIGNMENT_RE", pattern)
    text = "content=plain-secret" + (" " * 4096)

    redacted = redact_text(text)

    assert "plain-secret" not in redacted
    assert redacted == f"content={REDACTED}"
    assert pattern.match_calls <= 1


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


def test_secure_log_handler_initial_open_preserves_flags_mode_and_text_options(
    tmp_path, monkeypatch
):
    module = _log_handlers_module()
    log_path = tmp_path / "ki.log"
    observed = []
    original_open = os.open

    def observe_open(path, flags, mode=0o777, *args, **kwargs):
        observed.append((Path(path), flags, mode))
        return original_open(path, flags, mode, *args, **kwargs)

    monkeypatch.setattr(module.os, "open", observe_open)

    handler = module.SecureTimedRotatingFileHandler(
        log_path,
        when="midnight",
        encoding="utf-8",
        errors="backslashreplace",
    )
    try:
        assert handler.mode == "a"
        assert handler.encoding == "utf-8"
        assert handler.errors == "backslashreplace"
        assert handler.stream is not None
    finally:
        handler.close()

    assert observed == [
        (
            log_path,
            os.O_WRONLY | os.O_APPEND | os.O_CREAT | os.O_NOFOLLOW,
            0o600,
        )
    ]
    assert stat.S_IMODE(log_path.stat().st_mode) == 0o600


def test_secure_log_handler_closes_fd_when_text_open_fails(tmp_path, monkeypatch):
    module = _log_handlers_module()
    log_path = tmp_path / "ki.log"
    opened_fds = []
    original_os_open = os.open

    def observe_os_open(*args, **kwargs):
        fd = original_os_open(*args, **kwargs)
        opened_fds.append(fd)
        return fd

    def fail_text_open(*args, **kwargs):
        raise RuntimeError("text open failed")

    monkeypatch.setattr(module.os, "open", observe_os_open)
    monkeypatch.setattr(builtins, "open", fail_text_open)

    with pytest.raises(RuntimeError, match="text open failed"):
        module.SecureTimedRotatingFileHandler(log_path, when="midnight")

    assert len(opened_fds) == 1
    with pytest.raises(OSError) as closed:
        os.fstat(opened_fds[0])
    assert closed.value.errno == errno.EBADF


@pytest.mark.parametrize(
    ("target_kind", "message"),
    [
        ("symlink", "refusing symlink log target: ki.log"),
        ("directory", "refusing non-regular log target: ki.log"),
    ],
)
def test_secure_log_handler_rejects_unsafe_target_with_exact_message(
    tmp_path, target_kind, message
):
    module = _log_handlers_module()
    log_path = tmp_path / "ki.log"
    if target_kind == "symlink":
        target = tmp_path / "outside.log"
        target.write_text("do not touch", encoding="utf-8")
        log_path.symlink_to(target)
    else:
        log_path.mkdir()

    with pytest.raises(OSError, match=f"^{message}$"):
        module.SecureTimedRotatingFileHandler(log_path, when="midnight")


def test_secure_log_handler_rotation_replaces_racing_symlink_without_following_target(
    tmp_path, monkeypatch
):
    module = _log_handlers_module()
    source = tmp_path / "ki.log"
    destination = tmp_path / "ki.log.rotated"
    outside = tmp_path / "outside.log"
    source.write_text("source", encoding="utf-8")
    outside.write_text("outside", encoding="utf-8")

    def race_before_rename(handler, source_name, destination_name):
        destination.symlink_to(outside)
        logging.handlers.BaseRotatingHandler.rotate(
            handler, source_name, destination_name
        )

    monkeypatch.setattr(
        logging.handlers.TimedRotatingFileHandler,
        "rotate",
        race_before_rename,
    )
    handler = module.SecureTimedRotatingFileHandler(source, when="midnight", delay=True)
    try:
        handler.rotate(str(source), str(destination))
    finally:
        handler.close()

    assert destination.read_text(encoding="utf-8") == "source"
    assert stat.S_IMODE(destination.stat().st_mode) == 0o600
    assert outside.read_text(encoding="utf-8") == "outside"


@pytest.mark.parametrize("custom_rotator", [False, True], ids=["rename", "callable"])
def test_secure_log_handler_rotation_modes_harden_destination(tmp_path, custom_rotator):
    module = _log_handlers_module()
    source = tmp_path / "ki.log"
    destination = tmp_path / "ki.log.rotated"
    source.write_text("source", encoding="utf-8")
    source.chmod(0o644)
    handler = module.SecureTimedRotatingFileHandler(source, when="midnight", delay=True)
    if custom_rotator:
        handler.rotator = os.replace

    try:
        handler.rotate(str(source), str(destination))
    finally:
        handler.close()

    assert destination.read_text(encoding="utf-8") == "source"
    assert stat.S_IMODE(destination.stat().st_mode) == 0o600


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


def test_secure_log_handler_tolerates_old_rotated_chmod_failure(
    tmp_path, monkeypatch, caplog
):
    current = tmp_path / "ki.log"
    rotated = tmp_path / "ki.log.2026-07-20"
    current.write_text("current", encoding="utf-8")
    rotated.write_text("rotated", encoding="utf-8")
    original_chmod = Path.chmod

    def fail_rotated(self, *args, **kwargs):
        if self == rotated:
            raise PermissionError("read-only rotated log")
        return original_chmod(self, *args, **kwargs)

    monkeypatch.setattr(Path, "chmod", fail_rotated)

    with caplog.at_level("WARNING"):
        handler = SecureTimedRotatingFileHandler(current, when="midnight", backupCount=30)
        handler.close()

    assert stat.S_IMODE(current.stat().st_mode) == 0o600
    assert "rotated log" in caplog.text
    assert "PermissionError" in caplog.text
    assert {
        record.name for record in caplog.records if "rotated log" in record.message
    } == {"zhiji_backend.security.redaction"}


def test_secure_log_handler_keeps_active_log_chmod_failure_fatal(tmp_path, monkeypatch):
    current = tmp_path / "ki.log"
    current.write_text("current", encoding="utf-8")
    original_chmod = Path.chmod

    def fail_current(self, *args, **kwargs):
        if self == current:
            raise PermissionError("active log chmod failed")
        return original_chmod(self, *args, **kwargs)

    monkeypatch.setattr(Path, "chmod", fail_current)

    with pytest.raises(PermissionError, match="active log chmod failed"):
        SecureTimedRotatingFileHandler(current, when="midnight", backupCount=30)


def test_secure_log_handler_rejects_symlink_target(tmp_path):
    target = tmp_path / "outside.log"
    target.write_text("do not touch", encoding="utf-8")
    log_path = tmp_path / "ki.log"
    log_path.symlink_to(target)

    with pytest.raises(OSError, match="symlink"):
        SecureTimedRotatingFileHandler(log_path, when="midnight", backupCount=30)

    assert target.read_text(encoding="utf-8") == "do not touch"


def test_secure_log_handler_rollover_orders_rotate_open_then_hardening(
    tmp_path, monkeypatch
):
    module = _log_handlers_module()
    log_path = tmp_path / "ki.log"
    handler = module.SecureTimedRotatingFileHandler(
        log_path, when="midnight", backupCount=30
    )
    events = []
    original_rotate = handler.rotate
    original_open = handler._open
    original_harden = module._harden_existing_logs

    def observe_rotate(source, destination):
        events.append("rotate")
        return original_rotate(source, destination)

    def observe_open():
        events.append("open")
        return original_open()

    def observe_harden(path):
        events.append("harden")
        return original_harden(path)

    monkeypatch.setattr(handler, "rotate", observe_rotate)
    monkeypatch.setattr(handler, "_open", observe_open)
    monkeypatch.setattr(module, "_harden_existing_logs", observe_harden)

    try:
        handler.doRollover()
    finally:
        handler.close()

    assert events == ["rotate", "open", "harden"]


def test_secure_log_handler_supports_repeated_rollover(tmp_path):
    module = _log_handlers_module()
    log_path = tmp_path / "ki.log"
    handler = module.SecureTimedRotatingFileHandler(
        log_path, when="S", interval=1, backupCount=30, encoding="utf-8"
    )
    handler.setFormatter(logging.Formatter("%(message)s"))

    try:
        for message in ("first", "second", "third"):
            handler.emit(
                logging.LogRecord(
                    "stable.logger", logging.INFO, __file__, 1, message, (), None
                )
            )
            handler.doRollover()
    finally:
        handler.close()

    files = list(tmp_path.glob("ki.log*"))
    assert files
    assert all(stat.S_ISREG(path.lstat().st_mode) for path in files)
    assert all(stat.S_IMODE(path.stat().st_mode) == 0o600 for path in files)


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


def test_log_reader_rejects_symlink_swap_before_open(tmp_path, monkeypatch):
    from zhiji_backend.routes import log_routes

    log_path = tmp_path / "ki.log"
    secret_path = tmp_path / "secret.log"
    log_path.write_text(
        "2026-07-21 10:00:00 [INFO   ] worker:1 | safe message\n",
        encoding="utf-8",
    )
    secret_path.write_text(
        "2026-07-21 10:00:01 [ERROR  ] worker:2 | secret message\n",
        encoding="utf-8",
    )
    original_open = os.open
    observed_flags = []

    def swap_before_open(path, flags, *args, **kwargs):
        observed_flags.append(flags)
        log_path.unlink()
        log_path.symlink_to(secret_path)
        return original_open(path, flags, *args, **kwargs)

    monkeypatch.setattr(log_routes.os, "open", swap_before_open)

    entries = log_routes._parse_log_lines(log_path, "INFO", 10)

    assert entries == []
    assert observed_flags
    assert observed_flags[0] & os.O_NOFOLLOW


def test_log_reader_reads_pinned_fd_when_path_swapped_after_open(tmp_path, monkeypatch):
    from zhiji_backend.routes import log_routes

    log_path = tmp_path / "ki.log"
    secret_path = tmp_path / "secret.log"
    log_path.write_text(
        "2026-07-21 10:00:00 [INFO   ] worker:1 | pinned safe message\n",
        encoding="utf-8",
    )
    secret_path.write_text(
        "2026-07-21 10:00:01 [ERROR  ] worker:2 | swapped secret message\n",
        encoding="utf-8",
    )
    original_open = os.open

    def swap_after_open(path, flags, *args, **kwargs):
        fd = original_open(path, flags, *args, **kwargs)
        log_path.unlink()
        log_path.symlink_to(secret_path)
        return fd

    monkeypatch.setattr(log_routes.os, "open", swap_after_open)

    entries = log_routes._parse_log_lines(log_path, "INFO", 10)

    assert [entry["message"] for entry in entries] == ["pinned safe message"]
    assert "swapped secret message" not in repr(entries)


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
