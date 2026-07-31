"""Character-preservation rules shared by transcript revision workflows."""

from __future__ import annotations

import unicodedata


class BodyCharacterMismatchError(ValueError):
    pass


def body_sequence(value: str) -> str:
    return "".join(
        char
        for char in value
        if not char.isspace() and not unicodedata.category(char).startswith("P")
    )


def assert_same_body(source: str, candidate: str) -> None:
    if body_sequence(source) != body_sequence(candidate):
        raise BodyCharacterMismatchError(
            "AI result changed transcript body characters"
        )
