from __future__ import annotations

import hashlib
import json
import os
import signal
import sqlite3
import subprocess
import sys
import time
from pathlib import Path

import pytest

from zhiji_backend import database_backup

CHECKPOINTS = (
    "journal-publication-before",
    "journal-publication-after",
    "sidecar-quarantine-before",
    "sidecar-quarantine-after",
    "config-replacement-before",
    "config-replacement-after",
    "database-replacement-before",
    "database-replacement-after",
    "journal-quarantine-before",
    "journal-recovery-publication-before",
    "journal-recovery-publication-after",
    "journal-canonical-quarantine-before",
    "journal-canonical-quarantine-after",
    "journal-quarantine-after",
    "config-stage-cleanup-before",
    "config-stage-cleanup-after",
    "database-stage-cleanup-before",
    "database-stage-cleanup-after",
    "sidecar-cleanup-before",
    "sidecar-cleanup-after",
    "completion-before",
    "journal-removal-before",
    "journal-removal-after",
    "completion-after",
)


CHILD = r"""
import sys
import time
from pathlib import Path

from zhiji_backend import database_backup
from zhiji_backend import database_backup_restore_journal as journal_module
from zhiji_backend import database_backup_restore_sidecars as sidecar_module
from zhiji_backend import database_backup_restore_stages as stage_module

target = sys.argv[1]
manifest = Path(sys.argv[2])
ready = Path(sys.argv[3])

def pause(name):
    if name != target:
        return
    ready.write_text(name, encoding="utf-8")
    while True:
        time.sleep(1)

real_write = database_backup._write_json_exclusive
def write_journal(path, payload):
    pause("journal-publication-before")
    result = real_write(path, payload)
    pause("journal-publication-after")
    return result
database_backup._write_json_exclusive = write_journal

real_replace = database_backup._replace_staged_restore
def replace_stage(stage, destination):
    key = "database" if Path(destination).suffix == ".sqlite" else "config"
    pause(f"{key}-replacement-before")
    result = real_replace(stage, destination)
    pause(f"{key}-replacement-after")
    return result
database_backup._replace_staged_restore = replace_stage

real_sidecar_quarantine = sidecar_module.SidecarDisposition.quarantine
def quarantine_sidecars(self):
    pause("sidecar-quarantine-before")
    result = real_sidecar_quarantine(self)
    pause("sidecar-quarantine-after")
    return result
sidecar_module.SidecarDisposition.quarantine = quarantine_sidecars

real_journal_quarantine = journal_module.TrustedJournalDisposition.quarantine
def quarantine_journal(self, **kwargs):
    pause("journal-quarantine-before")
    result = real_journal_quarantine(self, **kwargs)
    pause("journal-quarantine-after")
    return result
journal_module.TrustedJournalDisposition.quarantine = quarantine_journal

real_recovery_publication = journal_module.TrustedJournalDisposition._publish_recovery
def publish_journal_recovery(self, path):
    pause("journal-recovery-publication-before")
    result = real_recovery_publication(self, path)
    pause("journal-recovery-publication-after")
    return result
journal_module.TrustedJournalDisposition._publish_recovery = publish_journal_recovery

real_move_journal = journal_module._move_to_private
def quarantine_canonical_journal(source, destination):
    pause("journal-canonical-quarantine-before")
    result = real_move_journal(source, destination)
    pause("journal-canonical-quarantine-after")
    return result
journal_module._move_to_private = quarantine_canonical_journal

real_stage_cleanup = stage_module.cleanup_owned_stage
def cleanup_stage(key, *args, **kwargs):
    pause(f"{key}-stage-cleanup-before")
    result = real_stage_cleanup(key, *args, **kwargs)
    pause(f"{key}-stage-cleanup-after")
    return result
stage_module.cleanup_owned_stage = cleanup_stage

real_sidecar_cleanup = sidecar_module.SidecarDisposition.cleanup
def cleanup_sidecars(self):
    pause("sidecar-cleanup-before")
    result = real_sidecar_cleanup(self)
    pause("sidecar-cleanup-after")
    return result
sidecar_module.SidecarDisposition.cleanup = cleanup_sidecars

real_complete = journal_module.TrustedJournalDisposition.complete
def complete(self, **kwargs):
    pause("completion-before")
    result = real_complete(self, **kwargs)
    pause("completion-after")
    return result
journal_module.TrustedJournalDisposition.complete = complete

real_remove_journal = journal_module.TrustedJournalDisposition._remove_quarantine
def remove_journal(self):
    pause("journal-removal-before")
    result = real_remove_journal(self)
    pause("journal-removal-after")
    return result
journal_module.TrustedJournalDisposition._remove_quarantine = remove_journal

database_backup.restore_rollback_backup(manifest)
raise RuntimeError(f"checkpoint was not reached: {target}")
"""


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _fixture(tmp_path: Path) -> tuple[Path, Path, Path, dict[str, str]]:
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    database_path = data_dir / "intelligence.sqlite"
    config_path = data_dir / "system_config.json"
    with sqlite3.connect(database_path) as connection:
        connection.executescript(
            "CREATE TABLE entities (id TEXT PRIMARY KEY);"
            "INSERT INTO entities VALUES ('rollback');"
        )
    config_path.write_text('{"rollback":true}\n', encoding="utf-8")
    manifest_path = database_backup.create_rollback_backup(
        database_path, config_path, tmp_path / "backups"
    )
    manifest = json.loads(manifest_path.read_bytes())
    expected = {
        key: str(manifest["artifacts"][key]["sha256"])
        for key in ("config", "database")
    }
    with sqlite3.connect(database_path) as connection:
        connection.execute("UPDATE entities SET id = 'current'")
    config_path.write_text('{"current":true}\n', encoding="utf-8")
    Path(f"{database_path}-wal").write_bytes(b"stale wal")
    Path(f"{database_path}-shm").write_bytes(b"stale shm")
    return database_path.resolve(), config_path.resolve(), manifest_path, expected


