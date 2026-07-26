from __future__ import annotations

import json
import os
import signal
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

import pytest

from zhiji_backend import database_backup_artifacts as artifacts
from zhiji_backend import database_backup_prerequisite as prerequisite_service

MIGRATION = "migration"
CONSUMED_AT = "2026-07-25T13:00:00+00:00"
MARKER = {
    "schema_version": 1,
    "state": "ready",
    "migration_name": MIGRATION,
    "created_at": "2026-07-25T12:00:00+00:00",
    "manifest_path": "/manifest.json",
    "manifest_sha256": "a" * 64,
    "source": {},
}


def _consume(root: Path) -> Path | None:
    ready = root / "ready.json"
    consumed = root / "consumed.json"
    return prerequisite_service.consume_backup_prerequisite(
        root / "database.sqlite",
        MIGRATION,
        ready_marker_path=lambda *_args: ready,
        consumed_marker_path=lambda *_args: consumed,
        load_json_regular=lambda path, _label: json.loads(path.read_bytes()),
        validate_marker_for_consumption=lambda *_args: None,
        validate_loaded_marker_for_consumption=lambda *_args: None,
        write_json_atomic=lambda path, payload: artifacts.write_json_atomic(
            path,
            payload,
            fsync_parent=artifacts.fsync_parent,
        ),
        now=lambda: datetime.fromisoformat(CONSUMED_AT),
        schema_version=1,
        replace=os.replace,
    )


def _kill_at_publication_step(root: Path, step: str) -> None:
    checkpoint = root / "checkpoint"
    repository = Path(__file__).parents[1]
    environment = os.environ.copy()
    environment["PYTHONPATH"] = str(repository / "src")
    script = r'''
import json
import os
import stat
import sys
import time
from datetime import datetime
from pathlib import Path

from zhiji_backend import database_backup_artifacts as artifacts
from zhiji_backend import database_backup_prerequisite as prerequisite
from zhiji_backend import _database_backup_path_publication as publication

root = Path(sys.argv[1])
step = sys.argv[2]
ready = root / "ready.json"
consumed = root / "consumed.json"
checkpoint = root / "checkpoint"
foreign = root / "foreign.json"
real_link = publication.os.link
real_rename = publication.os.rename
real_replace = publication.os.replace
real_fsync = publication.os.fsync
real_transition_fsync = publication._fsync_parent
consumed_fsyncs = 0

def pause(name):
    if step != name:
        return
    checkpoint.write_text("reached", encoding="utf-8")
    with checkpoint.open("rb") as handle:
        real_fsync(handle.fileno())
    while True:
        time.sleep(1)

def link_then_pause(source, destination, *args, **kwargs):
    result = real_link(source, destination, *args, **kwargs)
    source = Path(source)
    destination = Path(destination)
    if source == ready and destination == consumed:
        pause("consumed-linked")
    if source.name == "publication-source" and destination == consumed:
        pause("receipt-published")
    return result

def fsync_then_pause(fd):
    real_fsync(fd)
    if stat.S_ISREG(os.fstat(fd).st_mode):
        pause("receipt-temp-fsynced")

def rename_then_pause(source, destination):
    real_rename(source, destination)
    if Path(source) == consumed and Path(destination).name == "displaced-destination":
        pause("receipt-destination-displaced")
    if Path(source) == ready and Path(destination).name == "isolated":
        pause("ready-isolated")

def transition_fsync_then_pause(path):
    global consumed_fsyncs
    real_transition_fsync(path)
    if Path(path) == ready:
        pause("ready-removal-fsynced")
    else:
        consumed_fsyncs += 1
        pause(
            "consumed-link-fsynced"
            if consumed_fsyncs == 1
            else "receipt-validated-fsynced"
        )

def transition_replace(source, destination):
    real_replace(source, destination)
    if step == "foreign-collision":
        foreign.write_text('{"foreign":true}', encoding="utf-8")
        real_replace(foreign, consumed)
        pause("foreign-collision")
    pause("transition-hook-complete")

def receipt_replace(source, destination):
    real_replace(source, destination)
    if Path(destination).name == "publication-source":
        pause("receipt-source-staged")

def receipt_fsync_then_pause(path):
    artifacts.fsync_parent(path)
    pause("receipt-fsynced")

publication.os.link = link_then_pause
publication.os.rename = rename_then_pause
publication.os.fsync = fsync_then_pause
publication._fsync_parent = transition_fsync_then_pause
prerequisite.consume_backup_prerequisite(
    root / "database.sqlite",
    "migration",
    ready_marker_path=lambda *_args: ready,
    consumed_marker_path=lambda *_args: consumed,
    load_json_regular=lambda path, _label: json.loads(path.read_bytes()),
    validate_marker_for_consumption=lambda *_args: None,
    validate_loaded_marker_for_consumption=lambda *_args: None,
    write_json_atomic=lambda path, payload: artifacts.write_json_atomic(
        path,
        payload,
        fsync_parent=receipt_fsync_then_pause,
        replace=receipt_replace,
    ),
    now=lambda: datetime.fromisoformat("2026-07-25T13:00:00+00:00"),
    schema_version=1,
    replace=transition_replace,
)
'''
    process = subprocess.Popen(
        [sys.executable, "-c", script, str(root), step],
        cwd=repository,
        env=environment,
    )
    try:
        deadline = time.monotonic() + 10
        while not checkpoint.exists() and process.poll() is None:
            if time.monotonic() >= deadline:
                raise AssertionError("child did not reach publication checkpoint")
            time.sleep(0.01)
        assert process.poll() is None
        os.kill(process.pid, signal.SIGKILL)
        assert process.wait(timeout=5) == -signal.SIGKILL
    finally:
        if process.poll() is None:
            process.kill()
            process.wait(timeout=5)


