"""辅导中心 API — CRUD + 生成 + 文件服务"""

from __future__ import annotations

import json
import logging
import uuid
from pathlib import Path

from fastapi import APIRouter, File, Form, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel

from ..db import connect, init_db

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/study", tags=["study"])

STUDY_DATA_DIR = Path(__file__).resolve().parents[3] / "data" / "study"
STUDY_DATA_DIR.mkdir(parents=True, exist_ok=True)

# ── 请求模型 ──

class StudyCreateRequest(BaseModel):
    subject: str
    study_type: str
    title: str = ""
    raw_content: str = ""
    grade: str = ""
    source_type: str = "manual"

class StudyUpdateRequest(BaseModel):
    title: str | None = None
    subject: str | None = None
    grade: str | None = None
    study_type: str | None = None
    score: int | None = None
    is_correct: int | None = None
    status: str | None = None

class GenerateRequest(BaseModel):
    extra_instructions: str = ""

class MistakeReviewRequest(BaseModel):
    correct_answer: str
    child_answer: str


# ── 列表 ──

@router.get("/list")
def list_materials(
    subject: str = Query(""),
    study_type: str = Query(""),
    status: str = Query(""),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
):
    """列出学习资料，支持按学科/题型/状态筛选"""
    init_db()
    conditions = []
    params: dict = {}

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

    with connect() as conn:
        total = conn.execute(
            f"SELECT COUNT(*) FROM study_materials WHERE {where}", params
        ).fetchone()[0]

        rows = conn.execute(
            f"""SELECT id, subject, grade, study_type, title, source_type,
                       status, score, is_correct, created_at, updated_at
                FROM study_materials
                WHERE {where}
                ORDER BY created_at DESC
                LIMIT :limit OFFSET :offset""",
            {**params, "limit": page_size, "offset": offset},
        ).fetchall()

    return {
        "items": [dict(r) for r in rows],
        "total": total,
        "page": page,
        "page_size": page_size,
    }


# ── 详情 ──

@router.get("/{material_id}")
def get_material(material_id: str):
    """获取学习资料完整详情（含孩子版/家长版/格式）"""
    init_db()
    with connect() as conn:
        row = conn.execute(
            "SELECT * FROM study_materials WHERE id = ?", (material_id,)
        ).fetchone()

    if not row:
        raise HTTPException(status_code=404, detail="资料不存在")

    d = dict(row)
    for field in ("formats_json", "mistake_tags", "tags_json"):
        try:
            d[field] = json.loads(d[field])
        except (json.JSONDecodeError, TypeError):
            d[field] = {}
    return d


# ── 创建 ──

@router.post("/create")
def create_material(req: StudyCreateRequest):
    """提交学习资料（手动录入或文件上传后调用）"""
    init_db()
    material_id = f"study-{uuid.uuid4().hex[:12]}"

    with connect() as conn:
        conn.execute(
            """INSERT INTO study_materials
               (id, subject, grade, study_type, title, source_type, raw_content, status)
               VALUES (?, ?, ?, ?, ?, ?, ?, 'draft')""",
            (material_id, req.subject, req.grade, req.study_type,
             req.title or "未命名", req.source_type, req.raw_content),
        )

    return {
        "material_id": material_id,
        "status": "draft",
    }


# ── 更新 ──

@router.put("/{material_id}")
def update_material(material_id: str, req: StudyUpdateRequest):
    """更新学习资料（批改、标注对错等）"""
    init_db()
    updates = {}
    for field in ("title", "subject", "grade", "study_type", "score", "is_correct", "status"):
        val = getattr(req, field, None)
        if val is not None:
            updates[field] = val

    if not updates:
        return {"updated": material_id, "fields": []}

    updates.pop("updated_at", None)  # will use DEFAULT

    set_clause = ", ".join(
        f"{k} = :{k}" for k in updates
    )
    params = {k: v for k, v in updates.items()}

    with connect() as conn:
        conn.execute(
            f"UPDATE study_materials SET {set_clause}, updated_at = datetime('now') WHERE id = :id",
            {**params, "id": material_id},
        )

    return {"updated": material_id, "fields": list(updates.keys())}


# ── 删除 ──

@router.delete("/{material_id}")
def delete_material(material_id: str):
    """删除学习资料"""
    init_db()
    with connect() as conn:
        conn.execute("DELETE FROM study_materials WHERE id = ?", (material_id,))
    return {"deleted": material_id}


