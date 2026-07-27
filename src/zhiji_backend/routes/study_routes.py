"""辅导中心 API — CRUD + 生成 + 文件服务"""

from __future__ import annotations

import json
import logging
import uuid
from pathlib import Path
from typing import Literal

from fastapi import APIRouter, File, Form, Query, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel

from .. import study_intake_service as _intake
from .. import study_material_service as _material
from ..db import connect, init_db
from ..ingest import pdf_ocr
from ..paths import STUDY_DATA_DIR
from ..security.constraints import MAX_PAGE_SIZE, SafeIdentifier
from ..security.file_intake import (
    OCR_PDF_MAX_BYTES,
    FileKind,
    kind_for_filename,
    max_bytes_for_kind,
    stream_upload_to_temp,
    validate_file,
)
from ..security.paths import PathSecurityError, resolve_under
from ..study import pipeline

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/study", tags=["study"])

STUDY_DATA_DIR.mkdir(parents=True, exist_ok=True)


class StudyCreateRequest(BaseModel):
    subject: str
    study_type: str
    title: str = ""
    raw_content: str = ""
    grade: str = ""
    textbook: str = ""
    source_type: str = "manual"


class StudyUpdateRequest(BaseModel):
    title: str | None = None
    subject: str | None = None
    grade: str | None = None
    textbook: str | None = None
    study_type: str | None = None
    score: int | None = None
    is_correct: int | None = None
    status: str | None = None


class GenerateRequest(BaseModel):
    extra_instructions: str = ""


class MistakeReviewRequest(BaseModel):
    correct_answer: str
    child_answer: str


def _normalize_review_result(result) -> dict:
    data = (
        dict(result)
        if isinstance(result, dict)
        else {"review_content": str(result or "")}
    )
    data["status"] = "reviewed"
    data["is_correct"] = int(data.get("is_correct", 0))
    if not isinstance(data.get("mistake_tags"), list):
        data["mistake_tags"] = []
    return data


@router.get("/list")
def list_materials(
    subject: str = Query(""),
    study_type: str = Query(""),
    status: str = Query(""),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=MAX_PAGE_SIZE),
):
    """列出学习资料，支持按学科/题型/状态筛选"""
    return _material.list_materials(
        subject,
        study_type,
        status,
        page,
        page_size,
        connect_fn=connect,
        init_db_fn=init_db,
    )


@router.post("/create")
def create_material(req: StudyCreateRequest):
    """提交学习资料（手动录入或文件上传后调用）"""
    return _material.create_material(
        req, connect_fn=connect, init_db_fn=init_db, uuid_fn=uuid.uuid4
    )


@router.put("/{material_id}")
def update_material(material_id: SafeIdentifier, req: StudyUpdateRequest):
    """更新学习资料（批改、标注对错等）"""
    return _material.update_material(
        material_id, req, connect_fn=connect, init_db_fn=init_db
    )


@router.delete("/{material_id}")
def delete_material(material_id: SafeIdentifier):
    """删除学习资料"""
    return _material.delete_material(
        material_id, connect_fn=connect, init_db_fn=init_db
    )


@router.post("/upload")
def upload_and_ocr(
    file: UploadFile = File(...),
    category: str = Form(""),
    subject: str = Form(""),
    study_type: str = Form(""),
    grade: str = Form(""),
    title: str = Form(""),
):
    """上传 PDF/图片。教材类保留原文件；其他类型 OCR 提取文字。"""
    return _intake.upload_and_ocr(
        file,
        category,
        subject,
        study_type,
        grade,
        title,
        kind_for_filename_fn=kind_for_filename,
        max_bytes_for_kind_fn=max_bytes_for_kind,
        stream_upload_to_temp_fn=stream_upload_to_temp,
        validate_file_fn=validate_file,
        resolve_under_fn=resolve_under,
        connect_fn=connect,
        init_db_fn=init_db,
        uuid_fn=uuid.uuid4,
        process_pdf_fn=pdf_ocr.process_pdf,
        ocr_page_fn=pdf_ocr.ocr_page,
        study_data_dir=STUDY_DATA_DIR,
        ocr_pdf_max_bytes=OCR_PDF_MAX_BYTES,
        file_kind_type=FileKind,
    )


@router.post("/{material_id}/generate")
def generate_material(
    material_id: SafeIdentifier, req: GenerateRequest = GenerateRequest()
):
    """AI 生成讲题稿（同步执行）"""
    return _material.generate_material(
        material_id,
        req,
        connect_fn=connect,
        init_db_fn=init_db,
        generate_lecture_notes_fn=pipeline.generate_lecture_notes,
        logger=logger,
    )


@router.post("/{material_id}/review")
def review_mistake(material_id: SafeIdentifier, req: MistakeReviewRequest):
    """生成错题复盘讲义"""
    return _material.review_mistake(
        material_id,
        req,
        connect_fn=connect,
        init_db_fn=init_db,
        generate_mistake_review_fn=pipeline.generate_mistake_review,
        normalize_review_result_fn=_normalize_review_result,
        json_module=json,
        logger=logger,
    )


@router.get("/{material_id}/file/{fmt}")
def get_study_file(
    material_id: SafeIdentifier,
    fmt: Literal["md", "html", "pdf", "original"],
):
    """返回讲题稿文件（md/html/pdf）"""
    return _material.get_study_file(
        material_id,
        fmt,
        connect_fn=connect,
        study_data_dir=STUDY_DATA_DIR,
        resolve_under_fn=resolve_under,
        file_response_type=FileResponse,
        path_security_error_type=PathSecurityError,
        path_type=Path,
    )


@router.post("/upload-image")
def upload_image(
    file: UploadFile = File(...),
    subject: str = Form("语文"),
    study_type: str = Form("阅读理解"),
    grade: str = Form(""),
):
    """上传题目图片 → OCR → 创建学习资料"""
    ocr_image_fn = _ocr_image_path
    try:
        return _intake.upload_image(
            file,
            subject,
            study_type,
            grade,
            kind_for_filename_fn=kind_for_filename,
            max_bytes_for_kind_fn=max_bytes_for_kind,
            stream_upload_to_temp_fn=stream_upload_to_temp,
            validate_file_fn=validate_file,
            ocr_image_fn=ocr_image_fn,
            create_material_fn=create_material,
            file_kind_type=FileKind,
        )
    finally:
        if not callable(_ocr_image_path):
            globals()["_ocr_image_path"] = _ocr_image_path_adapter


def _ocr_image_path(path: Path) -> str:
    return _intake._ocr_image_path(path, ocr_page_fn=pdf_ocr.ocr_page)


_ocr_image_path_adapter = _ocr_image_path


@router.get("/mistakes/list")
def list_mistakes(
    subject: str = Query(""),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=MAX_PAGE_SIZE),
):
    """列出错题（is_correct = 0）"""
    return _material.list_mistakes(
        subject,
        page,
        page_size,
        connect_fn=connect,
        init_db_fn=init_db,
        json_module=json,
    )


@router.get("/stats")
def get_stats():
    """各科统计 + 正确率"""
    return _material.get_stats(connect_fn=connect, init_db_fn=init_db)


@router.get("/{material_id}")
def get_material(material_id: SafeIdentifier):
    """获取学习资料完整详情（含孩子版/家长版/格式）"""
    return _material.get_material(
        material_id, connect_fn=connect, init_db_fn=init_db, json_module=json
    )