@pytest.mark.parametrize(
    "step",
    [
        "consumed-linked",
        "consumed-link-fsynced",
        "transition-hook-complete",
        "receipt-temp-fsynced",
        "receipt-destination-displaced",
        "receipt-source-staged",
        "receipt-published",
        "receipt-fsynced",
        "receipt-validated-fsynced",
        "ready-isolated",
        "ready-removal-fsynced",
    ],
)
def test_restart_finishes_exact_receipt_after_each_publication_crash(
    tmp_path: Path,
    step: str,
) -> None:
    ready = tmp_path / "ready.json"
    consumed = tmp_path / "consumed.json"
    ready.write_text(json.dumps(MARKER), encoding="utf-8")

    _kill_at_publication_step(tmp_path, step)

    assert ready.exists() or consumed.exists()
    assert _consume(tmp_path) == consumed
    assert not ready.exists()
    assert json.loads(consumed.read_bytes()) == {
        **MARKER,
        "state": "consumed",
        "consumed_at": CONSUMED_AT,
    }


def test_restart_preserves_foreign_consumed_collision_after_process_kill(
    tmp_path: Path,
) -> None:
    ready = tmp_path / "ready.json"
    consumed = tmp_path / "consumed.json"
    ready.write_text(json.dumps(MARKER), encoding="utf-8")

    _kill_at_publication_step(tmp_path, "foreign-collision")

    with pytest.raises(RuntimeError, match="marker path collision"):
        _consume(tmp_path)
    assert ready.exists()
    assert consumed.read_text(encoding="utf-8") == '{"foreign":true}'

    consumed.unlink()
    assert _consume(tmp_path) == consumed
    assert json.loads(consumed.read_bytes()) == {
        **MARKER,
        "state": "consumed",
        "consumed_at": CONSUMED_AT,
    }


def test_restart_recovers_consumed_only_ready_replay_after_process_kill(
    tmp_path: Path,
) -> None:
    ready = tmp_path / "ready.json"
    consumed = tmp_path / "consumed.json"
    consumed.write_text(json.dumps(MARKER), encoding="utf-8")

    _kill_at_publication_step(tmp_path, "receipt-destination-displaced")

    assert ready.exists() or consumed.exists()
    assert _consume(tmp_path) == consumed
    assert not ready.exists()
    assert json.loads(consumed.read_bytes()) == {
        **MARKER,
        "state": "consumed",
        "consumed_at": CONSUMED_AT,
    }
