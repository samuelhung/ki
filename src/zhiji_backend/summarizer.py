"""Generate structured summaries from transcripts and documents using the configured AI API.
"""

from __future__ import annotations

import logging

from .ai_client import chat

logger = logging.getLogger(__name__)

# ── 视频/短文模板 ──

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


# ── 书籍/长文档模板 ──

BOOK_TEMPLATE = """你是一位资深学术书评人。以下内容来自一本完整书籍的全文。你的任务是撰写一份详尽、有深度的书评式总结。请严格基于原文，按以下结构输出 Markdown。

规则：
- 只基于原文，不得引入外部知识或常识补全
- 所有判断需有原文事实/引语支撑，引用原文关键句时标注所在章
- 写一份"配得上一本书的总结"——每个板块都要充实，不要蜻蜓点水
- 不适用就写"该书不涉及此维度"

---

## 全书概述（800-1200字）

叙事式概述，回答三个问题：
- 这本书要回答什么核心问题？作者站在什么立场、用什么方法？
- 全书读完最应该被记住的三件事是什么？
- 不逐章复述目录，而是抓住论证主线和思想贡献

## 论证架构

展示全书如何组织论证——分几条主线、各线之间是什么关系、在何处交汇形成核心判断。

格式：
1. **主线一：……**（涵盖第 X-Y 章）——这条线解决什么问题？
2. **主线二：……**（涵盖第 Z-W 章）——与前一条线的关系是对比/递进/补证？
   ↳ 两条线在何处交汇，形成什么判断？

## 核心论点（3-5条）

不是复述章节标题，而是读完后的独立判断。每条包含：**论点 + 论据**（引用原文关键句或数据，标注所在章）。

## 各章要义

每章一段，包含三个要素：
- **定位**：这章在全书论证中起什么作用（铺垫/转折/高潮/收束）
- **核心内容**：200-300字的概括
- **关键判断**：这章最值得记住的一个判断

## 关键人物/概念/事件

全书反复出现的重要实体，分三组呈现。每组每个实体附带一句话角色说明。

### 人物谱系
### 核心概念
### 关键事件

## 思想谱系

- 作者在跟谁对话？（继承谁的思路、反驳谁的观点、填补什么空白）
- 引用了哪些著作/学派/理论框架作为论据？
- 这本书在其所属领域的知识地图中处于什么位置？

## 独到之处

这本书跟同类题材/同领域著作相比，最不一样的三点是什么？可以是独特立场、少见史料、创新写法、有争议的判断——不一定是优点，但一定是特点。

## 可商榷之处

以独立思考的读者视角审视：
- 哪些论证所依赖的假设值得推敲？
- 哪些关键问题作者回避或轻轻带过？
- 哪些史料/数据的解读可以有不同看法？
- 作者的立场是否在某个议题上导致系统性偏差？
确实没有明显可商榷的就写"该书论证严密，未发现明显可商榷之处"

## 机会透镜

不强行找关联，但一本书的价值往往在于能否跨越时空提供启发。

### 中国市场关联
- 如果书中讨论的机制/模式/规律可以迁移到理解中国市场，具体怎么迁移？为什么能/不能？

### 国际视角
- 这本书对理解当前全球格局有哪些启发？哪些判断经得起时间检验？

## 拓展问题（5-8条）

基于全书内容自然延伸、但作者没有直接回答的深层问题。问题要有思辨深度——不是"XXXX是什么"的信息性提问，而是"如果X成立，Y是否必然？"这种推演式提问。

## 延伸阅读

基于本书推荐 3-5 本相关的书或论文，每本附一句（≤30字）说明推荐理由。可以是对照、补充、思想源头或对立面。"""


# ── 主函数 ──

BOOK_THRESHOLD = 50000       # 超过此字符数走书级模板
BOOK_INPUT_CAP = 600000      # 硬天花板，防止超 1M token
VIDEO_MAX_INPUT = 8000       # 视频/短文的截断上限


