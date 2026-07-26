from __future__ import annotations

import asyncio
import errno
import gzip
import importlib
import io
import json
import logging
import os
import shutil
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


def test_secure_log_handler_delay_overdue_first_emit_creates_active_log(tmp_path):
    module = _log_handlers_module()
    log_path = tmp_path / "ki.log"
    handler = module.SecureTimedRotatingFileHandler(
        log_path, when="S", interval=1, backupCount=30, delay=True, encoding="utf-8"
    )
    handler.setFormatter(logging.Formatter("%(message)s"))
    handler.rolloverAt = 0

    try:
        handler.emit(
            logging.LogRecord(
                "stable.logger", logging.INFO, __file__, 1, "first", (), None
            )
        )
    finally:
        handler.close()

    assert log_path.read_text(encoding="utf-8") == "first\n"
    assert stat.S_IMODE(log_path.stat().st_mode) == 0o600


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

    def fail_raw_open(*args, **kwargs):
        raise RuntimeError("raw open failed")

    monkeypatch.setattr(module.os, "open", observe_os_open)
    monkeypatch.setattr(io, "FileIO", fail_raw_open)

    with pytest.raises(RuntimeError, match="raw open failed"):
        module.SecureTimedRotatingFileHandler(log_path, when="midnight")

    assert len(opened_fds) == 1
    with pytest.raises(OSError) as closed:
        os.fstat(opened_fds[0])
    assert closed.value.errno == errno.EBADF


def test_secure_log_handler_invalid_encoding_closes_fd_and_preserves_error(
    tmp_path, monkeypatch
):
    module = _log_handlers_module()
    log_path = tmp_path / "ki.log"
    opened_fds = []
    original_os_open = os.open

    def observe_os_open(*args, **kwargs):
        fd = original_os_open(*args, **kwargs)
        opened_fds.append(fd)
        return fd

    monkeypatch.setattr(module.os, "open", observe_os_open)
    handler = module.SecureTimedRotatingFileHandler(
        log_path, when="midnight", delay=True, encoding="invalid-encoding-name"
    )

    with pytest.raises(LookupError, match="unknown encoding"):
        handler._open()

    assert len(opened_fds) == 1
    with pytest.raises(OSError) as closed:
        os.fstat(opened_fds[0])
    assert closed.value.errno == errno.EBADF


def test_secure_log_handler_wrapper_failure_closes_owned_fd_once(
    tmp_path, monkeypatch
):
    module = _log_handlers_module()
    log_path = tmp_path / "ki.log"
    wrapper_error = RuntimeError("wrapper construction failed")
    raw_streams = []
    original_file_io = io.FileIO

    class TrackingFileIO:
        def __init__(self, fd, *args, **kwargs):
            self.delegate = original_file_io(fd, *args, **kwargs)
            self.close_calls = 0
            raw_streams.append(self)

        @property
        def closed(self):
            return self.delegate.closed

        def close(self):
            self.close_calls += 1
            self.delegate.close()

    def fail_wrapper(*args, **kwargs):
        raise wrapper_error

    monkeypatch.setattr(io, "FileIO", TrackingFileIO)
    monkeypatch.setattr(io, "TextIOWrapper", fail_wrapper)
    handler = module.SecureTimedRotatingFileHandler(log_path, when="midnight", delay=True)

    with pytest.raises(RuntimeError) as raised:
        handler._open()

    assert raised.value is wrapper_error
    assert len(raw_streams) == 1
    assert raw_streams[0].close_calls == 1
    assert raw_streams[0].closed


def test_secure_log_handler_wrapper_failure_preserves_error_when_close_fails(
    tmp_path, monkeypatch
):
    module = _log_handlers_module()
    log_path = tmp_path / "ki.log"
    wrapper_error = RuntimeError("wrapper construction failed")
    original_file_io = io.FileIO

    class CloseFailingFileIO:
        def __init__(self, fd, *args, **kwargs):
            self.delegate = original_file_io(fd, *args, **kwargs)

        def close(self):
            self.delegate.close()
            raise OSError("secondary close failed")

    def fail_wrapper(*args, **kwargs):
        raise wrapper_error

    monkeypatch.setattr(io, "FileIO", CloseFailingFileIO)
    monkeypatch.setattr(io, "TextIOWrapper", fail_wrapper)
    handler = module.SecureTimedRotatingFileHandler(log_path, when="midnight", delay=True)

    with pytest.raises(RuntimeError) as raised:
        handler._open()

    assert raised.value is wrapper_error


