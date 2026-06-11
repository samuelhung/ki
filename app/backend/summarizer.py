"""Generate structured summaries from douyin transcripts using DeepSeek API.

Adapted from the Knowledge project's summary template approach:
https://github.com/nousresearch/hermes-agent/blob/main/docs/skills.md
"""

from __future__ import annotations

import logging

from .deepseek_client import chat

logger = logging.getLogger(__name__)

SUMMARY_TEMPLATE = """你是中文内容总结助手。请严格基于原文，按以下结构输出 Markdown 总结。

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

- （只出问题不下结论）"""


def summarize_transcript(transcript: str, title: str = "", timeout: int = 180) -> str | None:
    """Generate a structured Chinese summary from a douyin transcript.

    Returns the summary markdown string, or None on failure.
    """
    if not transcript or len(transcript.strip()) < 100:
        logger.warning("Transcript too short for summarization")
        return None

    # Truncate very long transcripts
    max_input = 8000
    truncated = transcript[:max_input] if len(transcript) > max_input else transcript

    user_prompt = f"原文标题：{title}\n\n原文内容：\n{truncated}"

    messages = [
        {"role": "system", "content": SUMMARY_TEMPLATE},
        {"role": "user", "content": user_prompt},
    ]

    content = chat(messages, temperature=0.4, max_tokens=4096, timeout=timeout)
    if content:
        logger.info("Summary generated for transcript (%d chars → %d chars)", len(transcript), len(content))
    return content
