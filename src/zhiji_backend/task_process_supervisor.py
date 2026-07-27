"""Child-process ownership and execution for the ingest task queue."""

from __future__ import annotations

import errno
import json
import signal
import time
from pathlib import Path

from . import task_queue_store as store

POST_PROCESS = object()


def _facade():
    from . import task_queue

    return task_queue


def observe_returncode(proc, task_id: str, phase: str) -> int | None:
    q = _facade()
    try:
        return proc.poll()
    except Exception:
        q.logger.warning(
            "Failed to poll ingest child for task %s during %s",
            task_id,
            phase,
            exc_info=True,
        )
        try:
            return proc.returncode
        except Exception:
            return None


def process_group_exists(process_group_id: int | None, task_id: str) -> bool:
    q = _facade()
    if q.os.name != "posix" or process_group_id is None:
        return False
    try:
        if process_group_id == q.os.getpgrp():
            return False
        q.os.killpg(process_group_id, 0)
        return True
    except ProcessLookupError:
        return False
    except OSError as exc:
        if exc.errno == errno.ESRCH:
            return False
        if exc.errno == errno.EPERM:
            return True
        q.logger.warning(
            "Failed to inspect ingest process group for task %s",
            task_id,
            exc_info=True,
        )
        return True
    except Exception:
        q.logger.warning(
            "Failed to inspect ingest process group for task %s",
            task_id,
            exc_info=True,
        )
        return True


def signal_process(
    proc, process_group_id, sig, fallback_operation, task_id, log_failure_fn
):
    q = _facade()
    if q.os.name == "posix" and process_group_id is not None:
        try:
            own_group_id = q.os.getpgrp()
        except Exception:
            q.logger.warning("Failed to inspect server process group", exc_info=True)
        else:
            if process_group_id != own_group_id:
                try:
                    q.os.killpg(process_group_id, sig)
                    return True, False
                except Exception:
                    log_failure_fn(task_id, f"process-group {fallback_operation}")
            else:
                q.logger.error(
                    "Refusing to signal server process group for ingest task %s",
                    task_id,
                )
    try:
        getattr(proc, fallback_operation)()
        return True, True
    except Exception:
        log_failure_fn(task_id, fallback_operation)
        return False, True


def wait_for_process_tree_exit(
    proc,
    process_group_id: int | None,
    task_id: str,
    timeout: float,
    observe_fn,
    group_exists_fn,
) -> tuple[int | None, bool]:
    q = _facade()
    deadline = time.monotonic() + max(0.0, timeout)
    returncode = observe_fn(proc, task_id, "process-tree wait")
    while True:
        group_gone = not group_exists_fn(process_group_id, task_id)
        if returncode is not None and group_gone:
            return returncode, True
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            return returncode, returncode is not None and group_gone
        if returncode is None:
            try:
                returncode = proc.wait(timeout=min(0.05, remaining))
            except q.subprocess.TimeoutExpired:
                pass
            except Exception:
                q._log_shutdown_operation_failure(task_id, "process-tree wait")
                returncode = observe_fn(
                    proc, task_id, "after process-tree wait failure"
                )
                return returncode, (
                    returncode is not None
                    and not group_exists_fn(process_group_id, task_id)
                )
        else:
            time.sleep(min(0.05, remaining))


def _record_signal(task_id, proc, sig, used_fallback, returncode) -> None:
    q = _facade()
    with q._active_process_lock:
        if q._shutdown_interrupted != (task_id, proc):
            return
        if not used_fallback:
            q._shutdown_signals_sent.add(int(sig))
            q._shutdown_signal_delivery_confirmed = True
        elif returncode is None:
            q._shutdown_signals_sent.add(int(sig))
            q._shutdown_signal_delivery_confirmed = True
        elif returncode == -int(sig):
            q._shutdown_signals_sent.add(int(sig))
        if used_fallback and q.os.name != "posix" and returncode is None:
            q._shutdown_fallback_causation = True


def matches_shutdown_causation(task_id: str, proc, returncode) -> bool:
    q = _facade()
    with q._active_process_lock:
        if q._shutdown_interrupted != (task_id, proc) or returncode is None:
            return False
        if returncode < 0 and -returncode in q._shutdown_signals_sent:
            return True
        if returncode >= 0 and q._shutdown_signal_delivery_confirmed:
            return True
        return q._shutdown_fallback_causation


