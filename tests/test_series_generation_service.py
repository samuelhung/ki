from __future__ import annotations

import importlib
import inspect
import json
import re
from contextlib import contextmanager
from pathlib import Path
from typing import Any

import pytest
from fastapi import HTTPException

from zhiji_backend.db import connect, init_db
from zhiji_backend.series_service import ConnectFn, InitDbFn


@pytest.fixture
def series_db(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("KI_DB_PATH", str(tmp_path / "series-generation.sqlite"))
    init_db()
    with connect() as conn:
        conn.execute(
            "INSERT INTO sources (id, name, type, url) "
            "VALUES ('manual', 'Manual', 'manual', '')"
        )
    return connect, init_db


def _service() -> Any:
    module_name = "zhiji_backend.series_generation_service"
    try:
        return importlib.import_module(module_name)
    except ModuleNotFoundError as error:
        if error.name != module_name:
            raise
        pytest.fail(f"{module_name} has not been extracted")


def _insert_event(event_id: str, title: str, overview: str) -> None:
    with connect() as conn:
        conn.execute(
            "INSERT INTO events "
            "(id, source_id, title, url, overview, status) "
            "VALUES (?, 'manual', ?, ?, ?, 'completed')",
            (event_id, title, f"https://example.com/{event_id}", overview),
        )


def _insert_series(member_ids: list[str] | str) -> None:
    stored_members = (
        member_ids if isinstance(member_ids, str) else json.dumps(member_ids)
    )
    with connect() as conn:
        conn.execute(
            "INSERT INTO series (id, name, description, member_ids, status) "
            "VALUES ('series-1', 'Target Series', 'Target description', ?, 'published')",
            (stored_members,),
        )


def _call(function_name: str, chat_fn, *, connect_fn=connect, init_db_fn=init_db):
    return getattr(_service(), function_name)(
        "series-1",
        connect_fn=connect_fn,
        init_db_fn=init_db_fn,
        chat_fn=chat_fn,
    )


INTRO_PROMPT = """你是知识专题策展人。请为以下专题撰写一段 300-500 字的导言。

专题名称：Target Series
专题简介：Target description

成员内容概述：

### [1] First title
First overview

### [2] Second title
Second overview


要求：
- 用叙事语言而非列表，像博物馆展览的引导词
- 告诉读者这个专题在回答什么核心问题
- 简要介绍各篇内容在专题中的角色和逻辑关系
- 给读者一个合理的阅读顺序建议
- 文末附 1-2 句邀请读者深入探索的话
- 引用用 [N] 标注
- 直接输出 Markdown，不要前置说明"""

SUMMARY_PROMPT = """你是知识专题分析师。请为以下专题生成一份详尽的结构化速览总结。

专题名称：Target Series
专题简介：Target description

**重要**：专题简介中列举的分析维度（如历史、宗教、政治、经济等），必须在「关键洞察」中逐一覆盖。每条洞察明确标注对应哪个维度。

成员内容概述：

### [1] First title
First overview

### [2] Second title
Second overview


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

直接输出 Markdown，不要前置说明。"""

PAPER_PROMPT = """你是资深国际关系研究学者。请为以下专题撰写一篇**论文式深度分析**。

专题名称：Target Series
专题简介：Target description

成员内容概述：

### [1] First title
First overview

### [2] Second title
Second overview


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
- 可以用小标题分段（不超过 5 个）"""


CASES = [
    (
        "generate_series_intro",
        "intro",
        INTRO_PROMPT,
        "你是知识专题策展人。导言用叙事语言，像博物馆引导词，告诉读者这个专题回答什么核心问题及各篇逻辑关系。",
        {
            "temperature": 0.5,
            "max_tokens": 1024,
            "timeout": 120,
            "module": "series",
            "task": "intro",
        },
        "专题成员不足，无法生成导言",
        "AI 导言生成失败",
    ),
    (
        "generate_series_summary",
        "summary",
        SUMMARY_PROMPT,
        "你是知识专题分析师。输出结构化的 Markdown 总结。关键洞察必须按专题简介承诺的分析维度逐一覆盖，每条标注维度标签（如 历史·、宗教·、政治·、经济·）。",
        {
            "temperature": 0.3,
            "max_tokens": 3072,
            "timeout": 120,
            "module": "series",
            "task": "summary",
        },
        "专题成员不足，无法生成总结",
        "AI 总结生成失败",
    ),
    (
        "generate_series_paper",
        "paper",
        PAPER_PROMPT,
        "你是资深国际关系研究学者。请撰写论文式深度分析：叙事弧线完整（开头→发展→高潮→结尾），论点-论据结构，连贯段落式写作，讲稿节奏。每个观点引用具体事件/数据并标注 [N]。输出纯 Markdown，全文 1500-2500 字。",
        {
            "temperature": 0.5,
            "max_tokens": 4096,
            "timeout": 180,
            "module": "series",
            "task": "paper",
        },
        "专题成员不足，无法生成论文",
        "AI 论文生成失败",
    ),
]


@pytest.mark.parametrize("function_name", [case[0] for case in CASES])
def test_generation_entrypoints_have_complete_service_types(function_name) -> None:
    service = _service()
    annotations = inspect.get_annotations(
        getattr(service, function_name), eval_str=True
    )

    assert annotations == {
        "series_id": str,
        "connect_fn": ConnectFn,
        "init_db_fn": InitDbFn,
        "chat_fn": getattr(service, "ChatFn", None),
        "return": dict[str, str],
    }


@pytest.mark.parametrize("function_name", [case[0] for case in CASES])
def test_missing_series_returns_404_and_initializes_database(
    series_db, function_name
) -> None:
    calls = []

    with pytest.raises(HTTPException) as error:
        _call(
            function_name,
            pytest.fail,
            init_db_fn=lambda: calls.append("init"),
        )

    assert calls == ["init"]
    assert error.value.status_code == 404
    assert error.value.detail == "专题不存在"


@pytest.mark.parametrize("function_name,detail", [(case[0], case[5]) for case in CASES])
@pytest.mark.parametrize("member_ids", [[], ["only-one"], "not-json"])
def test_malformed_or_insufficient_members_return_400(
    series_db, function_name, detail, member_ids
) -> None:
    _insert_series(member_ids)

    with pytest.raises(HTTPException) as error:
        _call(function_name, pytest.fail)

    assert error.value.status_code == 400
    assert error.value.detail == detail


@pytest.mark.parametrize(
    "function_name,field,expected_prompt,system_message,ai_arguments,_,__",
    CASES,
)
def test_generators_preserve_full_messages_ai_arguments_updates_and_response(
    series_db,
    function_name,
    field,
    expected_prompt,
    system_message,
    ai_arguments,
    _,
    __,
) -> None:
    _insert_event("event-1", "First title", "First overview")
    _insert_event("event-2", "Second title", "Second overview")
    _insert_series(["event-1", "event-2"])
    calls = []

    def chat(messages, **kwargs):
        calls.append((messages, kwargs))
        return "  generated output  \n"

    assert _call(function_name, chat) == {field: "generated output"}
    assert calls == [
        (
            [
                {"role": "system", "content": system_message},
                {"role": "user", "content": expected_prompt},
            ],
            ai_arguments,
        )
    ]
    with connect() as conn:
        row = conn.execute(
            f"SELECT {field}, updated_at FROM series WHERE id = 'series-1'"
        ).fetchone()
    assert row[field] == "generated output"
    assert re.fullmatch(r"\d{4}-\d{2}-\d{2} \d{2}:\d{2}", row["updated_at"])


@pytest.mark.parametrize(
    "function_name,field,_,__,___,____,empty_detail",
    CASES,
)
@pytest.mark.parametrize("empty_output", [None, ""])
def test_empty_ai_output_returns_500_without_updating_series(
    series_db,
    function_name,
    field,
    _,
    __,
    ___,
    ____,
    empty_detail,
    empty_output,
) -> None:
    _insert_event("event-1", "First title", "First overview")
    _insert_event("event-2", "Second title", "Second overview")
    _insert_series(["event-1", "event-2"])

    with pytest.raises(HTTPException) as error:
        _call(function_name, lambda *args, **kwargs: empty_output)

    assert error.value.status_code == 500
    assert error.value.detail == empty_detail
    with connect() as conn:
        row = conn.execute(
            f"SELECT {field}, updated_at FROM series WHERE id = 'series-1'"
        ).fetchone()
    assert row[field] is None
    assert row["updated_at"] is None


@pytest.mark.parametrize("function_name,field", [(case[0], case[1]) for case in CASES])
def test_member_query_order_and_connection_commit_boundaries_are_preserved(
    function_name, field
) -> None:
    events: list[Any] = []

    class Result:
        def __init__(self, *, one=None, all_rows=None):
            self.one = one
            self.all_rows = all_rows

        def fetchone(self):
            return self.one

        def fetchall(self):
            return self.all_rows

    class Connection:
        def __init__(self, label: str):
            self.label = label

        def execute(self, sql, params):
            events.append((self.label, "execute", sql, params))
            if sql.startswith("SELECT id, name"):
                return Result(
                    one={
                        "id": "series-1",
                        "name": "Target Series",
                        "description": "Target description",
                        "member_ids": '["event-2", "event-1"]',
                    }
                )
            if sql.startswith("SELECT title"):
                return Result(
                    all_rows=[
                        {"title": "First returned", "overview": "Overview A"},
                        {"title": "Second returned", "overview": "Overview B"},
                    ]
                )
            return Result()

    connection_count = 0

    @contextmanager
    def tracked_connect():
        nonlocal connection_count
        connection_count += 1
        label = f"connection-{connection_count}"
        events.append((label, "enter"))
        try:
            yield Connection(label)
        except Exception:
            events.append((label, "rollback"))
            raise
        else:
            events.append((label, "commit"))
        finally:
            events.append((label, "exit"))

    def chat(messages, **kwargs):
        assert events[-2:] == [
            ("connection-1", "commit"),
            ("connection-1", "exit"),
        ]
        prompt = messages[1]["content"]
        assert prompt.index("[1] First returned") < prompt.index("[2] Second returned")
        return " generated "

    assert _call(
        function_name,
        chat,
        connect_fn=tracked_connect,
        init_db_fn=lambda: events.append("init"),
    ) == {field: "generated"}
    assert events[0] == "init"
    assert events[2] == (
        "connection-1",
        "execute",
        "SELECT id, name, description, member_ids FROM series WHERE id = ?",
        ("series-1",),
    )
    assert events[3] == (
        "connection-1",
        "execute",
        "SELECT title, overview FROM events WHERE id IN (?,?)",
        ["event-2", "event-1"],
    )
    assert events[-2:] == [
        ("connection-2", "commit"),
        ("connection-2", "exit"),
    ]
    update = events[-3]
    assert update[0:3] == (
        "connection-2",
        "execute",
        f"UPDATE series SET {field} = ?, updated_at = ? WHERE id = ?",
    )
    assert update[3][0] == "generated"
    assert re.fullmatch(r"\d{4}-\d{2}-\d{2} \d{2}:\d{2}", update[3][1])
    assert update[3][2] == "series-1"


@pytest.mark.parametrize("function_name", [case[0] for case in CASES])
def test_ai_exceptions_propagate_without_opening_update_connection(
    series_db, function_name
) -> None:
    _insert_event("event-1", "First title", "First overview")
    _insert_event("event-2", "Second title", "Second overview")
    _insert_series(["event-1", "event-2"])
    connect_calls = 0

    def tracked_connect():
        nonlocal connect_calls
        connect_calls += 1
        return connect()

    def chat(*args, **kwargs):
        raise RuntimeError("chat failed")

    with pytest.raises(RuntimeError, match="chat failed"):
        _call(function_name, chat, connect_fn=tracked_connect)

    assert connect_calls == 1
