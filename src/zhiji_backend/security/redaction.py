from __future__ import annotations

import copy
import logging
import logging.handlers
import os
import re
import stat
from pathlib import Path
from typing import Any
from urllib.parse import unquote_plus, urlsplit, urlunsplit


REDACTED = "[REDACTED]"
MAX_REDACTION_INPUT_LENGTH = 65_536
MAX_REDACTED_TEXT_LENGTH = 16_384
MAX_TASK_ERROR_LENGTH = 200
_TRUNCATED = "...[TRUNCATED]"

logger = logging.getLogger(__name__)

_SENSITIVE_KEYS = {
    "authorization",
    "cookie",
    "set-cookie",
    "x-api-key",
    "api-key",
    "api_key",
    "apikey",
    "access-token",
    "access_token",
    "refresh-token",
    "refresh_token",
    "token",
    "signature",
    "sig",
    "secret",
    "password",
    "passwd",
    "prompt",
    "response",
    "response_body",
    "request_body",
    "body",
    "content",
    "messages",
    "input",
    "output",
    "completion",
}
_SENSITIVE_QUERY_KEYS = {
    "api_key",
    "apikey",
    "key",
    "token",
    "access_token",
    "refresh_token",
    "signature",
    "sig",
    "password",
    "passwd",
    "secret",
}

_URL_RE = re.compile(r"https?://[^\s<>\"']+", re.IGNORECASE)
_AUTH_RE = re.compile(
    r"(?i)([\"']?\bAuthorization\b[\"']?\s*[:=]\s*[\"']?Bearer\s+)"
    r"([^\"'\s,;}]+)"
)
_HEADER_RE = re.compile(
    r"(?i)([\"']?\b(?:X-API-Key|Cookie|Set-Cookie)\b[\"']?\s*[:=]\s*)"
    r"(?:\"[^\"\r\n]*\"|'[^'\r\n]*'|[^\r\n]+)"
)
_LABELED_SECRET_RE = re.compile(
    r"(?i)([\"']?\b(?:[A-Z0-9_]*(?:API[_-]?KEY)|api[_-]?key|access[_-]?token|"
    r"refresh[_-]?token|token|signature|sig|secret|password|passwd)\b[\"']?"
    r"\s*[:=]\s*)(?!\[REDACTED\])"
    r"(?:\"[^\"\r\n]*\"|'[^'\r\n]*'|[^\s,;&}\]]+)"
)
_BODY_RE = re.compile(
    r"(?i)([\"']?\b(?:prompt|response(?:_body)?|request_body)\b[\"']?"
    r"\s*[:=]\s*)(?:\"[^\"\r\n]*\"|'[^'\r\n]*'|[^\r\n]+)"
)
_RAW_KEY_RE = re.compile(
    r"\b(?:sk-[A-Za-z0-9_-]{8,}|AKIA[A-Z0-9]{16}|AIza[A-Za-z0-9_-]{20,})\b"
)
_SECRET_PATH_RE = re.compile(
    r"(?i)(?:~|/(?:Users|home|private|var|opt)/)[^\s\"']*"
    r"(?:\.env(?:\.[^\s\"']+)?|credentials?(?:\.[^\s\"']+)?|"
    r"secrets?(?:\.[^\s\"']+)?|id_(?:rsa|ed25519)|\.pem|\.key)"
)
_BODY_CONTEXT_RE = re.compile(r"(?i)\b(?:prompt|response|request[_ -]?body)\b")
_KEY_ASSIGNMENT_RE = re.compile(
    r"(?:(?P<quote>[\"'])(?P<quoted_key>[A-Za-z_][A-Za-z0-9_.-]{0,127})(?P=quote)"
    r"|(?<![A-Za-z0-9_.-])(?P<bare_key>[A-Za-z_][A-Za-z0-9_.-]{0,127}))"
    r"\s*[:=]\s*"
)

_TASK_MESSAGES = {
    "timeout": "任务处理超时，请稍后重试。",
    "cancelled": "任务已取消。",
    "unsupported_input": "不支持的输入格式。",
    "provider_unavailable": "服务暂时不可用，请稍后重试。",
    "task_failed": "任务处理失败，请稍后重试。",
}


def _is_sensitive_key(key: Any) -> bool:
    normalized = unquote_plus(str(key)).strip().lower().replace("-", "_")
    exact_keys = {item.replace("-", "_") for item in _SENSITIVE_KEYS}
    return normalized in exact_keys or normalized.endswith(
        ("_api_key", "_token", "_signature", "_secret", "_password")
    )