def test_secure_log_handler_wrapper_failure_does_not_close_reused_fd(
    tmp_path, monkeypatch
):
    module = _log_handlers_module()
    log_path = tmp_path / "ki.log"
    unrelated_path = tmp_path / "unrelated.log"
    opened_log_fds = []
    unrelated_fds = []
    original_os_open = os.open

    def observe_os_open(*args, **kwargs):
        fd = original_os_open(*args, **kwargs)
        opened_log_fds.append(fd)
        return fd

    def close_reuse_and_fail(raw, *args, **kwargs):
        raw.close()
        unrelated_fds.append(
            original_os_open(unrelated_path, os.O_WRONLY | os.O_CREAT, 0o600)
        )
        raise RuntimeError("wrapper failed after ownership transfer")

    monkeypatch.setattr(module.os, "open", observe_os_open)
    monkeypatch.setattr(io, "TextIOWrapper", close_reuse_and_fail)
    handler = module.SecureTimedRotatingFileHandler(log_path, when="midnight", delay=True)

    try:
        with pytest.raises(RuntimeError, match="after ownership transfer"):
            handler._open()

        assert unrelated_fds == opened_log_fds
        assert os.fstat(unrelated_fds[0]).st_mode
    finally:
        if unrelated_fds:
            os.close(unrelated_fds[0])


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


def test_secure_log_handler_default_rotation_tolerates_source_disappearing(
    tmp_path, monkeypatch
):
    module = _log_handlers_module()
    source = tmp_path / "ki.log"
    destination = tmp_path / "ki.log.rotated"
    source.write_text("source", encoding="utf-8")

    def remove_before_rename(handler, source_name, destination_name):
        source.unlink()
        logging.handlers.BaseRotatingHandler.rotate(
            handler, source_name, destination_name
        )

    monkeypatch.setattr(
        logging.handlers.TimedRotatingFileHandler,
        "rotate",
        remove_before_rename,
    )
    handler = module.SecureTimedRotatingFileHandler(source, when="midnight", delay=True)
    try:
        handler.rotate(str(source), str(destination))
    finally:
        handler.close()

    assert not source.exists()
    assert not destination.exists()


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


@pytest.mark.parametrize("compression", [False, True], ids=["copyfile", "gzip"])
def test_secure_log_handler_presecures_custom_rotator_destination(
    tmp_path, compression
):
    module = _log_handlers_module()
    source = tmp_path / "ki.log"
    destination = tmp_path / ("ki.log.rotated.gz" if compression else "ki.log.rotated")
    source.write_bytes(b"source")
    observed_modes = []
    staging_paths = []
    handler = module.SecureTimedRotatingFileHandler(source, when="midnight", delay=True)

    def rotate(source_name, destination_name):
        staging = Path(destination_name)
        staging_paths.append(staging)
        observed_modes.append(stat.S_IMODE(staging.stat().st_mode))
        assert staging.parent == destination.parent
        assert staging != destination
        assert staging.name.startswith(".")
        assert staging.name.endswith(destination.name)
        assert not destination.exists()
        if compression:
            with open(source_name, "rb") as source_stream:
                with gzip.open(destination_name, "wb") as destination_stream:
                    shutil.copyfileobj(source_stream, destination_stream)
        else:
            shutil.copyfile(source_name, destination_name)

    handler.rotator = rotate
    try:
        handler.rotate(str(source), str(destination))
    finally:
        handler.close()

    assert observed_modes == [0o600]
    assert not staging_paths[0].exists()
    assert stat.S_IMODE(destination.stat().st_mode) == 0o600
    if compression:
        with gzip.open(destination, "rb") as stream:
            assert stream.read() == b"source"
    else:
        assert destination.read_bytes() == b"source"