# ── AI 生成讲题稿 ──

@router.post("/{material_id}/generate")
def generate_material(material_id: str, req: GenerateRequest = GenerateRequest()):
    """AI 生成讲题稿（同步执行）"""
    init_db()
    with connect() as conn:
        row = conn.execute(
            "SELECT subject, study_type, raw_content FROM study_materials WHERE id = ?",
            (material_id,),
        ).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="资料不存在")

    try:
        from ..study.pipeline import generate_lecture_notes
        result = generate_lecture_notes(
            material_id=material_id,
            subject=row["subject"],
            study_type=row["study_type"],
            raw_content=row["raw_content"],
            extra_instructions=req.extra_instructions,
        )
        return result
    except Exception as e:
        logger.exception("生成讲题稿失败: %s", material_id)
        raise HTTPException(status_code=500, detail=str(e))


# ── 错题复盘 ──

@router.post("/{material_id}/review")
def review_mistake(material_id: str, req: MistakeReviewRequest):
    """生成错题复盘讲义"""
    init_db()
    with connect() as conn:
        row = conn.execute(
            "SELECT raw_content FROM study_materials WHERE id = ?",
            (material_id,),
        ).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="资料不存在")

    try:
        from ..study.pipeline import generate_mistake_review
        result = generate_mistake_review(
            material_id=material_id,
            raw_content=row["raw_content"],
            correct_answer=req.correct_answer,
            child_answer=req.child_answer,
        )
        return result
    except Exception as e:
        logger.exception("错题复盘失败: %s", material_id)
        raise HTTPException(status_code=500, detail=str(e))


# ── 文件下载 ──

@router.get("/{material_id}/file/{fmt}")
def get_study_file(material_id: str, fmt: str):
    """返回讲题稿文件（md/html/pdf）"""
    md_dir = STUDY_DATA_DIR / material_id
    file_map = {
        "md": "讲题稿版.md",
        "html": "讲题稿打印版.html",
        "pdf": "讲题稿版.pdf",
    }
    if fmt not in file_map:
        raise HTTPException(status_code=400, detail=f"不支持的格式: {fmt}")
    path = md_dir / file_map[fmt]
    if not path.exists():
        raise HTTPException(status_code=404, detail="文件尚未生成")
    return FileResponse(path)


# ── 图片上传 + OCR ──

@router.post("/upload")
def upload_image(
    file: UploadFile = File(...),
    subject: str = Form("语文"),
    study_type: str = Form("阅读理解"),
    grade: str = Form(""),
):
    """上传题目图片 → OCR → 创建学习资料"""
    import tempfile
    suffix = Path(file.filename or "upload.jpg").suffix
    tmp = tempfile.NamedTemporaryFile(suffix=suffix, delete=False)
    tmp.write(file.file.read())
    tmp.close()
    tmp_path = Path(tmp.name)

    try:
        from ..study.pipeline import ocr_image
        raw_content = ocr_image(tmp_path)
        if not raw_content:
            raise HTTPException(status_code=400, detail="OCR 未提取到文字，请确认图片清晰")
    finally:
        tmp_path.unlink(missing_ok=True)

    title = raw_content.split("\n")[0][:40] if raw_content else "图片题目"
    return create_material(StudyCreateRequest(
        subject=subject,
        study_type=study_type,
        title=title,
        raw_content=raw_content,
        grade=grade,
        source_type="photo",
    ))


# ── 错题本列表 ──

@router.get("/mistakes/list")
def list_mistakes(
    subject: str = Query(""),
    page: int = Query(1, ge=1),
    page_size: int = Query(50),
):
    """列出错题（is_correct = 0）"""
    init_db()
    conditions = ["is_correct = 0"]
    params: dict = {}

    if subject:
        conditions.append("subject = :subject")
        params["subject"] = subject

    where = " AND ".join(conditions)
    offset = (page - 1) * page_size

    with connect() as conn:
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
    for r in rows:
        d = dict(r)
        try:
            d["mistake_tags"] = json.loads(d["mistake_tags"])
        except Exception:
            d["mistake_tags"] = []
        items.append(d)

    return {"items": items, "total": total, "page": page}


# ── 统计 ──

@router.get("/stats")
def get_stats():
    """各科统计 + 正确率"""
    init_db()
    with connect() as conn:
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
    return {"by_subject": [dict(r) for r in rows]}
