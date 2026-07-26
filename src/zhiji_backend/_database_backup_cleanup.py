from __future__ import annotations

import os
import sys
from collections.abc import Callable, Iterable
from itertools import chain
from typing import Protocol

CleanupAction = tuple[str, Callable[[], None]]


class Closable(Protocol):
    def close(self) -> None: ...


def close_file_descriptor(resource: object, attribute: str) -> None:
    fd = getattr(resource, attribute)
    if fd >= 0:
        os.close(fd)
        setattr(resource, attribute, -1)


def close_actions(
    label: str, resources: Iterable[Closable]
) -> Iterable[CleanupAction]:
    return (
        (f"{label} {index}", resource.close)
        for index, resource in enumerate(resources)
    )


def argument_actions(
    label: str,
    entries: Iterable[tuple[str, tuple[object, ...]]],
    action: Callable[..., None],
) -> Iterable[CleanupAction]:
    return (
        (f"{label} {key}", lambda args=args: action(*args))
        for key, args in entries
    )


def run_composite_cleanup(*groups: Iterable[CleanupAction]) -> None:
    run_best_effort_cleanup(chain.from_iterable(groups))


def run_best_effort_cleanup(actions: Iterable[CleanupAction]) -> None:
    active_error = sys.exception()
    failures: list[tuple[str, Exception]] = []
    for label, action in actions:
        try:
            action()
        except Exception as exc:
            failures.append((label, exc))

    if active_error is not None:
        for label, failure in failures:
            active_error.add_note(
                f"{label} cleanup failed: {type(failure).__name__}: {failure}"
            )
        return
    if not failures:
        return

    _primary_label, primary_failure = failures[0]
    for label, failure in failures[1:]:
        primary_failure.add_note(
            f"{label} cleanup failed: {type(failure).__name__}: {failure}"
        )
    raise primary_failure