def test_secure_log_handler_rejects_custom_rotator_symlink_result(tmp_path):
    module = _log_handlers_module()
    source = tmp_path / "ki.log"
    destination = tmp_path / "ki.log.rotated"
    outside = tmp_path / "outside.log"
    source.write_text("source", encoding="utf-8")
    outside.write_text("outside", encoding="utf-8")
    outside.chmod(0o644)
    handler = module.SecureTimedRotatingFileHandler(source, when="midnight", delay=True)

    staging_paths = []

    def malicious_rotator(_source_name, destination_name):
        staging = Path(destination_name)
        staging_paths.append(staging)
        assert staging.is_file()
        staging.unlink()
        staging.symlink_to(outside)

    handler.rotator = malicious_rotator
    try:
        with pytest.raises(OSError, match="refusing symlink log target"):
            handler.rotate(str(source), str(destination))
    finally:
        handler.close()

    assert not destination.exists()
    assert staging_paths[0].is_symlink()
    assert outside.read_text(encoding="utf-8") == "outside"
    assert stat.S_IMODE(outside.stat().st_mode) == 0o644


def test_secure_log_handler_custom_rotation_replaces_final_symlink(tmp_path):
    module = _log_handlers_module()
    source = tmp_path / "ki.log"
    destination = tmp_path / "ki.log.rotated"
    outside = tmp_path / "outside.log"
    source.write_text("source", encoding="utf-8")
    outside.write_text("outside", encoding="utf-8")
    outside.chmod(0o644)
    destination.symlink_to(outside)
    handler = module.SecureTimedRotatingFileHandler(source, when="midnight", delay=True)
    handler.rotator = shutil.copyfile

    try:
        handler.rotate(str(source), str(destination))
    finally:
        handler.close()

    assert not destination.is_symlink()
    assert destination.read_text(encoding="utf-8") == "source"
    assert stat.S_IMODE(destination.stat().st_mode) == 0o600
    assert outside.read_text(encoding="utf-8") == "outside"
    assert stat.S_IMODE(outside.stat().st_mode) == 0o644


def test_secure_log_handler_skips_custom_rotator_when_source_is_absent(tmp_path):
    module = _log_handlers_module()
    source = tmp_path / "ki.log"
    destination = tmp_path / "ki.log.rotated"
    calls = []
    handler = module.SecureTimedRotatingFileHandler(source, when="midnight", delay=True)
    handler.rotator = lambda *args: calls.append(args)

    try:
        handler.rotate(str(source), str(destination))
    finally:
        handler.close()

    assert calls == []
    assert not destination.exists()


def test_secure_log_handler_failed_rotator_leaves_only_non_candidate_staging(
    tmp_path,
):
    module = _log_handlers_module()
    source = tmp_path / "ki.log"
    destination = tmp_path / "ki.log.2026-07-20"
    source.write_text("source", encoding="utf-8")
    rotator_error = RuntimeError("rotator failed")
    staging_paths = []
    handler = module.SecureTimedRotatingFileHandler(source, when="midnight", delay=True)

    def fail_before_touching(_source_name, destination_name):
        staging = Path(destination_name)
        staging_paths.append(staging)
        assert staging.is_file()
        assert stat.S_IMODE(staging.stat().st_mode) == 0o600
        assert not destination.exists()
        raise rotator_error

    handler.rotator = fail_before_touching

    try:
        with pytest.raises(RuntimeError) as raised:
            handler.rotate(str(source), str(destination))
    finally:
        handler.close()

    assert raised.value is rotator_error
    assert source.read_text(encoding="utf-8") == "source"
    assert not destination.exists()
    assert len(staging_paths) == 1
    assert staging_paths[0].is_file()
    assert stat.S_IMODE(staging_paths[0].stat().st_mode) == 0o600
    candidates = list(
        module._rotation_candidates(source, handler.extMatch, handler.namer)
    )
    assert staging_paths[0] not in candidates


def test_secure_log_handler_never_deletes_hostile_staging_replacement(tmp_path):
    module = _log_handlers_module()
    source = tmp_path / "ki.log"
    destination = tmp_path / "ki.log.rotated"
    source.write_text("source", encoding="utf-8")
    rotator_error = RuntimeError("rotator failed after replacement")
    replacement_identity = []
    staging_paths = []
    handler = module.SecureTimedRotatingFileHandler(source, when="midnight", delay=True)

    def replace_then_fail(_source_name, destination_name):
        staging = Path(destination_name)
        staging_paths.append(staging)
        staging.unlink()
        staging.write_text("replacement", encoding="utf-8")
        replacement = staging.lstat()
        replacement_identity.append((replacement.st_dev, replacement.st_ino))
        raise rotator_error

    handler.rotator = replace_then_fail
    try:
        with pytest.raises(RuntimeError) as raised:
            handler.rotate(str(source), str(destination))
    finally:
        handler.close()

    replacement = staging_paths[0].lstat()
    assert raised.value is rotator_error
    assert (replacement.st_dev, replacement.st_ino) == replacement_identity[0]
    assert staging_paths[0].read_text(encoding="utf-8") == "replacement"
    assert not destination.exists()


