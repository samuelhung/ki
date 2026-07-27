"""Study material persistence, generation, review, files, and reporting."""

from __future__ import annotations

import logging

from .security.constraints import MAX_OFFSET

logger = logging.getLogger("zhiji_backend.routes.study_routes")


class PaginationOffsetError(ValueError):
    pass


class MaterialNotFoundError(LookupError):
    pass


class MaterialGenerationError(RuntimeError):
    pass


class MistakeReviewError(RuntimeError):
    pass


class StudyFileNotFoundError(FileNotFoundError):
    pass


class InvalidStudyFilePathError(ValueError):
    pass


def list_materials(
    subject,
    study_type,
    status,
    page,
    page_size,
    *,
    connect_fn,
    init_db_fn,
):
    init_db_fn()
    conditions = []
    params = {}
    if subject:
        conditions.append("subject = :subject")
        params["subject"] = subject
    if study_type:
        conditions.append("study_type = :study_type")
        params["study_type"] = study_type
    if status:
        conditions.append("status = :status")
        params["status"] = status

    where = " AND ".join(conditions) if conditions else "1=1"
    offset = (page - 1) * page_size
    if offset > MAX_OFFSET:
        raise PaginationOffsetError

    with connect_fn() as conn:
        total = conn.execute(
            f"SELECT COUNT(*) FROM study_materials WHERE {where}", params
        ).fetchone()[0]
        rows = conn.execute(
            f"""SELECT id, subject, grade, textbook, study_type, title, source_type,
                       status, score, is_correct, created_at, updated_at
                FROM study_materials
                WHERE {where}
                ORDER BY created_at DESC
                LIMIT :limit OFFSET :offset""",
            {**params, "limit": page_size, "offset": offset},
        ).fetchall()
    return {
        "items": [dict(row) for row in rows],
        "total": total,
        "page": page,
        "page_size": page_size,
    }


def get_material(material_id, *, connect_fn, init_db_fn, json_module):
    init_db_fn()
    with connect_fn() as conn:
        row = conn.execute(
            "SELECT * FROM study_materials WHERE id = ?", (material_id,)
        ).fetchone()
    if not row:
        raise MaterialNotFoundError

    result = dict(row)
    for field in ("formats_json", "mistake_tags", "tags_json", "lessons_json"):
        try:
            result[field] = json_module.loads(result[field])
        except (json_module.JSONDecodeError, TypeError):
            result[field] = {}
    return result


def create_material(req, *, connect_fn, init_db_fn, uuid_fn):
    init_db_fn()
    material_id = f"study-{uuid_fn().hex[:12]}"
    with connect_fn() as conn:
        conn.execute(
            """INSERT INTO study_materials
               (id, subject, grade, textbook, study_type, title, source_type, raw_content, status)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'draft')""",
            (
                material_id,
                req.subject,
                req.grade,
                req.textbook,
                req.study_type,
                req.title or "未命名",
                req.source_type,
                req.raw_content,
            ),
        )
    return {"material_id": material_id, "status": "draft"}


def update_material(material_id, req, *, connect_fn, init_db_fn):
    init_db_fn()
    updates = {}
    for field in (
        "title",
        "subject",
        "grade",
        "textbook",
        "study_type",
        "score",
        "is_correct",
        "status",
    ):
        value = getattr(req, field, None)
        if value is not None:
            updates[field] = value
    if not updates:
        return {"updated": material_id, "fields": []}

    updates.pop("updated_at", None)
    set_clause = ", ".join(f"{key} = :{key}" for key in updates)
    params = dict(updates)
    with connect_fn() as conn:
        conn.execute(
            f"UPDATE study_materials SET {set_clause}, updated_at = datetime('now') WHERE id = :id",
            {**params, "id": material_id},
        )
    return {"updated": material_id, "fields": list(updates.keys())}


def delete_material(material_id, *, connect_fn, init_db_fn):
    init_db_fn()
    with connect_fn() as conn:
        conn.execute("DELETE FROM study_materials WHERE id = ?", (material_id,))
    return {"deleted": material_id}


def generate_material(
    material_id,
    req,
    *,
    connect_fn,
    init_db_fn,
    generate_lecture_notes_fn,
    logger,
):
    init_db_fn()
    with connect_fn() as conn:
        row = conn.execute(
            "SELECT subject, study_type, raw_content FROM study_materials WHERE id = ?",
            (material_id,),
        ).fetchone()
    if not row:
        raise MaterialNotFoundError
    try:
        return generate_lecture_notes_fn(
            material_id=material_id,
            subject=row["subject"],
            study_type=row["study_type"],
            raw_content=row["raw_content"],
            extra_instructions=req.extra_instructions,
        )
    except Exception as exc:
        logger.exception("生成讲题稿失败: %s", material_id)
        raise MaterialGenerationError(str(exc)) from exc


