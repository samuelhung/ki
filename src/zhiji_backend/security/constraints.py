"""Reusable request constraints for identifiers, pagination, and batches."""
from __future__ import annotations

import re
from typing import Annotated, TypeVar

from pydantic import AfterValidator, Field


MAX_IDENTIFIER_LENGTH = 128
MAX_BATCH_ITEMS = 100
MAX_OFFSET = 1_000_000
MAX_PAGE_SIZE = 200

_SAFE_IDENTIFIER_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}\Z", re.ASCII)

T = TypeVar("T")


def safe_identifier(value: str) -> str:
    """Return an identifier that cannot introduce filesystem path segments."""
    if not isinstance(value, str) or not _SAFE_IDENTIFIER_RE.fullmatch(value):
        raise ValueError("invalid identifier")
    return value


def dedupe_preserve_order(values: list[T]) -> list[T]:
    """Remove duplicates without changing first-seen order."""
    return list(dict.fromkeys(values))


def dedupe_at_least_two(values: list[T]) -> list[T]:
    deduped = dedupe_preserve_order(values)
    if len(deduped) < 2:
        raise ValueError("at least two distinct identifiers are required")
    return deduped


def parse_bounded_identifier_csv(value: str | None) -> list[str] | None:
    """Parse up to 100 comma-separated safe identifiers in first-seen order."""
    if value is None:
        return None
    if len(value) > MAX_BATCH_ITEMS * (MAX_IDENTIFIER_LENGTH + 1):
        raise ValueError("too many identifier values")
    values = [item.strip() for item in value.split(",") if item.strip()]
    if len(values) > MAX_BATCH_ITEMS:
        raise ValueError("too many identifier values")
    return dedupe_preserve_order([safe_identifier(item) for item in values])


SafeIdentifier = Annotated[str, AfterValidator(safe_identifier)]
SafeIdentifierList = Annotated[
    list[SafeIdentifier],
    Field(min_length=1, max_length=MAX_BATCH_ITEMS),
    AfterValidator(dedupe_preserve_order),
]
SafeIdentifierListMinTwo = Annotated[
    list[SafeIdentifier],
    Field(min_length=2, max_length=MAX_BATCH_ITEMS),
    AfterValidator(dedupe_at_least_two),
]
BoundedIdentifierList = Annotated[
    list[SafeIdentifier],
    Field(max_length=MAX_BATCH_ITEMS),
    AfterValidator(dedupe_preserve_order),
]
