"""Study PDF and image intake workflows."""

from __future__ import annotations

import base64
import logging
import os
import shutil
import tempfile
from pathlib import Path

logger = logging.getLogger("zhiji_backend.routes.study_routes")


class UnsupportedFileTypeError(ValueError):
    pass


class InvalidFileTypeError(ValueError):
    pass


class PdfProcessingError(RuntimeError):
    pass


class EmptyOcrResultError(ValueError):
    pass


def _create_directory(path: Path, *, parents: bool = False) -> bool:
    try:
        path.mkdir(mode=0o700, parents=parents)
    except FileExistsError:
        return False
    return True


def _fsync_directory(path: Path) -> None:
    flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0)
    descriptor = os.open(path, flags)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _fsync_directory_best_effort(path: Path) -> None:
    try:
        _fsync_directory(path)
    except OSError:
        pass


def _remove_owned_directory(path: Path | None, *, owned: bool) -> None:
    if path is None or not owned:
        return
    try:
        path.rmdir()
    except OSError:
        return
    _fsync_directory_best_effort(path.parent)


def _remove_file(path: Path | None) -> None:
    if path is None:
        return
    try:
        path.unlink(missing_ok=True)
    except OSError:
        pass


def _file_identity(path: Path) -> tuple[int, int]:
    stat_result = path.lstat()
    return stat_result.st_dev, stat_result.st_ino


def _remove_file_if_identity_matches(
    path: Path | None, identity: tuple[int, int] | None
) -> None:
    if path is None or identity is None:
        return
    try:
        if _file_identity(path) != identity:
            return
        path.unlink()
    except OSError:
        return
    _fsync_directory_best_effort(path.parent)


def _link_staging_no_clobber(staging: Path, destination: Path) -> None:
    os.link(staging, destination)


def _publish_no_clobber(source: Path, destination: Path) -> tuple[int, int]:
    descriptor, staging_name = tempfile.mkstemp(
        prefix=f".{destination.name}.", suffix=".tmp", dir=destination.parent
    )
    staging = Path(staging_name)
    published_identity = None
    try:
        with os.fdopen(descriptor, "wb") as output:
            descriptor = -1
            with source.open("rb") as input_file:
                shutil.copyfileobj(input_file, output)
            output.flush()
            os.fsync(output.fileno())
        identity = _file_identity(staging)
        _link_staging_no_clobber(staging, destination)
        published_identity = identity
        staging.unlink()
        _fsync_directory(destination.parent)
        return identity
    except BaseException:
        _remove_file(staging)
        _remove_file_if_identity_matches(destination, published_identity)
        raise
    finally:
        if descriptor >= 0:
            os.close(descriptor)