def review_mistake(
    material_id,
    req,
    *,
    connect_fn,
    init_db_fn,
    generate_mistake_review_fn,
    normalize_review_result_fn,
    json_module,
    logger,
):
    init_db_fn()
    with connect_fn() as conn:
        row = conn.execute(
            "SELECT raw_content FROM study_materials WHERE id = ?", (material_id,)
        ).fetchone()
    if not row:
        raise MaterialNotFoundError
    try:
        result = normalize_review_result_fn(
            generate_mistake_review_fn(
                material_id=material_id,
                raw_content=row["raw_content"],
                correct_answer=req.correct_answer,
                child_answer=req.child_answer,
            )
        )
        with connect_fn() as conn:
            conn.execute(
                """UPDATE study_materials
                   SET status = 'reviewed', is_correct = ?, score = COALESCE(?, score),
                       mistake_tags = ?, updated_at = datetime('now')
                   WHERE id = ?""",
                (
                    result["is_correct"],
                    result.get("score"),
                    json_module.dumps(result["mistake_tags"], ensure_ascii=False),
                    material_id,
                ),
            )
        return result
    except Exception as exc:
        logger.exception("错题复盘失败: %s", material_id)
        raise MistakeReviewError(str(exc)) from exc


def get_study_file(
    material_id,
    fmt,
    *,
    connect_fn,
    study_data_dir,
    resolve_under_fn,
    file_response_type,
    path_security_error_type,
    path_type,
):
    try:
        material_dir = resolve_under_fn(study_data_dir, material_id, expected="dir")
    except path_security_error_type:
        raise StudyFileNotFoundError("资料文件不存在") from None
    file_map = {
        "md": "讲题稿版.md",
        "html": "讲题稿打印版.html",
        "pdf": "讲题稿版.pdf",
        "original": None,
    }
    if fmt == "original":
        with connect_fn() as conn:
            row = conn.execute(
                "SELECT raw_content FROM study_materials WHERE id = ?", (material_id,)
            ).fetchone()
        if not row or not row["raw_content"]:
            raise StudyFileNotFoundError("原始文件不存在")
        stored = path_type(row["raw_content"])
        if (
            stored.is_absolute()
            or not stored.parts
            or stored.parts[0] != study_data_dir.name
        ):
            raise InvalidStudyFilePathError
        try:
            original = resolve_under_fn(
                study_data_dir, *stored.parts[1:], expected="file"
            )
        except path_security_error_type:
            raise StudyFileNotFoundError("原始文件已丢失") from None
        return file_response_type(original)
    try:
        path = resolve_under_fn(material_dir, file_map[fmt], expected="file")
    except path_security_error_type:
        raise StudyFileNotFoundError("文件尚未生成") from None
    return file_response_type(path)


def list_mistakes(subject, page, page_size, *, connect_fn, init_db_fn, json_module):
    init_db_fn()
    conditions = ["is_correct = 0"]
    params = {}
    if subject:
        conditions.append("subject = :subject")
        params["subject"] = subject
    where = " AND ".join(conditions)
    offset = (page - 1) * page_size
    if offset > MAX_OFFSET:
        raise PaginationOffsetError

    with connect_fn() as conn:
        total = conn.execute(
            f"SELECT COUNT(*) FROM study_materials WHERE {where}", params
        ).fetchone()[0]
        rows = conn.execute(
            f"""SELECT id, subject, grade, study_type, title, score,
                       mistake_tags, created_at
                FROM study_materials
                WHERE {where}
                ORDER BY created_at DESC
                LIMIT :limit OFFSET :offset""",
            {**params, "limit": page_size, "offset": offset},
        ).fetchall()

    items = []
    for row in rows:
        item = dict(row)
        try:
            item["mistake_tags"] = json_module.loads(item["mistake_tags"])
        except Exception:
            item["mistake_tags"] = []
        items.append(item)
    return {"items": items, "total": total, "page": page}


def get_stats(*, connect_fn, init_db_fn):
    init_db_fn()
    with connect_fn() as conn:
        rows = conn.execute(
            """SELECT subject,
                      COUNT(*) as total,
                      SUM(CASE WHEN is_correct = 1 THEN 1 ELSE 0 END) as correct,
                      SUM(CASE WHEN is_correct = 0 THEN 1 ELSE 0 END) as wrong,
                      SUM(CASE WHEN status = 'draft' THEN 1 ELSE 0 END) as drafts
               FROM study_materials
               GROUP BY subject
               ORDER BY total DESC"""
        ).fetchall()
    return {"by_subject": [dict(row) for row in rows]}
