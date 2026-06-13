"""Generate structured summaries from douyin transcripts using DeepSeek API.

Adapted from the Knowledge project's summary template approach:
https://github.com/nousresearch/hermes-agent/blob/main/docs/skills.md
"""

from __future__ import annotations

import logging

from .deepseek_client import chat

logger = logging.getLogger(__name__)

SUMMARY_TEMPLATE = """你是中文内容总结助手。请严格基于原文，按以下结构输出 Markdown。

规则：
- 只基于原文，不得引入外部知识或常识补全
- 每条事实/观点后附 `（证据：原文关键词 ≤20字）`，无证据就写 `（证据：信息不足）`
- 所有延伸判断用 `【推断】` 或 `【假设】` 开头，附 `（依据：...）`
- 不适用就写"信息不足/本期不涉及"

---

## 一句话结论

## 核心要点（5-8条）

- （每条的格式：主张 + 证据）

## 事实

- （原文明示的事实，每条带证据）

### 推断

- （从原文可推的判断，标注【推断】/【假设】）

### 信息缺口

- （原文没提但重要的变量）

## 机会透镜

### 中国市场关联

- 市场/生产/产品，不适用就写"不涉及"

### 国际视角

- 同上

## 值得深挖的问题

- （只出问题不下结论）

---

## 概述

用一段 **严格不超过 500 字**的连续文字，概述本视频/文档的核心内容。要求：
- 纯叙事，不要列表、不要分点、不要标题
- 讲清楚「这内容在说什么，核心观点是什么」
- 语言流畅自然，像在向朋友介绍这个视频
- **字数上限 500 字，超过将被截断。请在 480-500 字之间自然收尾。**"""


def summarize_transcript(transcript: str, title: str = "", timeout: int = 180, need_title: bool = False) -> dict | None:
    """Generate a structured Chinese summary + plain overview from a transcript.

    Returns dict with keys 'summary' (markdown) and 'overview' (≤500 chars narrative),
    plus 'suggested_title' when need_title=True.  Returns None on failure.
    """
    if not transcript or len(transcript.strip()) < 100:
        logger.warning("Transcript too short for summarization")
        return None

    # Truncate very long transcripts
    max_input = 8000
    truncated = transcript[:max_input] if len(transcript) > max_input else transcript

    user_prompt = f"原文标题：{title}\n\n原文内容：\n{truncated}"

    system_prompt = SUMMARY_TEMPLATE
    if need_title:
        system_prompt += "\n\n此外，请根据内容生成一个简洁的标题（≤30字），用 `## 建议标题` 标注在概述之后。"

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt},
    ]

    content = chat(messages, temperature=0.4, max_tokens=4096, timeout=timeout,
                   module="ingest_pipeline", task="summarize")
    if not content:
        return None

    # Split off the overview section
    overview_marker = "## 概述"
    overview = ""
    suggested_title = ""
    summary = content
    if overview_marker in content:
        parts = content.split(overview_marker, 1)
        summary = parts[0].strip()
        rest = parts[1].strip()
        # Check if suggested_title follows overview
        title_marker = "## 建议标题"
        if need_title and title_marker in rest:
            ov_parts = rest.split(title_marker, 1)
            overview = ov_parts[0].strip()
            # Extract title text: take the first non-empty line
            title_text = ov_parts[1].strip()
            # Strip "**" and bullet markers
            title_text = title_text.lstrip("-* ").strip()
            if title_text:
                suggested_title = title_text.split("\n")[0].strip()
        else:
            overview = rest
        # Limit to ~500 chars, but at the last complete sentence boundary
        if len(overview) > 500:
            # Find last 。！？ within first 500 chars
            cut = overview[:500]
            last_period = max(cut.rfind('。'), cut.rfind('！'), cut.rfind('？'))
            overview = cut[:last_period + 1] if last_period >= 0 else cut[:500]

    result = {"summary": summary, "overview": overview}
    if suggested_title:
        result["suggested_title"] = suggested_title

    logger.info("Summary + overview generated (%d chars transcript → %d chars summary, %d chars overview)%s",
                len(transcript), len(summary), len(overview),
                f", title={suggested_title}" if suggested_title else "")
    return result
