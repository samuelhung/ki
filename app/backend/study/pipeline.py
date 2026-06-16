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
    TEXTBOOK_SYSTEM, TEXTBOOK_USER,
    TEXTBOOK_LESSON_ID_SYSTEM, TEXTBOOK_LESSON_ID_USER,
    TEXTBOOK_LESSON_USER,
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


# ── 教材分课解析 ──

def _generate_textbook_lessons(
    material_id: str,
    raw_content: str,
    extra_instructions: str = "",
) -> dict:
    """教材管线：提取 PDF 文本 → AI 分课 → 逐课解析 → 存 lessons_json"""
    from ..ingest.pdf_ocr import process_pdf

    # 1. 提取文本
    pdf_path = STUDY_DATA_DIR.parent / raw_content  # data/study/{id}/raw/original.pdf
    if not pdf_path.exists():
        raise RuntimeError(f"教材 PDF 不存在: {pdf_path}")

    logger.info("教材分课解析: 提取 PDF 文本 %s", pdf_path)
    ocr_result = process_pdf(pdf_path)
    textbook_text = ocr_result.get("text", "")
    if not textbook_text.strip():
        raise RuntimeError("PDF 未能提取到文字，可能为纯扫描版")

    # 2. AI 识别课程（输出文本列表，非 JSON）
    logger.info("教材分课解析: AI 识别课程（全文 %d 字）", len(textbook_text))
    lesson_messages = [
        {"role": "system", "content": TEXTBOOK_LESSON_ID_SYSTEM},
        {"role": "user", "content": TEXTBOOK_LESSON_ID_USER.format(
            textbook_text=textbook_text[:5000]  # 只看前 5000 字目录区
        )},
    ]
    lesson_list_text = chat(
        lesson_messages,
        temperature=0.1,
        max_tokens=2048,
        timeout=120,
        module="study",
        task="study_textbook_identify",
    )
    if not lesson_list_text:
        raise RuntimeError("AI 识别课程失败：空响应")

    # 解析文本课程列表: "序号 | 课题名 | 起始标记"
    lesson_markers = _parse_lesson_list(lesson_list_text)

    if not lesson_markers:
        raise RuntimeError("AI 未能识别出任何课程")

    logger.info("教材分课解析: 识别到 %d 课", len(lesson_markers))

    # 用起始标记在原文中切分课程内容
    lessons = _split_textbook(textbook_text, lesson_markers)

    # 3. 逐课生成解析
    lesson_results = []
    for lesson in lessons:
        lesson_num = lesson["lesson_num"]
        lesson_title = lesson["title"]
        lesson_content = lesson["content"]

        if len(lesson_content) < 20:
            continue

        logger.info("教材分课解析: 解析第%d课「%s」（%d 字）", lesson_num, lesson_title, len(lesson_content))

        analysis_messages = [
            {"role": "system", "content": TEXTBOOK_SYSTEM},
            {"role": "user", "content": TEXTBOOK_LESSON_USER.format(
                lesson_num=lesson_num,
                lesson_title=lesson_title,
                lesson_content=lesson_content,
            )},
        ]
        analysis_md = chat(
            analysis_messages,
            temperature=0.3,
            max_tokens=8192,
            timeout=300,
            module="study",
            task="study_textbook_lesson",
        )
        if not analysis_md:
            logger.warning("第%d课「%s」解析生成失败: 空响应", lesson_num, lesson_title)
            analysis_md = f"## 第{lesson_num}课：{lesson_title}\n\n（AI 解析生成失败）"

        lesson_results.append({
            "lesson_num": lesson_num,
            "title": lesson_title,
            "content": lesson_content,
            "analysis_md": analysis_md,
        })

    # 4. 汇总 MD（全部课程解析拼接）
    # 获取教材原标题
    with connect() as conn:
        row = conn.execute("SELECT title FROM study_materials WHERE id = ?", (material_id,)).fetchone()
        textbook_title = row["title"] if row else ""
    combined_md = _build_textbook_md(lesson_results, textbook_title)

    # 5. 写 MD / HTML / PDF
    md_dir = STUDY_DATA_DIR / material_id
    md_dir.mkdir(parents=True, exist_ok=True)

    md_path = md_dir / "讲题稿版.md"
    md_path.write_text(combined_md, encoding="utf-8")

    title = _extract_suggested_title(combined_md) or _first_line(combined_md) or material_id
    subject = _get_material_subject(material_id) or "语文"

    html = render_html(subject, title, _md_to_html_body(combined_md))
    html_path = md_dir / "讲题稿打印版.html"
    html_path.write_text(html, encoding="utf-8")

    pdf_path = md_dir / "讲题稿版.pdf"
    _html_to_pdf(html_path, pdf_path)

    # 6. 回写 DB
    formats = {
        "md": str(md_path),
        "html": str(html_path),
        "pdf": str(pdf_path),
    }

    with connect() as conn:
        conn.execute(
            """UPDATE study_materials
               SET parent_version = ?,
                   formats_json = ?, lessons_json = ?,
                   title = ?, status = 'ready',
                   updated_at = datetime('now')
               WHERE id = ?""",
            (combined_md,
             json.dumps(formats, ensure_ascii=False),
             json.dumps(lesson_results, ensure_ascii=False),
             title, material_id),
        )

    return {
        "material_id": material_id,
        "status": "ready",
        "formats": formats,
        "title": title,
        "lessons": lesson_results,
    }


