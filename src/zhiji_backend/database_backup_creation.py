from __future__ import annotations

import sqlite3
from collections.abc import Callable
from datetime import datetime
from functools import partial
from pathlib import Path
from typing import Any, Protocol

from ._database_backup_cleanup import run_best_effort_cleanup

FileIdentity = tuple[int, int]
CanonicalSource = Callable[[Path, str], tuple[Path, FileIdentity]]


class PinnedManifest(Protocol):
    sha256: str

    def close(self) -> None: ...


def _close_lock_connection(lock_conn: sqlite3.Connection) -> None:
    run_best_effort_cleanup(
        (("rollback", lock_conn.rollback), ("close", lock_conn.close))
    )


def _migration_is_pending(
    source: Path,
    migration_name: str,
    *,
    connect: Callable[..., sqlite3.Connection],
    read_only_uri: Callable[[Path], str],
) -> bool:
    with connect(read_only_uri(source), uri=True) as conn:
        migrations_table = conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = '_migrations'"
        ).fetchone()
        if migrations_table is None:
            return True
        return conn.execute(
            "SELECT 1 FROM _migrations WHERE name = ?", (migration_name,)
        ).fetchone() is None


def backup_database(
    source: Path,
    output_dir: Path,
    *,
    canonical_regular_source: CanonicalSource,
    read_only_uri: Callable[[Path], str],
    require_source_identity: Callable[[Path, FileIdentity], None],
    verify_backup: Callable[[Path], None],
    regular_file_identity: Callable[[Path], FileIdentity],
    publish_backup: Callable[[Path, Path, FileIdentity], None],
    unlink_if_identity: Callable[[Path, FileIdentity], None],
    connect: Callable[..., sqlite3.Connection],
    now: Callable[[], datetime],
    mkdtemp: Callable[..., str],
    remove_tree: Callable[[Path], None],
    temp_prefix: str,
    on_published: Callable[[Path, FileIdentity], None] | None = None,
) -> Path:
    """Create and verify a timestamped SQLite backup without overwriting files."""
    source, source_identity = canonical_regular_source(source, "database source")
    output_dir = Path(output_dir).expanduser()
    output_dir.mkdir(parents=True, exist_ok=True)
    output_dir = output_dir.resolve(strict=True)
    timestamp = now().strftime("%Y%m%d-%H%M%S")
    target = output_dir / f"intelligence-pre-cleanup-{timestamp}.sqlite"
    temp_dir = Path(mkdtemp(prefix=temp_prefix, dir=output_dir))
    staged_backup = temp_dir / "backup.sqlite"
    staged_identity: FileIdentity | None = None

    try:
        with connect(read_only_uri(source), uri=True) as src:
            require_source_identity(source, source_identity)
            with connect(staged_backup) as dst:
                src.backup(dst)
            require_source_identity(source, source_identity)
        verify_backup(staged_backup)
        require_source_identity(source, source_identity)
        staged_identity = regular_file_identity(staged_backup)
        publish_backup(staged_backup, target, staged_identity)
        published_identity = regular_file_identity(target)
        if published_identity != staged_identity:
            raise RuntimeError("published backup identity mismatch")
        if on_published is not None:
            on_published(target, published_identity)
    except Exception:
        if staged_identity is not None:
            unlink_if_identity(target, staged_identity)
        raise
    finally:
        try:
            remove_tree(temp_dir)
        except FileNotFoundError:
            pass

    return target