def _wait_for_checkpoint(process: subprocess.Popen[bytes], ready: Path) -> None:
    deadline = time.monotonic() + 10
    while time.monotonic() < deadline:
        if ready.exists():
            return
        if process.poll() is not None:
            stdout, stderr = process.communicate(timeout=1)
            pytest.fail(
                f"child exited before checkpoint ({process.returncode}): "
                f"{stdout.decode()}\n{stderr.decode()}"
            )
        time.sleep(0.01)
    process.kill()
    process.wait(timeout=5)
    pytest.fail("child did not reach checkpoint within 10 seconds")


def _recovery_journals(journal_path: Path) -> list[Path]:
    return list(
        journal_path.parent.glob(f".{journal_path.name}.recovery-*/{journal_path.name}")
    )


def _restart_recovery(manifest_path: Path, journal_path: Path) -> None:
    candidates = _recovery_journals(journal_path) if not journal_path.exists() else []
    if candidates:
        assert len(candidates) == 1
        database_backup.recover_rollback_restore(candidates[0])
    else:
        database_backup.restore_rollback_backup(manifest_path)


def _assert_journal_disposition(
    journal_path: Path,
    manifest_path: Path,
    destinations: dict[str, Path],
    expected: dict[str, str],
) -> None:
    assert not journal_path.exists()
    for recovery_dir in journal_path.parent.glob(
        f".{journal_path.name}.recovery-*"
    ):
        assert recovery_dir.is_dir()
        for candidate in recovery_dir.rglob("*"):
            if candidate.is_dir():
                continue
            assert candidate.is_file() and not candidate.is_symlink()
            payload = json.loads(candidate.read_bytes())
            assert set(payload) == {
                "schema_version",
                "state",
                "created_at",
                "manifest_path",
                "manifest_sha256",
                "entries",
            }
            assert payload["manifest_path"] == str(manifest_path)
            assert payload["manifest_sha256"] == _sha256(manifest_path)
            assert set(payload["entries"]) == {"config", "database"}
            for key in ("config", "database"):
                assert payload["entries"][key]["destination"] == str(
                    destinations[key]
                )
                assert payload["entries"][key]["sha256"] == expected[key]
            assert payload["schema_version"] == 1
            assert payload["state"] == "staged"


@pytest.mark.parametrize("checkpoint", CHECKPOINTS)
def test_restore_recovers_idempotently_after_sigkill_at_each_transition(
    tmp_path: Path,
    checkpoint: str,
) -> None:
    database_path, config_path, manifest_path, expected = _fixture(tmp_path)
    ready = tmp_path / "checkpoint"
    process = subprocess.Popen(
        [sys.executable, "-c", CHILD, checkpoint, str(manifest_path), str(ready)],
        cwd=Path(__file__).parents[1],
        env={
            **os.environ,
            "PYTHONPATH": str(Path(__file__).parents[1] / "src"),
        },
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    try:
        _wait_for_checkpoint(process, ready)
        os.kill(process.pid, signal.SIGKILL)
        process.wait(timeout=5)
    finally:
        if process.poll() is None:
            process.kill()
            process.wait(timeout=5)

    assert process.returncode == -signal.SIGKILL
    journal_path = database_backup.restore_journal_path(database_path)
    destinations = {"config": config_path, "database": database_path}
    for _attempt in range(2):
        _restart_recovery(manifest_path, journal_path)
        assert config_path.is_file() and not config_path.is_symlink()
        assert database_path.is_file() and not database_path.is_symlink()
        assert _sha256(config_path) == expected["config"]
        assert _sha256(database_path) == expected["database"]
        assert not Path(f"{database_path}-wal").exists()
        assert not Path(f"{database_path}-shm").exists()
        _assert_journal_disposition(
            journal_path, manifest_path, destinations, expected
        )
