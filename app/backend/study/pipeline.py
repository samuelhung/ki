"""辅导中心 — 讲题稿生成管线"""

from __future__ import annotations

import json
import logging
import re
import subprocess
from pathlib import Path

from ..deepseek_client import chat
from ..db import connect
from .prompts import (
    ENGLISH_SYSTEM, ENGLISH_USER,
    MATH_SYSTEM, MATH_USER,
    MISTAKE_SYSTEM, MISTAKE_USER,
    READING_CHINESE_SYSTEM, READING_CHINESE_USER,
    TITLE_PROMPT_SECTION,
)
from .templates import render_html

logger = logging.getLogger(__name__)

STUDY_DATA_DIR = Path(__file__).resolve().parents[3] / "data" / "study"
STUDY_DATA_DIR.mkdir(parents=True, exist_ok=True)

CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"


# ── OCR ──

def ocr_image(image_path: Path) -> str:
    """使用 macOS Vision 框架对图片 OCR"""
    import tempfile
    resized = Path(tempfile.mktemp(suffix=".png"))
    subprocess.run(
        ["sips", "-Z", "1200", str(image_path), "--out", str(resized)],
        check=True, capture_output=True,
    )

    ocr_script = Path(
        "/Users/mrh/.hermes/skills/study/study-orchestrator/scripts/ocr_vision.swift"
    )
    if not ocr_script.exists():
        logger.warning("OCR 脚本不存在: %s", ocr_script)
        resized.unlink(missing_ok=True)
        return ""

    result = subprocess.run(
        ["swift", str(ocr_script), str(resized)],
        capture_output=True, text=True, timeout=60,
    )
    resized.unlink(missing_ok=True)
    return result.stdout.strip()


# ── 讲题稿生成 ──

def generate_lecture_notes(
    material_id: str,
    subject: str,
    study_type: str,
    raw_content: str,
    extra_instructions: str = "",
    child_answer: str = "",
) -> dict:
    """生成讲题稿（孩子版 + 家长版），返回 md/html/pdf 路径"""

    # ── 选 prompt ──
    if subject == "数学":
        system = MATH_SYSTEM
        user_template = MATH_USER
    elif subject == "英语":
        system = ENGLISH_SYSTEM
        user_template = ENGLISH_USER
    else:
        system = READING_CHINESE_SYSTEM
        user_template = READING_CHINESE_USER

    # ── 孩子错答补充 ──
    child_section = ""
    if child_answer:
        child_section = f"""
#### 孩子作答情况
（孩子原答：{child_answer}）
- 对错程度判断
- 真正问题在哪
- 错因归类（回文定位不准 / 审题对象抓错 / 信息提取不完整 / 概括不准 / 表达不规范）
- 订正引导
"""

    # ── 标题生成提示 ──
    title_section = TITLE_PROMPT_SECTION

    user = user_template.format(
        raw_content=raw_content,
        extra_instructions=extra_instructions,
        child_answer_section=child_section,
        need_title_section=title_section,
    )

    messages = [
        {"role": "system", "content": system},
        {"role": "user", "content": user},
    ]

    # Map to config_manager task names
    task_key = f"{subject}_{study_type}"

    md_content = chat(
        messages,
        temperature=0.3,
        max_tokens=16384,
        timeout=300,
        module="study",
        task=task_key,
    )

    if not md_content:
        raise RuntimeError("AI 生成讲题稿失败：空响应")

    # ── 写 MD ──
    md_dir = STUDY_DATA_DIR / material_id
    md_dir.mkdir(parents=True, exist_ok=True)

    md_path = md_dir / "讲题稿版.md"
    md_path.write_text(md_content, encoding="utf-8")

    # ── 提取标题 ──
    title = _extract_suggested_title(md_content) or _first_line(md_content) or material_id

    # ── 生成 HTML ──
    html = render_html(subject, title, _md_to_html_body(md_content))
    html_path = md_dir / "讲题稿打印版.html"
    html_path.write_text(html, encoding="utf-8")

    # ── 生成 PDF ──
    pdf_path = md_dir / "讲题稿版.pdf"
    _html_to_pdf(html_path, pdf_path)

    # ── 回写 DB ──
    formats = {
        "md": str(md_path),
        "html": str(html_path),
        "pdf": str(pdf_path),
    }

    child_version = _extract_child_version(md_content)

    with connect() as conn:
        conn.execute(
            """UPDATE study_materials
               SET child_version = ?, parent_version = ?,
                   formats_json = ?, title = ?, status = 'ready',
                   updated_at = datetime('now')
               WHERE id = ?""",
            (child_version, md_content, json.dumps(formats, ensure_ascii=False),
             title, material_id),
        )

    return {
        "material_id": material_id,
        "status": "ready",
        "formats": formats,
        "title": title,
    }


# ── 错题复盘 ──