def _redact_url(match: re.Match[str]) -> str:
    raw = match.group(0)
    trailing = ""
    while raw and raw[-1] in ".,);]":
        trailing = raw[-1] + trailing
        raw = raw[:-1]
    try:
        parts = urlsplit(raw)
    except ValueError:
        return REDACTED + trailing

    netloc = parts.netloc
    if "@" in netloc:
        _, host = netloc.rsplit("@", 1)
        netloc = f"{REDACTED}@{host}"

    query_parts: list[str] = []
    for item in parts.query.split("&") if parts.query else []:
        key, _, _ = item.partition("=")
        if _is_sensitive_key(key) or unquote_plus(key).lower() in _SENSITIVE_QUERY_KEYS:
            query_parts.append(f"{key}={REDACTED}")
        else:
            query_parts.append(item)
    redacted_url = urlunsplit(
        (parts.scheme, netloc, parts.path, "&".join(query_parts), parts.fragment)
    )
    return redacted_url + trailing


def _balanced_structure_end(text: str, start: int) -> int | None:
    pairs = {"{": "}", "[": "]", "(": ")"}
    stack = [pairs[text[start]]]
    quote: str | None = None
    escaped = False
    for index in range(start + 1, len(text)):
        char = text[index]
        if quote is not None:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == quote:
                quote = None
            continue
        if char in ("\"", "'"):
            quote = char
        elif char in pairs:
            stack.append(pairs[char])
        elif stack and char == stack[-1]:
            stack.pop()
            if not stack:
                return index + 1
    return None


def _sensitive_value_end(text: str, start: int) -> int:
    if start >= len(text):
        return start
    if text[start] in ("\"", "'"):
        quote = text[start]
        escaped = False
        for index in range(start + 1, len(text)):
            char = text[index]
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == quote:
                return index + 1
        return len(text)
    if text[start] in "[{(":
        return _balanced_structure_end(text, start) or len(text)

    index = start
    while index < len(text):
        char = text[index]
        if char in ",;&}]\r\n":
            return index
        if char.isspace():
            next_index = index
            while next_index < len(text) and text[next_index].isspace():
                next_index += 1
            if _KEY_ASSIGNMENT_RE.match(text, next_index):
                return index
        index += 1
    return len(text)


def _redact_sensitive_assignments(text: str) -> str:
    parts: list[str] = []
    cursor = 0
    search_from = 0

    while True:
        match = _KEY_ASSIGNMENT_RE.search(text, search_from)
        if match is None:
            break
        key = match.group("quoted_key") or match.group("bare_key")
        if not _is_sensitive_key(key):
            search_from = match.end()
            continue
        end = _sensitive_value_end(text, match.end())
        parts.append(text[cursor:match.end()])
        parts.append(REDACTED)
        cursor = end
        search_from = end

    if not parts:
        return text
    parts.append(text[cursor:])
    return "".join(parts)


def _bound_redacted_text(text: str) -> str:
    if len(text) <= MAX_REDACTED_TEXT_LENGTH:
        return text
    keep = MAX_REDACTED_TEXT_LENGTH - len(_TRUNCATED)
    return text[:keep] + _TRUNCATED


def redact_text(value: Any) -> str:
    raw_text = str(value)
    input_truncated = len(raw_text) > MAX_REDACTION_INPUT_LENGTH
    text = raw_text[:MAX_REDACTION_INPUT_LENGTH]
    text = _redact_sensitive_assignments(text)
    text = _URL_RE.sub(_redact_url, text)
    text = _AUTH_RE.sub(lambda match: match.group(1) + REDACTED, text)
    text = _HEADER_RE.sub(lambda match: match.group(1) + REDACTED, text)
    text = _BODY_RE.sub(lambda match: match.group(1) + REDACTED, text)
    text = _LABELED_SECRET_RE.sub(lambda match: match.group(1) + REDACTED, text)
    text = _RAW_KEY_RE.sub(REDACTED, text)
    text = _SECRET_PATH_RE.sub(REDACTED, text)
    if input_truncated:
        text += _TRUNCATED
    return _bound_redacted_text(text)


def _redact_value(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            key: REDACTED if _is_sensitive_key(key) else _redact_value(item)
            for key, item in value.items()
        }
    if isinstance(value, tuple):
        return tuple(_redact_value(item) for item in value)
    if isinstance(value, list):
        return [_redact_value(item) for item in value]
    if isinstance(value, set):
        return {_redact_value(item) for item in value}
    if isinstance(value, str):
        return redact_text(value)
    return value


