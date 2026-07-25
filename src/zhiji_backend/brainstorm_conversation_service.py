"""Multi-turn conversation and summary workflows for brainstorm questions."""

from __future__ import annotations

import json
import logging
from collections.abc import Callable
from typing import Any

from fastapi import HTTPException

type ConnectFn = Callable[[], Any]
type MarkdownPathFn = Callable[[str], Any]
type BuildReferenceDocsFn = Callable[[list[str]], tuple[list[dict], dict[str, str]]]
type ChatFn = Callable[..., str | None]


logger = logging.getLogger("zhiji_backend.routes.brainstorm_routes")


def _append_markdown(markdown_path: Any, block: str) -> str:
    with open(markdown_path, "a", encoding="utf-8") as file:
        file.write(block)
    return markdown_path.read_text(encoding="utf-8") if markdown_path.exists() else ""


def _call_ai_chat(
    messages: list[dict],
    temperature: float = 0.3,
    max_tokens: int = 2000,
    module: str = "",
    task: str = "",
    *,
    chat_fn: ChatFn,
) -> str:
    content = chat_fn(
        messages,
        temperature=temperature,
        max_tokens=max_tokens,
        timeout=120,
        module=module,
        task=task,
    )
    if content is None:
        raise RuntimeError("AI API 未配置")
    return content


def _brainstorm_chat(
    messages: list[dict], max_tokens: int, task: str, call_ai_chat_fn: ChatFn
) -> str:
    return call_ai_chat_fn(
        messages,
        temperature=0.3,
        max_tokens=max_tokens,
        module="brainstorm",
        task=task,
    )


def _build_reference_docs(
    event_ids: list[str], *, connect_fn: ConnectFn
) -> tuple[list[dict], dict[str, str]]:
    articles: list[dict[str, object]] = []
    id_to_idx: dict[str, str] = {}
    with connect_fn() as conn:
        placeholders = ",".join(["?" for _ in event_ids])
        rows = conn.execute(
            f"SELECT id, title, title_cn, ai_summary, raw_summary FROM events WHERE id IN ({placeholders})",
            tuple(event_ids),
        ).fetchall()
    for i, row in enumerate(rows, 1):
        text = (row["ai_summary"] or "") or (row["raw_summary"] or "")
        if text.strip():
            title = row["title_cn"] or row["title"] or "未命名"
            articles.append(
                {
                    "index": i,
                    "title": title,
                    "text": text[:4000] if len(text) > 4000 else text,
                }
            )
            id_to_idx[row["id"]] = f"文档{i}"
    return articles, id_to_idx


def _build_conversation_messages(
    question_id: str,
    role_filter: bool = True,
    *,
    connect_fn: ConnectFn,
) -> list[dict]:
    with connect_fn() as conn:
        rows = conn.execute(
            "SELECT role, content FROM brainstorm_messages WHERE question_id = ? ORDER BY id ASC",
            (question_id,),
        ).fetchall()
    return [{"role": row["role"], "content": row["content"]} for row in rows]


def _parse_refs_from_answer(answer: str, id_to_idx: dict[str, str]) -> list[str]:
    ref_ids: list[str] = []
    seen: set[str] = set()
    for event_id, label in id_to_idx.items():
        if label in answer and event_id not in seen:
            ref_ids.append(event_id)
            seen.add(event_id)
    return ref_ids


