"""Single-owner coordination for stopping an active ingest process tree."""

from __future__ import annotations

import threading

_claim: tuple[str, object, int | None] | None = None
_result: tuple[int | None, bool] | None = None
_complete = threading.Event()


def _facade():
    from . import task_queue

    return task_queue


def _is_claim(task_id: str, proc, group_id: int | None) -> bool:
    return bool(
        _claim and _claim[0] == task_id and _claim[1] is proc and _claim[2] == group_id
    )


def _claim_owner(task_id: str, proc, group_id: int | None) -> bool:
    """Claim ownership while the caller holds the active-process lock."""
    global _claim, _result
    if _is_claim(task_id, proc, group_id):
        return False
    _claim = (task_id, proc, group_id)
    _result = None
    _complete.clear()
    return True


def select_active_for_shutdown():
    q = _facade()
    with q._active_process_lock:
        proc, task_id = q._active_process, q._active_task_id
        group_id = q._active_process_group_id
        if proc is None or task_id is None:
            return None, None, None, False
        leader_alive = q._observe_process_returncode(proc, task_id, "selection") is None
        group_alive = q._process_group_exists(group_id, task_id)
        if not leader_alive and not group_alive:
            return None, None, None, False
        owner = _claim_owner(task_id, proc, group_id)
        if owner and leader_alive:
            q._shutdown_interrupted = (task_id, proc)
            q._shutdown_signals_sent.clear()
            q._shutdown_signal_delivery_confirmed = False
            q._shutdown_fallback_causation = False
            q._shutdown_signal_resolved.clear()
        return proc, task_id, group_id, owner


def complete_shutdown_claim(
    task_id: str,
    proc,
    group_id: int | None,
    returncode: int | None,
    quiesced: bool,
) -> None:
    global _result
    q = _facade()
    with q._active_process_lock:
        if not _is_claim(task_id, proc, group_id):
            return
        _result = (returncode, quiesced)
        _complete.set()


def wait_for_shutdown_owner(
    task_id: str, proc, group_id: int | None, timeout: float
) -> tuple[int | None, bool]:
    q = _facade()
    _complete.wait(timeout=max(0.0, timeout * 2))
    with q._active_process_lock:
        result = _result if _is_claim(task_id, proc, group_id) else None
    if result is not None:
        return result
    returncode = q._observe_process_returncode(proc, task_id, "owner wait")
    quiesced = returncode is not None and not q._process_group_exists(group_id, task_id)
    return returncode, quiesced
