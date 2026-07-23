
import pytest

from zhiji_backend.security.constraints import safe_identifier
from zhiji_backend.security.paths import (
    PathSecurityError,
    resolve_under,
    safe_unlink_under,
)


@pytest.mark.parametrize(
    "value",
    [
        "a",
        "evt-ingest-0123abcd",
        "550e8400-e29b-41d4-a716-446655440000",
        "series.2026_07-21",
        "A" + "x" * 127,
    ],
)
def test_safe_identifier_accepts_existing_generated_shapes(value):
    assert safe_identifier(value) == value


@pytest.mark.parametrize(
    "value",
    [
        "",
        ".",
        "..",
        ".hidden",
        "../event",
        "event/child",
        r"event\child",
        "event\x00child",
        "event\nchild",
        "-event",
        "A" + "x" * 128,
        "事件-1",
    ],
)
def test_safe_identifier_rejects_unsafe_values(value):
    with pytest.raises(ValueError, match="invalid identifier"):
        safe_identifier(value)


def test_resolve_under_accepts_regular_file_and_directory(tmp_path):
    directory = tmp_path / "root" / "documents"
    directory.mkdir(parents=True)
    file_path = directory / "event-1.pdf"
    file_path.write_bytes(b"pdf")

    assert resolve_under(tmp_path / "root", "documents", expected="dir") == directory
    assert (
        resolve_under(
            tmp_path / "root", "documents", "event-1.pdf", expected="file"
        )
        == file_path
    )


@pytest.mark.parametrize("part", ["../outside.txt", "documents/../../outside.txt"])
def test_resolve_under_rejects_traversal(tmp_path, part):
    root = tmp_path / "root"
    root.mkdir()

    with pytest.raises(PathSecurityError):
        resolve_under(root, part, must_exist=False)


def test_resolve_under_rejects_symlink_component_and_final_symlink(tmp_path):
    root = tmp_path / "root"
    outside = tmp_path / "outside"
    root.mkdir()
    outside.mkdir()
    (outside / "secret.txt").write_text("secret", encoding="utf-8")
    (root / "linked-dir").symlink_to(outside, target_is_directory=True)
    (root / "linked-file.txt").symlink_to(outside / "secret.txt")

    with pytest.raises(PathSecurityError):
        resolve_under(root, "linked-dir", "secret.txt", expected="file")
    with pytest.raises(PathSecurityError):
        resolve_under(root, "linked-file.txt", expected="file")


def test_resolve_under_requires_expected_type(tmp_path):
    root = tmp_path / "root"
    root.mkdir()
    (root / "file.txt").write_text("x", encoding="utf-8")
    (root / "directory").mkdir()

    with pytest.raises(PathSecurityError):
        resolve_under(root, "file.txt", expected="dir")
    with pytest.raises(PathSecurityError):
        resolve_under(root, "directory", expected="file")


def test_safe_unlink_under_removes_regular_file_but_not_symlink(tmp_path):
    root = tmp_path / "root"
    outside = tmp_path / "outside.txt"
    root.mkdir()
    outside.write_text("keep", encoding="utf-8")
    regular = root / "remove.txt"
    regular.write_text("remove", encoding="utf-8")
    link = root / "linked.txt"
    link.symlink_to(outside)

    assert safe_unlink_under(root, regular) is True
    assert not regular.exists()
    with pytest.raises(PathSecurityError):
        safe_unlink_under(root, link)
    assert outside.read_text(encoding="utf-8") == "keep"