def generate_mistake_review(
    material_id: str,
    raw_content: str,
    correct_answer: str,
    child_answer: str,
) -> dict:
    """生成错题复盘讲义"""
    user = MISTAKE_USER.format(
        raw_content=raw_content,
        correct_answer=correct_answer,
        child_answer=child_answer,
    )

    messages = [
        {"role": "system", "content": MISTAKE_SYSTEM},
        {"role": "user", "content": user},
    ]

    md_content = chat(
        messages,
        temperature=0.3,
        max_tokens=4096,
        timeout=180,
        module="study",
        task="study_mistake_review",
    )

    if not md_content:
        raise RuntimeError("AI 生成错题复盘失败")

    md_dir = STUDY_DATA_DIR / material_id
    md_dir.mkdir(parents=True, exist_ok=True)

    existing_path = md_dir / "讲题稿版.md"
    if existing_path.exists():
        existing = existing_path.read_text(encoding="utf-8")
        combined = existing + "\n\n---\n\n## 错题复盘\n\n" + md_content
    else:
        combined = md_content
    existing_path.write_text(combined, encoding="utf-8")

    subject = _get_material_subject(material_id)

    with connect() as conn:
        row = conn.execute(
            "SELECT title FROM study_materials WHERE id = ?", (material_id,)
        ).fetchone()
        title = row["title"] if row else material_id

    html = render_html(subject or "语文", title, _md_to_html_body(combined))
    html_path = md_dir / "讲题稿打印版.html"
    html_path.write_text(html, encoding="utf-8")

    pdf_path = md_dir / "讲题稿版.pdf"
    _html_to_pdf(html_path, pdf_path)

    formats = {
        "md": str(existing_path),
        "html": str(html_path),
        "pdf": str(pdf_path),
    }

    with connect() as conn:
        conn.execute(
            """UPDATE study_materials
               SET parent_version = ?, formats_json = ?,
                   updated_at = datetime('now')
               WHERE id = ?""",
            (combined, json.dumps(formats, ensure_ascii=False), material_id),
        )

    return {"material_id": material_id, "formats": formats}


# ── Helpers ──

def _md_to_html_body(md: str) -> str:
    """极简 Markdown→HTML 转换"""
    lines = md.split("\n")
    result = []
    in_list = False
    in_ordered = False

    for line in lines:
        stripped = line.strip()

        # 标题
        if stripped.startswith("#### "):
            _close_lists(result, in_list, in_ordered)
            in_list = in_ordered = False
            result.append(f"<h4>{_fmt(stripped[5:])}</h4>")
        elif stripped.startswith("### "):
            _close_lists(result, in_list, in_ordered)
            in_list = in_ordered = False
            result.append(f"<h3>{_fmt(stripped[4:])}</h3>")
        elif stripped.startswith("## "):
            _close_lists(result, in_list, in_ordered)
            in_list = in_ordered = False
            result.append(f"<h2>{_fmt(stripped[3:])}</h2>")
        elif stripped.startswith("# "):
            _close_lists(result, in_list, in_ordered)
            in_list = in_ordered = False
            result.append(f"<h1>{_fmt(stripped[2:])}</h1>")
        # 有序列表
        elif re.match(r"^\d+\.\s", stripped):
            content = _fmt(re.sub(r"^\d+\.\s", "", stripped))
            if not in_ordered:
                _close_lists(result, in_list, in_ordered)
                result.append("<ol>")
                in_ordered = True
            result.append(f"<li>{content}</li>")
        # 无序列表
        elif stripped.startswith("- "):
            content = _fmt(stripped[2:])
            if not in_list:
                _close_lists(result, in_list, in_ordered)
                result.append("<ul>")
                in_list = True
            result.append(f"<li>{content}</li>")
        # 空行
        elif not stripped:
            _close_lists(result, in_list, in_ordered)
            in_list = in_ordered = False
        # 正文
        else:
            _close_lists(result, in_list, in_ordered)
            in_list = in_ordered = False
            result.append(f"<p>{_fmt(stripped)}</p>")

    _close_lists(result, in_list, in_ordered)
    return "\n".join(result)


def _close_lists(result: list, in_list: bool, in_ordered: bool) -> None:
    if in_ordered:
        result.append("</ol>")
    elif in_list:
        result.append("</ul>")


def _fmt(text: str) -> str:
    """加粗处理"""
    return re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", text)


def _html_to_pdf(html_path: Path, pdf_path: Path):
    """Chrome headless 生成 PDF"""
    try:
        subprocess.run(
            [
                CHROME,
                "--headless", "--disable-gpu", "--no-sandbox",
                f"--print-to-pdf={pdf_path}",
                f"file://{html_path.resolve()}",
            ],
            check=True,
            timeout=60,
            capture_output=True,
        )
    except FileNotFoundError:
        logger.warning("Chrome not found at %s, skipping PDF", CHROME)
    except subprocess.TimeoutExpired:
        logger.warning("PDF generation timed out for %s", pdf_path)


def _extract_child_version(md_content: str) -> str:
    """提取孩子版（去掉「家长怎么讲」和过长思路）"""
    parts = md_content.split("## ")
    child_parts = []
    for part in parts:
        if "家长怎么讲" in part or "详细解题思路" in part:
            lines = part.split("\n")
            kept = [lines[0]]
            for i, line in enumerate(lines):
                if "参考答案" in line:
                    kept.extend(lines[i:])
                    break
            child_parts.append("\n".join(kept))
        else:
            child_parts.append(part)
    return "## ".join(child_parts)


def _extract_suggested_title(md_content: str) -> str | None:
    """从 AI 生成内容中提取「建议标题」"""
    m = re.search(r"## 建议标题\s*\n+(.+?)(?:\n|$)", md_content)
    if m:
        title = m.group(1).strip()
        if title and len(title) <= 30:
            return title
    return None


def _first_line(md_content: str) -> str | None:
    """从第一行提取标题（去掉 # 前缀）"""
    line = md_content.split("\n")[0].strip()
    return re.sub(r"^#+\s*", "", line) or None


def _get_material_subject(material_id: str) -> str | None:
    with connect() as conn:
        row = conn.execute(
            "SELECT subject FROM study_materials WHERE id = ?", (material_id,)
        ).fetchone()
    return row["subject"] if row else None