def test_secure_log_handler_rollover_retries_after_rotator_failure(tmp_path):
    module = _log_handlers_module()
    source = tmp_path / "ki.log"
    handler = module.SecureTimedRotatingFileHandler(
        source, when="S", interval=1, backupCount=30, encoding="utf-8"
    )
    handler.setFormatter(logging.Formatter("%(message)s"))
    handler.emit(
        logging.LogRecord("stable.logger", logging.INFO, __file__, 1, "before", (), None)
    )
    handler.rolloverAt = 0
    rotator_error = RuntimeError("first rotation failed")
    failed_stages = []
    successful_stages = []

    def fail_first_rotation(_source_name, destination_name):
        failed_stages.append(Path(destination_name))
        raise rotator_error

    handler.rotator = fail_first_rotation

    try:
        with pytest.raises(RuntimeError) as raised:
            handler.doRollover()

        assert raised.value is rotator_error
        assert not any(
            path.name.startswith("ki.log.") for path in tmp_path.iterdir()
        )
        assert source.read_text(encoding="utf-8") == "before\n"
        assert handler.rolloverAt == 0
        assert len(failed_stages) == 1
        assert failed_stages[0].is_file()
        assert failed_stages[0].stat().st_size == 0
        assert stat.S_IMODE(failed_stages[0].stat().st_mode) == 0o600
        assert failed_stages[0] not in list(
            module._rotation_candidates(source, handler.extMatch, handler.namer)
        )

        def successful_rotation(source_name, destination_name):
            successful_stages.append(Path(destination_name))
            os.replace(source_name, destination_name)

        handler.rotator = successful_rotation
        handler.doRollover()
        assert handler.rolloverAt > 0
    finally:
        handler.close()

    rotated = list(module._rotation_candidates(source, handler.extMatch, handler.namer))
    assert len(rotated) == 1
    assert rotated[0].read_text(encoding="utf-8") == "before\n"
    assert stat.S_IMODE(rotated[0].stat().st_mode) == 0o600
    assert source.is_file()
    assert source.stat().st_size == 0
    assert stat.S_IMODE(source.stat().st_mode) == 0o600
    assert failed_stages[0].is_file()
    assert len(successful_stages) == 1
    assert successful_stages[0] != failed_stages[0]


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


def test_secure_log_handler_does_not_harden_unrelated_prefix_matches(tmp_path):
    current = tmp_path / "ki.log"
    rotated = tmp_path / "ki.log.2026-07-20"
    unrelated = [tmp_path / "ki.logger-config", tmp_path / "ki.log-export"]
    for path in (current, rotated, *unrelated):
        path.write_text(path.name, encoding="utf-8")
        path.chmod(0o666)

    handler = SecureTimedRotatingFileHandler(current, when="midnight", backupCount=30)
    handler.close()

    assert stat.S_IMODE(current.stat().st_mode) == 0o600
    assert stat.S_IMODE(rotated.stat().st_mode) == 0o600
    assert [stat.S_IMODE(path.stat().st_mode) for path in unrelated] == [0o666, 0o666]


def test_secure_log_handler_hardens_supported_custom_namer_candidates(tmp_path):
    module = _log_handlers_module()
    current = tmp_path / "ki.log"
    current.write_text("current", encoding="utf-8")
    handler = module.SecureTimedRotatingFileHandler(
        current, when="midnight", backupCount=30
    )
    handler.namer = lambda default_name: f"{default_name}.gz"
    rotated = tmp_path / "ki.log.2026-07-20.gz"
    unrelated = tmp_path / "ki.log.archive-2026-07-20.gz"
    for path in (rotated, unrelated):
        path.write_text(path.name, encoding="utf-8")
        path.chmod(0o666)

    try:
        module._harden_existing_logs(
            current,
            ext_match=handler.extMatch,
            namer=handler.namer,
        )
    finally:
        handler.close()

    assert stat.S_IMODE(rotated.stat().st_mode) == 0o600
    assert stat.S_IMODE(unrelated.stat().st_mode) == 0o666


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

    def observe_harden(path, *args, **kwargs):
        events.append("harden")
        return original_harden(path, *args, **kwargs)

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
