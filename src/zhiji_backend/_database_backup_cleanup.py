from __future__ import annotations

import sys
from collections.abc import Callable, Iterable

CleanupAction = tuple[str, Callable[[], None]]


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
