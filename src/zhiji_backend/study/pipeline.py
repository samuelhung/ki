from __future__ import annotations

import json
import re

from ..ai_client import chat
from ..db import connect


def _parse_json_object(content: str) -> dict:
    text = (content or "").strip()
    fenced = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.S)
    candidate = fenced.group(1) if fenced else text
    try:
        value = json.loads(candidate)
        return value if isinstance(value, dict) else {}
    except json.JSONDecodeError:
        start, end = candidate.find("{"), candidate.rfind("}")
        if start >= 0 and end > start:
            try:
                value = json.loads(candidate[start:end + 1])
                return value if isinstance(value, dict) else {}
            except json.JSONDecodeError:
                pass
    return {}


def generate_mistake_review(*, material_id: str, raw_content: str, correct_answer: str, child_answer: str) -> dict:
    content = chat(
        [
            {"role": "system", "content": "你是小学学习复盘助手。只返回 JSON，不要 Markdown。字段: is_correct(0或1), score(0-100), mistake_tags(最多3个短标签), review_content(清晰解释错误原因、正确思路和一道迁移提示)。"},
            {"role": "user", "content": f"题目:\n{raw_content}\n\n孩子答案:\n{child_answer}\n\n正确答案:\n{correct_answer}"},
        ],
        temperature=0.2,
        max_tokens=1800,
        response_format={"type": "json_object"},
        module="study",
        task="mistake_review",
    )
    if not content:
        raise RuntimeError("AI 错题复盘未返回内容，请检查 AI 配置")
    result = _parse_json_object(content)
    if not result:
        result = {"is_correct": 0, "score": 0, "mistake_tags": ["待复核"], "review_content": content}
    result["material_id"] = material_id
    return result


def generate_lecture_notes(*, material_id: str, subject: str, study_type: str, raw_content: str, extra_instructions: str = "") -> dict:
    content = chat(
        [
            {"role": "system", "content": "你是小学辅导老师。输出一份结构清晰的 Markdown 讲题稿，先给孩子版简明步骤，再给家长版讲解、易错点与迁移练习。"},
            {"role": "user", "content": f"学科: {subject}\n类型: {study_type}\n材料:\n{raw_content}\n\n额外要求: {extra_instructions or '无'}"},
        ],
        temperature=0.3,
        max_tokens=5000,
        module="study",
        task="lecture_notes",
    )
    if not content:
        raise RuntimeError("AI 讲题稿未返回内容，请检查 AI 配置")
    child_version = content
    parent_version = content
    with connect() as conn:
        conn.execute(
            """UPDATE study_materials
               SET child_version = ?, parent_version = ?, status = 'ready', updated_at = datetime('now')
               WHERE id = ?""",
            (child_version, parent_version, material_id),
        )
    return {"material_id": material_id, "status": "ready", "child_version": child_version, "parent_version": parent_version}