def start_conversation(
    question_id: str,
    request: Any,
    *,
    connect_fn: ConnectFn,
    call_ai_chat_fn: ChatFn,
    build_reference_docs_fn: BuildReferenceDocsFn,
    parse_refs_fn: Callable[[str, dict[str, str]], list[str]],
    markdown_path_fn: MarkdownPathFn,
    now_fn: Callable[[], Any],
    logger: logging.Logger,
) -> dict[str, object]:
    if not request.event_ids:
        raise HTTPException(status_code=400, detail="至少选择一个参考文档")
    articles, id_to_idx = build_reference_docs_fn(request.event_ids)
    if not articles:
        return {"error": "所选事件没有可用的文本内容"}
    try:
        docs_text = "\n\n".join(
            f"[文档{a['index']}] 《{a['title']}》\n{a['text']}" for a in articles
        )
        system_prompt = (
            "你是严谨的研究分析助手。请基于以下参考文档回答用户问题。\n"
            "规则：\n"
            "1. 引用文档中的具体事实、数据、观点时，在对应句子末尾标注 [文档N]\n"
            "2. 概念性问题（如'XX是什么意思'）用通用知识回答，不强制引用文档\n"
            "3. 回答结构化、有深度，不要简单罗列\n\n"
            "参考文档：\n"
            f"{docs_text}"
        )
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": request.question},
        ]
        answer = _brainstorm_chat(messages, 2000, "answer", call_ai_chat_fn)
    except Exception as error:
        logger.warning(
            "Conversation start failed for question %s: %s", question_id, error
        )
        return {"error": f"AI 回答生成失败: {error}"}
    refs = parse_refs_fn(answer, id_to_idx)
    now = now_fn().strftime("%Y-%m-%d %H:%M")
    with connect_fn() as conn:
        conn.execute(
            "INSERT INTO brainstorm_messages (question_id, role, content, refs_json, created_at) VALUES (?, 'user', ?, '[]', ?)",
            (question_id, request.question, now),
        )
        conn.execute(
            "INSERT INTO brainstorm_messages (question_id, role, content, refs_json, created_at) VALUES (?, 'assistant', ?, ?, ?)",
            (question_id, answer, json.dumps(refs), now),
        )
        for event_id in request.event_ids:
            conn.execute(
                "INSERT OR IGNORE INTO brainstorm_event_links (question_id, event_id) VALUES (?, ?)",
                (question_id, event_id),
            )
        markdown_path = markdown_path_fn(question_id)
        md_block = f"## 回答 ({now})\n\n{answer}\n\n---\n\n"
        full_markdown = _append_markdown(markdown_path, md_block)
        conn.execute(
            "UPDATE brainstorm_questions SET content_md = ? WHERE id = ?",
            (full_markdown, question_id),
        )
    return {
        "messages": [
            {"role": "user", "content": request.question, "created_at": now},
            {
                "role": "assistant",
                "content": answer,
                "refs": refs,
                "created_at": now,
            },
        ],
        "locked_event_ids": request.event_ids,
    }