def upload_and_ocr(
    file,
    category,
    subject,
    study_type,
    grade,
    title,
    *,
    kind_for_filename_fn,
    max_bytes_for_kind_fn,
    stream_upload_to_temp_fn,
    validate_file_fn,
    resolve_under_fn,
    connect_fn,
    init_db_fn,
    uuid_fn,
    process_pdf_fn,
    ocr_page_fn,
    study_data_dir,
    ocr_pdf_max_bytes,
    file_kind_type,
):
    ext = Path(file.filename or "upload.pdf").suffix.lower()
    if ext not in (".pdf", ".png", ".jpg", ".jpeg", ".webp"):
        raise UnsupportedFileTypeError(ext)

    filename = file.filename or f"upload{ext}"
    kind = kind_for_filename_fn(filename)
    if kind not in {file_kind_type.DOCUMENT, file_kind_type.IMAGE}:
        raise InvalidFileTypeError
    max_bytes = max_bytes_for_kind_fn(kind)
    if ext == ".pdf" and category != "教材/课本":
        max_bytes = min(max_bytes, ocr_pdf_max_bytes)
    tmp_path = stream_upload_to_temp_fn(file, max_bytes=max_bytes, suffix=ext)
    try:
        validate_file_fn(tmp_path, filename=filename)
    except BaseException:
        tmp_path.unlink(missing_ok=True)
        raise

    if category == "教材/课本":
        material_id = str(uuid_fn())
        material_dir = None
        raw_dir = None
        dest = None
        material_dir_owned = False
        raw_dir_owned = False
        published_identity = None
        succeeded = False
        try:
            material_dir = resolve_under_fn(
                study_data_dir, material_id, must_exist=False
            )
            material_dir_owned = _create_directory(material_dir, parents=True)
            if material_dir_owned:
                material_dir.chmod(0o700)
                _fsync_directory(material_dir.parent)
            material_dir = resolve_under_fn(study_data_dir, material_id, expected="dir")
            raw_dir = resolve_under_fn(material_dir, "raw", must_exist=False)
            raw_dir_owned = _create_directory(raw_dir)
            if raw_dir_owned:
                raw_dir.chmod(0o700)
                _fsync_directory(raw_dir.parent)
            raw_dir = resolve_under_fn(material_dir, "raw", expected="dir")
            dest = resolve_under_fn(raw_dir, f"original{ext}", must_exist=False)
            published_identity = _publish_no_clobber(tmp_path, dest)

            init_db_fn()
            with connect_fn() as conn:
                conn.execute(
                    """INSERT INTO study_materials
                       (id, subject, grade, textbook, study_type, title, source_type, raw_content, status)
                       VALUES (?, ?, ?, ?, ?, ?, 'pdf', ?, 'draft')""",
                    (
                        material_id,
                        subject,
                        grade,
                        title or "",
                        "教材/课本",
                        title or file.filename.rsplit(".", 1)[0],
                        str(dest.relative_to(study_data_dir.parent)),
                    ),
                )
            result = {
                "material_id": material_id,
                "text": "",
                "file_saved": str(dest.relative_to(study_data_dir.parent)),
                "skip_ocr": True,
                "auto_created": True,
            }
            succeeded = True
            return result
        finally:
            _remove_file(tmp_path)
            if not succeeded:
                _remove_file_if_identity_matches(dest, published_identity)
                _remove_owned_directory(raw_dir, owned=raw_dir_owned)
                _remove_owned_directory(material_dir, owned=material_dir_owned)

    try:
        text = ""
        if ext == ".pdf":
            try:
                result = process_pdf_fn(tmp_path)
                text = result.get("text", "")
            except Exception as exc:
                raise PdfProcessingError(str(exc)) from exc
        else:
            encoded = base64.b64encode(tmp_path.read_bytes()).decode()
            text = ocr_page_fn(encoded)

        material_id = str(uuid_fn())
        material_dir = resolve_under_fn(study_data_dir, material_id, must_exist=False)
        material_dir.mkdir(parents=True, exist_ok=True)
        material_dir = resolve_under_fn(study_data_dir, material_id, expected="dir")
        raw_dir = resolve_under_fn(material_dir, "raw", must_exist=False)
        raw_dir.mkdir(exist_ok=True)
        raw_dir = resolve_under_fn(material_dir, "raw", expected="dir")
        dest = resolve_under_fn(raw_dir, f"uploaded{ext}", must_exist=False)
        tmp_path.rename(dest)
        return {
            "material_id": material_id,
            "text": text.strip(),
            "file_saved": str(dest.relative_to(study_data_dir.parent)),
        }
    finally:
        if tmp_path.exists():
            tmp_path.unlink(missing_ok=True)


def upload_image(
    file,
    subject,
    study_type,
    grade,
    *,
    kind_for_filename_fn,
    max_bytes_for_kind_fn,
    stream_upload_to_temp_fn,
    validate_file_fn,
    ocr_image_fn,
    create_material_fn,
    request_factory,
    file_kind_type,
):
    filename = file.filename or "upload.jpg"
    suffix = Path(filename).suffix.lower()
    kind = kind_for_filename_fn(filename)
    if kind is not file_kind_type.IMAGE:
        raise InvalidFileTypeError
    tmp_path = stream_upload_to_temp_fn(
        file, max_bytes=max_bytes_for_kind_fn(kind), suffix=suffix
    )
    try:
        validate_file_fn(tmp_path, filename=filename)
        raw_content = ocr_image_fn(tmp_path)
        if not raw_content:
            raise EmptyOcrResultError
    finally:
        tmp_path.unlink(missing_ok=True)

    title = raw_content.split("\n")[0][:40] if raw_content else "图片题目"
    return create_material_fn(
        request_factory(
            subject=subject,
            study_type=study_type,
            title=title,
            raw_content=raw_content,
            grade=grade,
            source_type="photo",
        )
    )


def _ocr_image_path(path, *, ocr_page_fn):
    return ocr_page_fn(base64.b64encode(path.read_bytes()).decode("ascii"))