def _parse_lesson_list(text: str) -> list[dict]:
    """解析 AI 返回的课程列表: '序号. 课题名'"""
    markers = []
    for line in text.strip().split("\n"):
        line = line.strip()
        if not line or line.startswith("#") or line.startswith("```"):
            continue
        # 匹配 "1. 课题名" 或 "1、课题名" 或 "1 课题名"
        m = re.match(r'^(\d+)[.\s、]+\s*(.+)$', line)
        if m:
            try:
                num = int(m.group(1))
                title = m.group(2).strip()
                markers.append({"lesson_num": num, "title": title, "marker": title})
            except ValueError:
                continue
    return markers


def _split_textbook(full_text: str, markers: list[dict]) -> list[dict]:
    """按目录页码切分：解析 TOC 页码 → 按页归并课文内容"""
    # 1. 解析全文中的「--- 第 X 页 ---」标记
    page_pattern = re.compile(r'--- 第 (\d+) 页 ---')
    page_splits = list(page_pattern.finditer(full_text))

    if not page_splits:
        logger.warning("未找到页码标记，回退标题定位")
        return _split_textbook_by_title(full_text, markers)

    # 构建页码→内容映射
    page_contents: dict[int, str] = {}
    for i, match in enumerate(page_splits):
        page_num = int(match.group(1))
        start = match.end()
        end = page_splits[i + 1].start() if i + 1 < len(page_splits) else len(full_text)
        page_contents[page_num] = full_text[start:end].strip()

    logger.info("解析到 %d 页内容", len(page_contents))

    # 2. 从目录页提取每课的起始页码
    lesson_pages = _parse_toc_pages(full_text, markers)

    if not lesson_pages:
        logger.warning("无法从目录提取页码，回退标题定位")
        return _split_textbook_by_title(full_text, markers)

    # 3. 按页码归并课文内容
    lessons = []
    sorted_lessons = sorted(lesson_pages, key=lambda x: x["lesson_num"])

    for i, lesson in enumerate(sorted_lessons):
        start_page = lesson["start_page"]
        # 确定结束页码（下一课的起始页-1，或最后一页）
        if i + 1 < len(sorted_lessons):
            end_page = sorted_lessons[i + 1]["start_page"] - 1
        else:
            end_page = max(page_contents.keys()) if page_contents else start_page

        # 归并页码范围
        content_parts = []
        for pg in range(start_page, end_page + 1):
            if pg in page_contents:
                content_parts.append(page_contents[pg])

        content = "\n".join(content_parts).strip()
        if len(content) >= 50:
            lessons.append({
                "lesson_num": lesson["lesson_num"],
                "title": lesson["title"],
                "content": content,
            })
        else:
            logger.warning("第%d课「%s」内容过短(%d字)", lesson["lesson_num"], lesson["title"], len(content))

    return lessons


