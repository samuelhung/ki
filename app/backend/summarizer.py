"""Generate structured summaries from douyin transcripts using DeepSeek API.
"""

from __future__ import annotations

import logging

from .deepseek_client import chat

logger = logging.getLogger(__name__)

SUMMARY_TEMPLATE = """你是中文内容总结助手。请严格基于原文，按以下结构输出 Markdown。

规则：
- 只基于原文，不得引入外部知识或常识补全
- 所有判断需有原文事实支撑
- 引用原文具体数据/引语时，在句末标注来源编号 [N]（如 [1]、[2]），普通叙述不需标注
- 不适用就写"信息不足/本期不涉及"
- 概述在前，让读者先了解全貌

---

## 概述

用一段 **严格不超过 500 字**的连续文字，概述本视频/文档的核心内容。要求：
- 纯叙事，不要列表、不要分点、不要标题
- 讲清楚「这内容在说什么，核心观点是什么」
- 语言流畅自然，像在向朋友介绍这个视频
- **字数上限 500 字，超过将被截断。请在 480-500 字之间自然收尾。**

## 核心论点

（一句话，不超过 60 字，概括这个内容在回答什么核心问题）

## 关键洞察

（从原文提炼 3-5 条核心洞察。每条格式：维度标签 · 核心观点 + 1-2 句支撑论据。维度标签如 历史·、政治·、经济·、科技·、文化·、社会·、军事· 等，选最贴切的。）

示例：
- **历史 · 殖民扩张模式**：英国以农业定居为主，法国以毛皮贸易和印第安结盟为主，两种模式决定了北美殖民地未来的走向。[1]
  论据：英国人圈地种田驱赶原住民，法国人深入内陆学习印第安语言通婚。

## 关键数据/时间节点

（从原文提取的具体数字、年份、关键事件，每条一行，按时间或重要性排列。示例格式：`- 1759 — 魁北克战役，英军15分钟取胜，双方主将阵亡`）

## 叙事脉络

（原文的论证/叙事逻辑链，3-4 步，说明因果关系或递进关系）
1. 起点（背景/问题设定）
2. 转折（关键事件或冲突）
3. 结果（结局与影响）
   ↳ 如有：进一步推演或遗留问题

## 信息缺口

（原文没提但重要的变量，3-5 条）

## 机会透镜

### 中国市场关联

- 市场/生产/产品/投资角度，确实没有关联就写"本期内容不涉及中国市场"

### 国际视角

- 全球格局/地缘/跨国产业角度，确实没有就写"本期内容不涉及国际视角"

## 深挖问题

（基于原文自然延伸但未回答的问题，3-5 条，只出问题不下结论）"""


def summarize_transcript(transcript: str, title: str = "", timeout: int = 180, need_title: bool = False) -> dict | None:
    """Generate a structured Chinese summary + plain overview from a transcript.

    Returns dict with keys 'summary' (markdown body) and 'overview' (≤500 chars narrative),
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
        system_prompt += "\n\n此外，请根据内容生成一个简洁的标题（≤30字），用 `## 建议标题` 标注在全文末尾。"

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt},
    ]

    content = chat(messages, temperature=0.4, max_tokens=4096, timeout=timeout,
                   module="ingest_pipeline", task="summarize")
    if not content:
        return None

    # ── Parse the new template structure ──
    # Structure: ## 概述 (narrative) → ## 核心论点 → ... → ## 深挖问题 → [## 建议标题]
    overview = ""
    summary = content
    suggested_title = ""

    overview_marker = "## 概述"
    thesis_marker = "## 核心论点"
    title_marker = "## 建议标题"

    if overview_marker in content and thesis_marker in content:
        # Split: everything before ## 核心论点 is overview, everything from ## 核心论点 onward is summary body
        ov_start = content.index(overview_marker)
        th_start = content.index(thesis_marker)

        if ov_start < th_start:
            # Extract overview text between ## 概述 and ## 核心论点
            ov_raw = content[ov_start + len(overview_marker):th_start].strip()
            overview = ov_raw

            # Summary body starts from ## 核心论点
            summary = content[th_start:]

            # If need_title, strip ## 建议标题 from end of summary
            if need_title and title_marker in summary:
                ti_pos = summary.index(title_marker)
                title_text = summary[ti_pos + len(title_marker):].strip()
                summary = summary[:ti_pos].strip()
                # Extract title: first non-empty line, strip markers
                for line in title_text.split("\n"):
                    clean = line.strip().lstrip("-* ").strip()
                    if clean:
                        suggested_title = clean
                        break

    # ── Limit overview to ~500 chars at sentence boundary ──
    if len(overview) > 500:
        cut = overview[:500]
        last_period = max(cut.rfind('。'), cut.rfind('！'), cut.rfind('？'))
        overview = cut[:last_period + 1] if last_period >= 0 else cut[:500]

    # ── Fallback: if markers not found, treat whole as summary ──
    if not overview and overview_marker not in content:
        # Old format or unexpected output — extract overview from end as before
        if overview_marker in content:
            parts = content.split(overview_marker, 1)
            summary = parts[0].strip()
            overview = parts[1].strip()
            if len(overview) > 500:
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