def send_conversation_message(
    question_id: str,
    request: Any,
    *,
    connect_fn: ConnectFn,
    call_ai_chat_fn: ChatFn,
    build_reference_docs_fn: BuildReferenceDocsFn,
    build_conversation_messages_fn: Callable[[str], list[dict]],
    parse_refs_fn: Callable[[str, dict[str, str]], list[str]],
    markdown_path_fn: MarkdownPathFn,
    now_fn: Callable[[], Any],
    logger: logging.Logger,
) -> dict[str, object]:
    if not request.content.strip():
        raise HTTPException(status_code=400, detail="追问内容不能为空")
    with connect_fn() as conn:
        event_rows = conn.execute(
            "SELECT event_id FROM brainstorm_event_links WHERE question_id = ?",
            (question_id,),
        ).fetchall()
    locked_ids = [row["event_id"] for row in event_rows]
    if not locked_ids:
        raise HTTPException(status_code=400, detail="请先选择参考文档并开始对话")
    articles, id_to_idx = build_reference_docs_fn(locked_ids)
    history = build_conversation_messages_fn(question_id)
    try:
        docs_text = "\n\n".join(
            f"[文档{a['index']}] 《{a['title']}》\n{a['text']}" for a in articles
        )
        system_prompt = (
            "你是严谨的研究分析助手。请基于以下参考文档和对话历史回答用户追问。\n"
            "规则：\n"
            "1. 引用文档中的具体事实、数据、观点时，在对应句子末尾标注 [文档N]\n"
            "2. 概念性问题（如'XX是什么意思'）用通用知识回答，不强制引用文档\n"
            "3. 回答简洁、有针对性\n\n"
            "参考文档：\n"
            f"{docs_text}"
        )
        messages = [{"role": "system", "content": system_prompt}]
        messages.extend(history)
        messages.append({"role": "user", "content": request.content})
        answer = _brainstorm_chat(messages, 2000, "answer", call_ai_chat_fn)
    except Exception as error:
        logger.warning(
            "Conversation message failed for question %s: %s", question_id, error
        )
        return {"error": f"AI 回答生成失败: {error}"}
    refs = parse_refs_fn(answer, id_to_idx)
    now = now_fn().strftime("%Y-%m-%d %H:%M")
    with connect_fn() as conn:
        conn.execute(
            "INSERT INTO brainstorm_messages (question_id, role, content, refs_json, created_at) VALUES (?, 'user', ?, '[]', ?)",
            (question_id, request.content, now),
        )
        conn.execute(
            "INSERT INTO brainstorm_messages (question_id, role, content, refs_json, created_at) VALUES (?, 'assistant', ?, ?, ?)",
            (question_id, answer, json.dumps(refs), now),
        )
        markdown_path = markdown_path_fn(question_id)
        md_block = (
            f"## 追问 ({now})\n\n**问：**{request.content}\n\n{answer}\n\n---\n\n"
        )
        full_markdown = _append_markdown(markdown_path, md_block)
        conn.execute(
            "UPDATE brainstorm_questions SET content_md = ? WHERE id = ?",
            (full_markdown, question_id),
        )
    return {
        "message": {
            "role": "assistant",
            "content": answer,
            "refs": refs,
            "created_at": now,
        }
    }


def get_conversation(question_id: str, *, connect_fn: ConnectFn) -> dict[str, object]:
    with connect_fn() as conn:
        question = conn.execute(
            "SELECT id FROM brainstorm_questions WHERE id = ?", (question_id,)
        ).fetchone()
        if not question:
            raise HTTPException(status_code=404, detail="Question not found")
        event_rows = conn.execute(
            "SELECT event_id FROM brainstorm_event_links WHERE question_id = ?",
            (question_id,),
        ).fetchall()
        message_rows = conn.execute(
            "SELECT id, role, content, refs_json, created_at FROM brainstorm_messages WHERE question_id = ? ORDER BY id ASC",
            (question_id,),
        ).fetchall()
    locked_ids = [row["event_id"] for row in event_rows]
    messages: list[dict] = []
    for row in message_rows:
        refs: list[str] = []
        try:
            refs = json.loads(row["refs_json"])
        except (json.JSONDecodeError, TypeError):
            pass
        messages.append(
            {
                "id": row["id"],
                "role": row["role"],
                "content": row["content"],
                "refs": refs,
                "created_at": row["created_at"],
            }
        )
    return {"locked_event_ids": locked_ids, "messages": messages}


