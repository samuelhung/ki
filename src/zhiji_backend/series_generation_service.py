"""AI-generated content workflows for series."""

import json
import logging

from fastapi import HTTPException

logger = logging.getLogger("zhiji_backend.routes.series_routes")


def generate_series_intro(series_id, *, connect_fn, init_db_fn, chat_fn):
    """Generate a narrative intro connecting all member overviews."""
    init_db_fn()
    with connect_fn() as conn:
        row = conn.execute(
            "SELECT id, name, description, member_ids FROM series WHERE id = ?",
            (series_id,),
        ).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="专题不存在")

        try:
            member_ids = json.loads(row["member_ids"])
        except (json.JSONDecodeError, TypeError):
            member_ids = []

        if len(member_ids) < 2:
            raise HTTPException(status_code=400, detail="专题成员不足，无法生成导言")

        placeholders = ",".join(["?" for _ in member_ids])
        event_rows = conn.execute(
            f"SELECT title, overview FROM events WHERE id IN ({placeholders})",
            member_ids,
        ).fetchall()

    members_text = ""
    for i, ev in enumerate(event_rows):
        members_text += f"\n### [{i + 1}] {ev['title']}\n{ev['overview']}\n"

    prompt = f"""你是知识专题策展人。请为以下专题撰写一段 300-500 字的导言。

专题名称：{row['name']}
专题简介：{row['description']}

成员内容概述：
{members_text}

要求：
- 用叙事语言而非列表，像博物馆展览的引导词
- 告诉读者这个专题在回答什么核心问题
- 简要介绍各篇内容在专题中的角色和逻辑关系
- 给读者一个合理的阅读顺序建议
- 文末附 1-2 句邀请读者深入探索的话
- 引用用 [N] 标注
- 直接输出 Markdown，不要前置说明"""  # fmt: skip

    messages = [
        {
            "role": "system",
            "content": "你是知识专题策展人。导言用叙事语言，像博物馆引导词，告诉读者这个专题回答什么核心问题及各篇逻辑关系。",
        },
        {"role": "user", "content": prompt},
    ]

    intro = chat_fn(
        messages,
        temperature=0.5,
        max_tokens=1024,
        timeout=120,
        module="series",
        task="intro",
    )
    if not intro:
        raise HTTPException(status_code=500, detail="AI 导言生成失败")

    now_ts = __import__("datetime").datetime.now().strftime("%Y-%m-%d %H:%M")
    with connect_fn() as conn:
        conn.execute(
            "UPDATE series SET intro = ?, updated_at = ? WHERE id = ?",
            (intro.strip(), now_ts, series_id),
        )

    return {"intro": intro.strip()}


def generate_series_summary(series_id, *, connect_fn, init_db_fn, chat_fn):
    """Generate the structured series summary."""
    init_db_fn()
    with connect_fn() as conn:
        row = conn.execute(
            "SELECT id, name, description, member_ids FROM series WHERE id = ?",
            (series_id,),
        ).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="专题不存在")

        try:
            member_ids = json.loads(row["member_ids"])
        except (json.JSONDecodeError, TypeError):
            member_ids = []

        if len(member_ids) < 2:
            raise HTTPException(status_code=400, detail="专题成员不足，无法生成总结")

        placeholders = ",".join(["?" for _ in member_ids])
        event_rows = conn.execute(
            f"SELECT title, overview FROM events WHERE id IN ({placeholders})",
            member_ids,
        ).fetchall()

    members_text = ""
    for i, ev in enumerate(event_rows):
        members_text += f"\n### [{i + 1}] {ev['title']}\n{ev['overview']}\n"

    prompt = f"""你是知识专题分析师。请为以下专题生成一份详尽的结构化速览总结。

专题名称：{row['name']}
专题简介：{row['description']}

**重要**：专题简介中列举的分析维度（如历史、宗教、政治、经济等），必须在「关键洞察」中逐一覆盖。每条洞察明确标注对应哪个维度。

成员内容概述：
{members_text}

请严格按以下 Markdown 格式输出，每个部分都要充实：

## 核心论点
（一句话，不超过 60 字，概括这个专题在回答什么核心问题）

## 关键洞察
（从成员 overview 中提炼 4-6 条核心洞察。按专题简介承诺的维度组织，每条格式：「维度 · 视角标签：核心观点」+ 1-2 句支撑论据。标注依据来源 [N]）
- **历史 · 殖民创伤**：伊朗对西方的仇恨根植于近代被英俄瓜分的屈辱史。[3]
  论据：1907年英俄条约直接瓜分伊朗主权，伊朗连参与谈判的资格都没有。
- **宗教 · 什叶派身份**：伊朗为对抗逊尼派主动改宗，强化了独特的民族认同。[4]
  论据：...

## 关键数据/时间节点
（从内容中提取的具体数字、年份、关键事件，按时间或重要性排列）
- 1907 — 英俄条约瓜分伊朗主权
- 16% vs 84% — 巴列维时期石油利润分配比例

## 逻辑脉络
（揭示成员之间的逻辑关系。用分组说明哪些是因果、哪些是对比、哪些是递进）
1. [1] 标题简述 — 作用：奠定历史背景
2. [2] 标题简述 — 作用：揭示转折点
   ↳ 对比 [3]：从另一视角提供对照

## 视角分歧
（如果成员之间对同一问题有不同的立场、解释或侧重，标注出来）
- 分歧点：成员 [A] 认为...，而成员 [B] 强调...

## 关键人物/实体
（专题反复提及的核心人物、组织、国家，每项附简要角色说明）
- 实体名 — 角色与重要性

## 待探索问题
（基于现有内容自然延伸但尚未覆盖的问题，3-5 条）
- 问题一

直接输出 Markdown，不要前置说明。"""  # fmt: skip

    messages = [
        {
            "role": "system",
            "content": "你是知识专题分析师。输出结构化的 Markdown 总结。关键洞察必须按专题简介承诺的分析维度逐一覆盖，每条标注维度标签（如 历史·、宗教·、政治·、经济·）。",
        },
        {"role": "user", "content": prompt},
    ]

    summary = chat_fn(
        messages,
        temperature=0.3,
        max_tokens=3072,
        timeout=120,
        module="series",
        task="summary",
    )
    if not summary:
        raise HTTPException(status_code=500, detail="AI 总结生成失败")

    now_ts = __import__("datetime").datetime.now().strftime("%Y-%m-%d %H:%M")
    with connect_fn() as conn:
        conn.execute(
            "UPDATE series SET summary = ?, updated_at = ? WHERE id = ?",
            (summary.strip(), now_ts, series_id),
        )

    return {"summary": summary.strip()}