def _parse_toc_pages(text: str, markers: list[dict]) -> list[dict]:
    """从目录中提取每课的页码。
    目录格式: '1 课题名.........................2' (序号 课题名 ... 页码)
    用 AI 返回的课题名做锚点，在目录区匹配页码。
    """
    # 构建标题→序号映射
    title_to_num: dict[str, int] = {}
    for m in markers:
        title_to_num[m["title"]] = m["lesson_num"]

    lesson_pages = []
    for title, lesson_num in title_to_num.items():
        escaped = re.escape(title)
        # 匹配: [序号] [可选的*] 课题名[可选的（节选）等] ...点... 页码
        # 支持 "4* 三月桃花水" 和 "19 小英雄雨来（节选）"
        pattern = re.compile(
            r'(?:^|\n)\s*\d+\*?\s*' + escaped + r'(?:（[^）]*）)?[\s.]*?(\d+)\s*$',
            re.MULTILINE
        )
        m = pattern.search(text)
        if m:
            page = int(m.group(1))
            lesson_pages.append({
                "lesson_num": lesson_num,
                "title": title,
                "start_page": page,
            })
        else:
            # 再试更宽松的匹配：只搜课题名后跟数字
            pattern2 = re.compile(
                escaped + r'.*?(\d{1,3})\s*$',
                re.MULTILINE
            )
            m2 = pattern2.search(text)
            if m2:
                page = int(m2.group(1))
                lesson_pages.append({
                    "lesson_num": lesson_num,
                    "title": title,
                    "start_page": page,
                })
            else:
                logger.warning("目录中未找到「%s」的页码", title)

    return lesson_pages


def _split_textbook_by_title(full_text: str, markers: list[dict]) -> list[dict]:
    """回退方案：用课题名在文中定位切分"""
    lessons = []
    for i, m in enumerate(markers):
        pos = full_text.find(m["title"])
        if pos == -1:
            continue
        if i + 1 < len(markers):
            next_pos = full_text.find(markers[i + 1]["title"], pos + 1)
            if next_pos == -1:
                next_pos = len(full_text)
        else:
            next_pos = len(full_text)
        content = full_text[pos:next_pos].strip()
        if len(content) >= 20:
            lessons.append({
                "lesson_num": m["lesson_num"],
                "title": m["title"],
                "content": content,
            })
    return lessons


def _clean_json(text: str) -> str:
    """清理 AI 输出的 JSON（去掉 markdown 代码块包裹）"""
    text = text.strip()
    if text.startswith("```"):
        lines = text.split("\n")
        # 去掉首尾 ``` 行
        if lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].startswith("```"):
            lines = lines[:-1]
        text = "\n".join(lines)
    return text.strip()


def _build_textbook_md(lessons: list, title: str = "") -> str:
    """将课程解析列表拼接为完整 MD"""
    heading = f"# {title}\n" if title else "# 教材解读\n"
    parts = [heading]
    for lesson in lessons:
        parts.append(f"\n<!--PAGEBREAK-->\n\n{lesson['analysis_md']}")
    return "\n".join(parts)


# ── 讲题稿生成 ──

def generate_lecture_notes(
    material_id: str,
    subject: str,
    study_type: str,
    raw_content: str,
    extra_instructions: str = "",
    child_answer: str = "",
) -> dict:
    """生成讲稿，返回 md/html/pdf 路径"""

    # ── 选 prompt ──
    is_textbook = study_type == "教材/课本"

    if is_textbook:
        return _generate_textbook_lessons(material_id, raw_content, extra_instructions)
    elif subject == "数学":
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

    with connect() as conn:
        conn.execute(
            """UPDATE study_materials
               SET parent_version = ?,
                   formats_json = ?, title = ?, status = 'ready',
                   updated_at = datetime('now')
               WHERE id = ?""",
            (md_content, json.dumps(formats, ensure_ascii=False),
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
        # 分页标记
        elif stripped == "<!--PAGEBREAK-->":
            _close_lists(result, in_list, in_ordered)
            in_list = in_ordered = False
            result.append('<div style="page-break-before: always;"></div>')
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