def generate_conversation_summary(
    question_id: str,
    *,
    connect_fn: ConnectFn,
    call_ai_chat_fn: ChatFn,
    build_reference_docs_fn: BuildReferenceDocsFn,
    build_conversation_messages_fn: Callable[[str], list[dict]],
    parse_refs_fn: Callable[[str, dict[str, str]], list[str]],
    markdown_path_fn: MarkdownPathFn,
    now_fn: Callable[[], Any],
    logger: logging.Logger,
) -> dict[str, object]:
    with connect_fn() as conn:
        question = conn.execute(
            "SELECT id, question FROM brainstorm_questions WHERE id = ?",
            (question_id,),
        ).fetchone()
        if not question:
            raise HTTPException(status_code=404, detail="Question not found")
        event_rows = conn.execute(
            "SELECT event_id FROM brainstorm_event_links WHERE question_id = ?",
            (question_id,),
        ).fetchall()
    locked_ids = [row["event_id"] for row in event_rows]
    if not locked_ids:
        return {"error": "请先选择参考文档并开始对话"}
    articles, id_to_idx = build_reference_docs_fn(locked_ids)
    history = build_conversation_messages_fn(question_id)
    if not history:
        return {"error": "没有对话历史可总结"}

    with connect_fn() as conn:
        concept_rows = conn.execute(
            "SELECT title, ai_summary FROM events WHERE content_type = 'concept' AND ai_summary IS NOT NULL AND ai_summary != ''"
        ).fetchall()
        concepts = [
            {"title": row["title"], "summary": row["ai_summary"]}
            for row in concept_rows
        ]

    transcript_parts: list[str] = []
    for message in history:
        role_label = "用户" if message["role"] == "user" else "AI助手"
        transcript_parts.append(f"**{role_label}**：{message['content']}")
    transcript = "\n\n".join(transcript_parts)

    try:
        docs_text = "\n\n".join(
            f"[文档{a['index']}] 《{a['title']}》\n{a['text']}" for a in articles
        )
        concepts_text = (
            "\n".join(f"### 《{c['title']}》\n{c['summary']}" for c in concepts)
            if concepts
            else "（暂无）"
        )
        prompt = (
            "你正在进行研究对话的最终总结。以下是参考文档和完整对话历史。\n"
            "请提炼为一个结构化总结，格式如下：\n\n"
            "## 核心结论\n（用一两段话清晰回答原始问题，标注引用 [文档N]）\n\n"
            "## 概念定义\n（如果问题是询问特定概念/术语的含义，请从对话和文档中提取每个概念的完整定义。\n"
            "不要省略——对话中给出的核心特征、表现形式、运作机制、具体举例等都应纳入。格式：\n"
            "### 概念名称\n- **定义**：一句话概括\n- **核心特征**：...\n"
            "- **表现形式/运作机制**：...\n"
            "若问题不涉及概念定义（如纯分析/判断类问题），本节可省略）\n\n"
            "## 关键论点\n1. 论点一 [文档N][文档M]\n2. 论点二 [文档N]\n...\n\n"
            "## 待深挖方向\n- 方向一\n- 方向二\n\n"
            "## 相关概念\n（分析对话中涉及的概念，对比下方「系统已有概念」，列出相关的并简述关联点。格式：\n"
            "- **概念名称**：关联说明\n若无相关则标注「暂无明确相关概念」）\n\n"
            "## 参考文档清单\n[文档1] 标题一\n[文档2] 标题二\n...\n\n"
            "要求：每条论点独立标注来源；引用格式为 [文档N]。\n\n"
            f"参考文档：\n{docs_text}\n\n"
            f"系统已有概念：\n{concepts_text}\n\n"
            f"原始问题：{question['question']}\n\n"
            f"对话历史：\n{transcript}"
        )
        messages = [
            {
                "role": "system",
                "content": "你是严谨的研究总结助手，请基于对话和参考文档生成结构化总结。",
            },
            {"role": "user", "content": prompt},
        ]
        summary = _brainstorm_chat(messages, 3000, "summary", call_ai_chat_fn)
    except Exception as error:
        logger.warning(
            "Summary generation failed for question %s: %s", question_id, error
        )
        return {"error": f"AI 总结生成失败: {error}"}

    refs = parse_refs_fn(summary, id_to_idx)
    now = now_fn().strftime("%Y-%m-%d %H:%M")
    with connect_fn() as conn:
        markdown_path = markdown_path_fn(question_id)
        md_block = f"## 总结 ({now})\n\n{summary}\n\n---\n\n"
        full_markdown = _append_markdown(markdown_path, md_block)
        conn.execute(
            "UPDATE brainstorm_questions SET content_md = ?, answer = ?, summary_created_at = ? WHERE id = ?",
            (full_markdown, summary, now, question_id),
        )

    return {"summary": summary, "refs": refs, "created_at": now}