def generate_series_paper(series_id, *, connect_fn, init_db_fn, chat_fn):
    """Generate the paper-style deep analysis for a series."""
    init_db_fn()
    with connect_fn() as conn:
        row = conn.execute(
            "SELECT id, name, description, member_ids FROM series WHERE id = ?",
            (series_id,),
        ).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="专题不存在")

        try:
            member_ids = json.loads(row["member_ids"])
        except (json.JSONDecodeError, TypeError):
            member_ids = []

        if len(member_ids) < 2:
            raise HTTPException(status_code=400, detail="专题成员不足，无法生成论文")

        placeholders = ",".join(["?" for _ in member_ids])
        event_rows = conn.execute(
            f"SELECT title, overview FROM events WHERE id IN ({placeholders})",
            member_ids,
        ).fetchall()

    members_text = ""
    for i, ev in enumerate(event_rows):
        members_text += f"\n### [{i + 1}] {ev['title']}\n{ev['overview']}\n"

    prompt = f"""你是资深国际关系研究学者。请为以下专题撰写一篇**论文式深度分析**。

专题名称：{row['name']}
专题简介：{row['description']}

成员内容概述：
{members_text}

---

**写作要求：**

1. **叙事弧线**：这是一篇有起承转合的论文/演讲稿，不是要点列表
   - 开头（背景/问题）：为什么这个问题值得关注？核心矛盾是什么？
   - 发展（分析论证）：逐层深入，每段有论点+论据+过渡
   - 高潮（核心发现）：跨维度提炼最关键的判断，这是全文的思想顶点
   - 结尾（结论与展望）：未来走向是什么？留下的思考是什么？

2. **论点-论据结构**：每个观点必须有具体事件/数据支撑，引用用 [N] 标注
   - 不要空泛概括——要引具体史实、人物、时间点
   - 论据不是重复概述，而是用来推进论证

3. **段落式写作**：连贯段落，有逻辑连接词和过渡句
   - 每段说清楚一件事，段落间有"然而""更进一步""这背后是""换句话说"等过渡
   - 可以设问，可以强调

4. **讲稿节奏**：
   - 可以有"关键在于""更关键的是""这揭示了一个更深层的问题"等引导语
   - 结尾有力度，像演讲的收束，给读者留下思考余味

**格式要求：**
- 输出纯 Markdown，不要前置说明
- 全文 1500-2500 字
- 每段之间空一行
- 引用用 [N] 标注
- 可以用小标题分段（不超过 5 个）"""  # fmt: skip

    messages = [
        {
            "role": "system",
            "content": "你是资深国际关系研究学者。请撰写论文式深度分析：叙事弧线完整（开头→发展→高潮→结尾），论点-论据结构，连贯段落式写作，讲稿节奏。每个观点引用具体事件/数据并标注 [N]。输出纯 Markdown，全文 1500-2500 字。",
        },
        {"role": "user", "content": prompt},
    ]

    paper = chat_fn(
        messages,
        temperature=0.5,
        max_tokens=4096,
        timeout=180,
        module="series",
        task="paper",
    )
    if not paper:
        raise HTTPException(status_code=500, detail="AI 论文生成失败")

    now_ts = __import__("datetime").datetime.now().strftime("%Y-%m-%d %H:%M")
    with connect_fn() as conn:
        conn.execute(
            "UPDATE series SET paper = ?, updated_at = ? WHERE id = ?",
            (paper.strip(), now_ts, series_id),
        )

    return {"paper": paper.strip()}
