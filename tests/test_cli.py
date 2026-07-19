import json
import sys
import sqlite3
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from zhiji_backend.cli import _parse_version, main


def test_parse_version_supports_build_metadata():
    assert _parse_version("v1.3.8+83") == (1, 3, 8, 83)
    assert _parse_version("1.3.9") == (1, 3, 9)
    assert _parse_version("v1.4.0-beta+2") == (1, 4, 0, 2)


def test_backup_db_command_prints_verified_rollback_manifest_path(
    tmp_path, monkeypatch, capsys
):
    source = tmp_path / "intelligence.sqlite"
    with sqlite3.connect(source) as conn:
        conn.execute("CREATE TABLE records (value TEXT)")
        conn.execute("INSERT INTO records (value) VALUES ('committed')")
    config_path = tmp_path / "system_config.json"
    config_path.write_text('{"general": {"model": "rollback-model"}}', encoding="utf-8")

    output_dir = tmp_path / "backups"
    monkeypatch.setenv("KI_DB_PATH", str(source))
    monkeypatch.setattr(
        sys,
        "argv",
        ["zhiji", "backup-db", "--output-dir", str(output_dir)],
    )

    main()

    captured = capsys.readouterr()
    manifest_path = Path(captured.out.strip())
    assert captured.err == ""
    assert manifest_path.parent == output_dir
    assert manifest_path.exists()
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    backup = Path(manifest["artifacts"]["database"]["path"])
    config_backup = Path(manifest["artifacts"]["config"]["path"])
    with sqlite3.connect(backup) as conn:
        assert conn.execute("SELECT value FROM records").fetchall() == [("committed",)]
        assert conn.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
    assert config_backup.read_text(encoding="utf-8") == config_path.read_text(
        encoding="utf-8"
    )


def test_backup_db_command_exits_nonzero_on_error(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("KI_DB_PATH", str(tmp_path / "missing.sqlite"))
    monkeypatch.setattr(
        sys,
        "argv",
        ["zhiji", "backup-db", "--output-dir", str(tmp_path / "backups")],
    )

    with pytest.raises(SystemExit) as exc_info:
        main()

    captured = capsys.readouterr()
    assert exc_info.value.code != 0
    assert captured.out == ""
    assert "missing.sqlite" in captured.err