class RedactingFormatter(logging.Formatter):
    """Format a sanitized record copy so handlers cannot leak through each other."""

    def format(self, record: logging.LogRecord) -> str:
        safe_record = copy.copy(record)
        safe_record.msg = redact_text(record.msg)
        if _BODY_CONTEXT_RE.search(str(record.msg)) and record.args:
            if isinstance(record.args, dict):
                safe_record.args = {key: REDACTED for key in record.args}
            else:
                safe_record.args = tuple(REDACTED for _ in record.args)
        else:
            safe_record.args = _redact_value(record.args)
        safe_record.exc_text = None
        if safe_record.stack_info:
            safe_record.stack_info = redact_text(safe_record.stack_info)
        return redact_text(super().format(safe_record))

    def formatException(self, exc_info) -> str:  # noqa: N802 - logging API name
        return redact_text(super().formatException(exc_info))


def _reject_symlink(path: Path) -> None:
    try:
        mode = path.lstat().st_mode
    except FileNotFoundError:
        return
    if stat.S_ISLNK(mode):
        raise OSError(f"refusing symlink log target: {path.name}")
    if not stat.S_ISREG(mode):
        raise OSError(f"refusing non-regular log target: {path.name}")


def _harden_existing_logs(log_path: Path) -> None:
    for path in log_path.parent.glob(f"{log_path.name}*"):
        try:
            mode = path.lstat().st_mode
        except OSError:
            continue
        if stat.S_ISREG(mode):
            try:
                path.chmod(0o600, follow_symlinks=False)
            except OSError as exc:
                if path == log_path:
                    raise
                logger.warning(
                    "Unable to harden rotated log file=%s error_class=%s",
                    path.name,
                    type(exc).__name__,
                )


class SecureTimedRotatingFileHandler(logging.handlers.TimedRotatingFileHandler):
    """Timed rotation with no-follow creation and mode 0600 for every log."""

    def __init__(self, filename: str | os.PathLike[str], *args, **kwargs):
        log_path = Path(filename)
        _reject_symlink(log_path)
        _harden_existing_logs(log_path)
        super().__init__(str(log_path), *args, **kwargs)
        _harden_existing_logs(log_path)

    def _open(self):
        path = Path(self.baseFilename)
        _reject_symlink(path)
        flags = os.O_WRONLY | os.O_APPEND | os.O_CREAT
        if hasattr(os, "O_NOFOLLOW"):
            flags |= os.O_NOFOLLOW
        fd = os.open(path, flags, 0o600)
        try:
            os.fchmod(fd, 0o600)
            return open(
                fd,
                self.mode,
                encoding=self.encoding,
                errors=self.errors,
                closefd=True,
            )
        except Exception:
            os.close(fd)
            raise

    def rotate(self, source: str, dest: str) -> None:
        source_path = Path(source)
        dest_path = Path(dest)
        _reject_symlink(source_path)
        _reject_symlink(dest_path)
        super().rotate(source, dest)
        dest_path.chmod(0o600, follow_symlinks=False)

    def doRollover(self) -> None:  # noqa: N802 - logging API name
        super().doRollover()
        _harden_existing_logs(Path(self.baseFilename))


def classify_task_error(error: BaseException | str | None) -> str:
    error_class = type(error).__name__.lower() if isinstance(error, BaseException) else ""
    if isinstance(error, TimeoutError):
        return "timeout"
    text = str(error or "").lower()
    if "timeout" in error_class:
        return "timeout"
    if "cancel" in error_class:
        return "cancelled"
    if any(term in text for term in ("timeout", "timed out", "超时")):
        return "timeout"
    if any(term in text for term in ("cancelled", "canceled", "shutdown", "shutting down", "取消")):
        return "cancelled"
    if any(
        term in text
        for term in (
            "unsupported",
            "invalid queued content",
            "unknown ingest type",
            "不支持",
            "invalid input",
        )
    ):
        return "unsupported_input"
    if any(
        term in text
        for term in (
            "provider unavailable",
            "service unavailable",
            "connection refused",
            "connection error",
            "temporarily unavailable",
            "http 502",
            "http 503",
            "status 502",
            "status 503",
        )
    ):
        return "provider_unavailable"
    return "task_failed"


def sanitize_task_error(error: BaseException | str | None) -> str:
    message = _TASK_MESSAGES[classify_task_error(error)]
    return message[:MAX_TASK_ERROR_LENGTH]