def release_active_process(task_id: str, proc) -> bool:
    q = _facade()
    with q._active_process_lock:
        selected = q._shutdown_interrupted == (task_id, proc)
        if q._active_process is proc and q._active_task_id == task_id:
            q._active_process = None
            q._active_task_id = None
            q._active_process_group_id = None
    if not selected:
        return False
    q._shutdown_signal_resolved.wait(timeout=q._SHUTDOWN_TERMINATE_TIMEOUT_SECONDS)
    return matches_shutdown_causation(task_id, proc, proc.returncode)


def clear_shutdown_interrupted(task_id: str, proc) -> None:
    q = _facade()
    with q._active_process_lock:
        if q._shutdown_interrupted == (task_id, proc):
            q._shutdown_interrupted = None
            q._shutdown_signals_sent.clear()
            q._shutdown_signal_delivery_confirmed = False
            q._shutdown_fallback_causation = False
            q._shutdown_signal_resolved.clear()


def select_active_for_shutdown():
    q = _facade()
    with q._active_process_lock:
        proc, task_id = q._active_process, q._active_task_id
        group_id = q._active_process_group_id
        if proc is None or task_id is None:
            return None, None, None
        leader_alive = q._observe_process_returncode(proc, task_id, "selection") is None
        group_alive = q._process_group_exists(group_id, task_id)
        if leader_alive:
            q._shutdown_interrupted = (task_id, proc)
            q._shutdown_signals_sent.clear()
            q._shutdown_signal_delivery_confirmed = False
            q._shutdown_fallback_causation = False
            q._shutdown_signal_resolved.clear()
        elif not group_alive:
            return None, None, None
        return proc, task_id, group_id


def resolve_shutdown_interruption(task_id: str, proc) -> None:
    q = _facade()
    with q._active_process_lock:
        if q._shutdown_interrupted == (task_id, proc):
            q._shutdown_signal_resolved.set()


def stop_process_tree(task_id: str, proc, process_group_id, timeout: float):
    q = _facade()
    sent, fallback = q._signal_ingest_process(
        proc, process_group_id, signal.SIGTERM, "terminate", task_id
    )
    if sent:
        code = q._observe_process_returncode(proc, task_id, "after terminate")
        _record_signal(task_id, proc, signal.SIGTERM, fallback, code)
        code, quiesced = q._wait_for_process_tree_exit(
            proc, process_group_id, task_id, timeout
        )
    else:
        code = q._observe_process_returncode(proc, task_id, "after failed terminate")
        quiesced = code is not None and not q._process_group_exists(
            process_group_id, task_id
        )
    if not quiesced:
        sent, fallback = q._signal_ingest_process(
            proc, process_group_id, signal.SIGKILL, "kill", task_id
        )
        if sent:
            code = q._observe_process_returncode(proc, task_id, "after kill")
            _record_signal(task_id, proc, signal.SIGKILL, fallback, code)
        code, quiesced = q._wait_for_process_tree_exit(
            proc, process_group_id, task_id, timeout
        )
    return code, quiesced


def _spawn(task_id: str):
    q = _facade()
    with q._active_process_lock:
        if q._shutdown_flag.is_set():
            return None, None
        kwargs = {
            "stdout": q.subprocess.PIPE,
            "stderr": q.subprocess.PIPE,
            "text": True,
        }
        if q.os.name == "posix":
            kwargs["start_new_session"] = True
        proc = q.subprocess.Popen(
            [q.sys.executable, "-m", "zhiji_backend.ingest_task_runner", task_id],
            **kwargs,
        )
        q._active_process, q._active_task_id = proc, task_id
        pid = getattr(proc, "pid", None)
        group_id = (
            pid if q.os.name == "posix" and isinstance(pid, int) and pid > 0 else None
        )
        q._active_process_group_id = group_id
        return proc, group_id


def _log_task_error(task_id: str, error_class: str, raw_error) -> None:
    q = _facade()
    q.logger.error(
        "module=%s task=%s status=error error_class=%s error_code=%s",
        q.__name__,
        task_id,
        error_class,
        q.classify_task_error(raw_error),
    )