def create_rollback_backup(
    source: Path,
    config_path: Path,
    output_dir: Path,
    *,
    migration_name: str,
    schema_version: int,
    canonical_regular_source: CanonicalSource,
    source_metadata: Callable[[Path], dict[str, int]],
    marker_path_for: Callable[[Path, str], Path],
    sqlite_snapshot_sha256: Callable[[Path], str],
    backup_database: Callable[..., Path],
    copy_regular_file: Callable[[Path, Path], FileIdentity],
    artifact_metadata: Callable[..., dict[str, Any]],
    write_json_exclusive: Callable[[Path, dict[str, Any]], FileIdentity],
    pin_json_file: Callable[[Path, str], tuple[PinnedManifest, dict[str, Any]]],
    write_json_atomic: Callable[..., None],
    unlink_if_identity: Callable[[Path, FileIdentity], None],
    migration_is_pending: Callable[[Path, str], bool],
    read_only_uri: Callable[[Path], str],
    connect: Callable[..., sqlite3.Connection],
    now: Callable[[], datetime],
    now_utc: Callable[[], datetime],
) -> Path:
    """Archive the live database and config, then publish the migration marker."""
    source, _ = canonical_regular_source(source, "database source")
    config_path, _ = canonical_regular_source(config_path, "config source")
    initial_source_metadata = source_metadata(source)
    initial_config_metadata = source_metadata(config_path)

    output_dir = Path(output_dir).expanduser()
    marker_path = marker_path_for(source, migration_name)
    database_backup_path: Path | None = None
    config_backup: Path | None = None
    manifest_path: Path | None = None
    owned_publications: list[tuple[Path, FileIdentity]] = []
    marker_published = False
    lock_conn = connect(str(source))

    try:
        lock_conn.execute("PRAGMA busy_timeout=5000")
        lock_conn.execute("BEGIN IMMEDIATE")
        if not migration_is_pending(source, migration_name):
            raise RuntimeError(f"migration {migration_name} is not pending")
        output_dir.mkdir(parents=True, exist_ok=True)
        output_dir = output_dir.resolve(strict=True)
        timestamp = now().strftime("%Y%m%d-%H%M%S")
        config_backup = output_dir / f"system_config-pre-cleanup-{timestamp}.json"
        manifest_path = output_dir / f"rollback-manifest-{timestamp}.json"
        snapshot_sha256 = sqlite_snapshot_sha256(source)

        def own_publication(path: Path, identity: FileIdentity) -> None:
            owned_publications.append((path, identity))

        database_backup_path = backup_database(
            source, output_dir, on_published=own_publication
        )
        config_identity = copy_regular_file(config_path, config_backup)
        owned_publications.append((config_backup, config_identity))
        if (
            source_metadata(source) != initial_source_metadata
            or source_metadata(config_path) != initial_config_metadata
            or sqlite_snapshot_sha256(source) != snapshot_sha256
        ):
            raise RuntimeError("database or config source changed during rollback backup")
        created_at = now_utc().isoformat()
        manifest = {
            "schema_version": schema_version,
            "migration_name": migration_name,
            "created_at": created_at,
            "marker_path": str(marker_path),
            "source": {
                "database_path": str(source),
                "config_path": str(config_path),
                "database_identity": initial_source_metadata,
                "config_identity": initial_config_metadata,
                "sqlite_snapshot_sha256": snapshot_sha256,
            },
            "artifacts": {
                "database": artifact_metadata(
                    database_backup_path, integrity_check="ok"
                ),
                "config": artifact_metadata(config_backup),
                "digest_archive": None,
            },
        }
        manifest_identity = write_json_exclusive(manifest_path, manifest)
        owned_publications.append((manifest_path, manifest_identity))
        manifest_path = manifest_path.resolve(strict=True)
        manifest_pin, published_manifest = pin_json_file(manifest_path, "manifest")
        try:
            if published_manifest != manifest:
                raise RuntimeError("backup prerequisite manifest publication mismatch")
            manifest_sha256 = manifest_pin.sha256
        finally:
            manifest_pin.close()
        marker = {
            "schema_version": schema_version,
            "state": "ready",
            "migration_name": migration_name,
            "created_at": created_at,
            "manifest_path": str(manifest_path),
            "manifest_sha256": manifest_sha256,
            "source": manifest["source"],
        }
        def mark_published() -> None:
            nonlocal marker_published
            marker_published = True

        write_json_atomic(marker_path, marker, on_published=mark_published)
    except Exception:
        if not marker_published:
            run_best_effort_cleanup(
                (
                    (
                        f"publication {path.name}",
                        partial(unlink_if_identity, path, identity),
                    )
                    for path, identity in reversed(owned_publications)
                )
            )
        raise
    finally:
        _close_lock_connection(lock_conn)

    if manifest_path is None:
        raise RuntimeError("rollback backup manifest was not created")
    return manifest_path