def summarize_transcript(
    transcript: str,
    title: str = "",
    timeout: int = 180,
    need_title: bool = False,
    extract_entities: bool = True,
) -> dict | None:
    """Generate a structured Chinese summary + overview + entity graph.

    Auto-detects book-length content (>50K chars) and switches to a
    detailed book-review template with full-text input and expanded output.

    When extract_entities=True, also extracts knowledge graph entities and
    relations in a follow-up AI call.

    Returns dict with keys:
      - 'summary' (markdown body)
      - 'overview' (narrative)
      - 'entities' (list of {name, type, summary, category}) when extract_entities=True
      - 'relations' (list of {source, target, type}) when extract_entities=True
      - 'suggested_title' when need_title=True
    Returns None on failure.
    """
    if not transcript or len(transcript.strip()) < 100:
        logger.warning("Transcript too short for summarization")
        return None

    text_len = len(transcript)

    # ── Auto-detect: book-length content → book template ──
    use_book_template = text_len > BOOK_THRESHOLD

    if use_book_template:
        max_input = BOOK_INPUT_CAP
        system_prompt = BOOK_TEMPLATE
        max_tokens = 65536
        overview_label = "全书概述"
    else:
        max_input = VIDEO_MAX_INPUT
        system_prompt = SUMMARY_TEMPLATE
        max_tokens = 4096
        overview_label = "概述"

    truncated = transcript[:max_input] if text_len > max_input else transcript

    if use_book_template:
        user_prompt = (
            f"书名：{title}\n\n"
            f"以下为全书全文（约 {text_len} 字符）。请撰写详尽书评式总结。\n\n"
            f"{truncated}"
        )
    else:
        user_prompt = f"原文标题：{title}\n\n原文内容：\n{truncated}"

    if need_title:
        system_prompt += "\n\n此外，请根据内容生成一个简洁的标题（≤30字），用 `## 建议标题` 标注在全文末尾。"

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt},
    ]

    content = chat(
        messages,
        temperature=0.4,
        max_tokens=max_tokens,
        timeout=timeout,
        module="ingest_pipeline",
        task="summarize",
    )
    if not content:
        return None

    # ── Parse: extract overview and summary body ──
    overview_marker = f"## {overview_label}"
    thesis_marker = "## 论证架构" if use_book_template else "## 核心论点"
    title_marker = "## 建议标题"

    overview = ""
    summary = content
    suggested_title = ""

    if overview_marker in content and thesis_marker in content:
        ov_start = content.index(overview_marker)
        th_start = content.index(thesis_marker)
        if ov_start < th_start:
            overview = content[ov_start + len(overview_marker):th_start].strip()
            summary = content[th_start:]

            if need_title and title_marker in summary:
                ti_pos = summary.index(title_marker)
                title_text = summary[ti_pos + len(title_marker):].strip()
                summary = summary[:ti_pos].strip()
                for line in title_text.split("\n"):
                    clean = line.strip().lstrip("-* ").strip()
                    if clean:
                        suggested_title = clean
                        break

    # ── Trim overview to length ──
    ov_limit = 1200 if use_book_template else 500
    if len(overview) > ov_limit:
        cut = overview[:ov_limit]
        last_period = max(cut.rfind("。"), cut.rfind("！"), cut.rfind("？"))
        overview = cut[:last_period + 1] if last_period >= 0 else cut[:ov_limit]

    # ── Fallback: markers not found ──
    if not overview and overview_marker in content:
        parts = content.split(overview_marker, 1)
        summary = parts[0].strip()
        overview = parts[1].strip()
        if len(overview) > ov_limit:
            cut = overview[:ov_limit]
            last_period = max(cut.rfind("。"), cut.rfind("！"), cut.rfind("？"))
            overview = cut[:last_period + 1] if last_period >= 0 else cut[:ov_limit]

    result = {"summary": summary, "overview": overview}
    if suggested_title:
        result["suggested_title"] = suggested_title

    # ── Entity extraction for knowledge graph ──
    ent_count = 0
    rel_count = 0
    if extract_entities:
        entities, relations = _extract_entities(transcript, title, timeout)
        if entities is not None:
            result["entities"] = entities
            result["relations"] = relations
            ent_count = len(entities)
            rel_count = len(relations)

    logger.info(
        "Summary + overview generated (%d chars input, %s -> %d chars summary, %d chars overview)%s%s%s",
        text_len,
        "book" if use_book_template else "video",
        len(summary),
        len(overview),
        f", title={suggested_title}" if suggested_title else "",
        f", entities={ent_count}" if extract_entities else "",
        f", relations={rel_count}" if extract_entities else "",
    )
    return result


# ── Entity extraction ──

ENTITY_EXTRACTION_PROMPT = """你是知识图谱实体提取器。从文本中提取关键实体和它们之间的关系。

实体类型: person(人物) organization(组织) location(地点) concept(概念) event(事件) theory(理论框架) book(书籍) metric(数据指标)

关系类型: claims(主张) refutes(反驳) extends(继承发展) causes(因果关系) belongs_to(属于) contrasts(对比) cites(引用) synergizes(协同作用)

输出纯 JSON, 包含两个字段:
{
  "entities": [
    {"name": "实体名", "type": "类型", "summary": "<=15字简介", "category": "格局/财富/认知/前瞻"}
  ],
  "relations": [
    {"source": "源实体名", "target": "目标实体名", "type": "关系类型"}
  ]
}

要求:
- entity 的 name 必须与 relations 的 source/target 完全一致
- 只提取有实质内容的实体(核心人物/关键概念/重要地点组织), 泛泛提及的跳过
- 实体 5-15 个, 关系 3-8 对
- category 从 格局/财富/认知/前瞻 中选最贴切的一个
- 直接用 JSON 输出, 不包裹在 Markdown 代码块中"""


def _extract_entities(text: str, title: str, timeout: int) -> tuple:
    """Extract entities and relations from text using AI.

    Returns (entities_list, relations_list) or (None, None) on failure.
    """
    import json as _json

    # Use a smaller slice for entity extraction to keep it fast
    sample = text[:60000] if len(text) > 60000 else text
    user_prompt = f"标题: {title}\n\n文本内容:\n{sample}"

    messages = [
        {"role": "system", "content": ENTITY_EXTRACTION_PROMPT},
        {"role": "user", "content": user_prompt},
    ]

    raw = chat(
        messages,
        temperature=0.1,
        max_tokens=2048,
        timeout=min(timeout, 60),
        module="ingest_pipeline",
        task="entity_extraction",
    )
    if not raw:
        return None, None

    try:
        raw = raw.strip()
        if raw.startswith("```"):
            parts = raw.split("```")
            if len(parts) >= 2:
                raw = parts[1]
                if raw.startswith("json"):
                    raw = raw[4:]
                raw = raw.strip()
        data = _json.loads(raw)
        entities = data.get("entities", [])
        relations = data.get("relations", [])
        logger.info(
            "Entity extraction: %d entities, %d relations from %d chars",
            len(entities), len(relations), len(sample),
        )
        return entities, relations
    except (_json.JSONDecodeError, KeyError, TypeError) as e:
        logger.warning("Entity extraction parse error: %s", e)
        return None, None