def _handle_timeout(task_id, event_id, proc, group_id) -> bool:
    q = _facade()
    q._signal_ingest_process(proc, group_id, signal.SIGTERM, "terminate", task_id)
    try:
        proc.communicate(timeout=10)
    except q.subprocess.TimeoutExpired:
        q._signal_ingest_process(proc, group_id, signal.SIGKILL, "kill", task_id)
        try:
            proc.communicate(timeout=q._SHUTDOWN_TERMINATE_TIMEOUT_SECONDS)
        except q.subprocess.TimeoutExpired:
            q.logger.error("Task %s child did not exit after timeout kill", task_id)
        _, quiesced = q._wait_for_process_tree_exit(
            proc, group_id, task_id, q._SHUTDOWN_TERMINATE_TIMEOUT_SECONDS
        )
    else:
        if q._process_group_exists(group_id, task_id):
            q._signal_ingest_process(proc, group_id, signal.SIGKILL, "kill", task_id)
            _, quiesced = q._wait_for_process_tree_exit(
                proc, group_id, task_id, q._SHUTDOWN_TERMINATE_TIMEOUT_SECONDS
            )
        else:
            quiesced = True
    if q._release_active_process(task_id, proc):
        q._restore_shutdown_interrupted_task(task_id)
        return True
    if not quiesced:
        raw = "内部超时：采集进程组在 SIGKILL 后仍未退出，已阻止自动重试"
        store.mark_error(
            task_id,
            event_id,
            q.sanitize_task_error(raw),
            q.connect,
            processing_only=False,
        )
        _log_task_error(task_id, "TimeoutError", raw)
        return True
    raw = TimeoutError(f"任务超时（{q._TASK_TIMEOUT_SECONDS}s），已自动重试1次仍失败")
    outcome, retries = store.apply_timeout(
        task_id, event_id, q.sanitize_task_error(raw), q.connect
    )
    if outcome == "done":
        q.logger.warning(
            "Task %s completed but exceeded %ss timeout — marked done",
            task_id,
            q._TASK_TIMEOUT_SECONDS,
        )
    elif outcome == "retry":
        q.logger.warning(
            "Task %s timed out — auto-retrying in 60s (retry %d→%d)",
            task_id,
            retries,
            retries + 1,
        )
    else:
        _log_task_error(task_id, type(raw).__name__, raw)
    return True


def process_one(task_id: str) -> None:
    """Process one task while owning all child-process supervision."""
    q = _facade()
    row = store.load_task(task_id, q.connect)
    if not row:
        return
    event_id, payload = row["event_id"], json.loads(row["payload_json"])
    if payload.get("content_path"):
        try:
            q.resolve_under(
                q.PENDING_DIR, Path(payload["content_path"]), expected="file"
            )
        except (q.PathSecurityError, TypeError, ValueError):
            raw = "invalid queued content path"
            store.mark_error(task_id, event_id, q.sanitize_task_error(raw), q.connect)
            _log_task_error(task_id, "PathSecurityError", raw)
            return
    store.mark_running(task_id, q.connect)
    proc, group_id = _spawn(task_id)
    if proc is None:
        q._restore_shutdown_interrupted_task(task_id)
        return
    interrupted = False
    try:
        try:
            stdout, stderr = proc.communicate(timeout=q._TASK_TIMEOUT_SECONDS)
        except q.subprocess.TimeoutExpired:
            _handle_timeout(task_id, event_id, proc, group_id)
            return
        interrupted = q._release_active_process(task_id, proc)
        if interrupted:
            q._restore_shutdown_interrupted_task(task_id)
            return
        if proc.returncode != 0:
            raw = stderr or stdout or f"ingest child exited with {proc.returncode}"
            store.mark_error(task_id, event_id, q.sanitize_task_error(raw), q.connect)
            _log_task_error(task_id, "ChildProcessError", raw)
            return
        store.mark_done(task_id, q.connect)
        if path := payload.get("content_path"):
            store.safe_pending_unlink(str(path), q.PENDING_DIR, q.logger)
        q.logger.info("Task %s completed for event %s", task_id, event_id)
    finally:
        owns_shutdown = q._shutdown_interrupted == (task_id, proc)
        interrupted = q._release_active_process(task_id, proc) or interrupted
        if owns_shutdown:
            clear_shutdown_interrupted(task_id, proc)
    return POST_PROCESS, event_id
