from __future__ import annotations

import json
from collections.abc import Callable
from typing import Any, Protocol

from fastapi import HTTPException

from .chain_node_service import ConnectFn

type ChatFn = Callable[..., str | None]


class AiUpdateRequest(Protocol):
    node_id: str
    source_text: str


def update_node_from_source(
    request: AiUpdateRequest,
    *,
    connect_fn: ConnectFn,
    chat_fn: ChatFn,
) -> dict[str, Any]:
    with connect_fn() as conn:
        conn.row_factory = _dict_factory
        node = conn.execute(
            "SELECT * FROM industry_chain_nodes WHERE id = ?", (request.node_id,)
        ).fetchone()
        if not node:
            raise HTTPException(status_code=404, detail="节点不存在")

        node["global_shares"] = json.loads(node["global_shares"])
        node["substitutes"] = json.loads(node["substitutes"])

    prompt = f"""你是一位产业链数据专家。以下是节点"{node['name']}"（{node['chain']}，{node['node_type']}）的当前数据：

{json.dumps(node['global_shares'], ensure_ascii=False, indent=2)}

现有替代方案：
{json.dumps(node['substitutes'], ensure_ascii=False, indent=2)}

---
## 来源文本（可能包含更新的数据）
{request.source_text[:4000]}
---

请从来源文本中提取与这个节点相关的结构化数据，按以下 JSON 格式返回：

```json
{{
  "global_shares": [
    {{"c": "国家名", "p": 产量占比, "p_export_global": 出口占全球出口, "p_export_ratio": 出口占产量比, "p_export_national": 占本国总出口, "d": 消费占比, "d_import_global": 进口占全球进口, "d_import_ratio": 进口占消费比, "d_import_national": 占本国总进口}}
  ],
  "substitutes": [
    {{"node": "替代品名", "maturity": "成熟度", "trigger": "触发条件", "advantage": "优势", "bottleneck": "瓶颈"}}
  ],
  "summary": "一句话总结本次更新了什么"
}}
```

规则：
1. 如果来源文本中没有提及某个国家，保留其原有数据不变，不要编造
2. 如果来源文本包含新的数据，用新数据覆盖对应字段
3. 如果来源文本与本节点无关，返回空的 global_shares 和 substitutes
4. 只输出 JSON，不要其他文字"""

    try:
        result = chat_fn(
            messages=[{"role": "user", "content": prompt}],
            temperature=0.1,
            max_tokens=2048,
            module="chain_data_update",
            task="ai_update",
        )
        if not result:
            return {"error": "AI 返回空结果"}

        result = result.strip()
        if "```json" in result:
            result = result.split("```json")[1].split("```")[0].strip()
        elif "```" in result:
            result = result.split("```")[1].split("```")[0].strip()

        extracted = json.loads(result)

        with connect_fn() as conn:
            new_shares = extracted.get("global_shares", [])
            new_substitutes = extracted.get("substitutes", [])

            if new_shares:
                conn.execute(
                    """UPDATE industry_chain_nodes
                       SET global_shares = ?, last_updated = datetime('now')
                       WHERE id = ?""",
                    (json.dumps(new_shares, ensure_ascii=False), request.node_id),
                )
            if new_substitutes:
                conn.execute(
                    """UPDATE industry_chain_nodes
                       SET substitutes = ?, last_updated = datetime('now')
                       WHERE id = ?""",
                    (
                        json.dumps(new_substitutes, ensure_ascii=False),
                        request.node_id,
                    ),
                )
            conn.commit()

        return {
            "ok": True,
            "summary": extracted.get("summary", ""),
            "updated_shares": len(new_shares) > 0,
            "updated_subs": len(new_substitutes) > 0,
            "global_shares": new_shares,
            "substitutes": new_substitutes,
        }
    except json.JSONDecodeError:
        return {"error": f"AI 返回格式无法解析: {result[:300]}"}
    except Exception as exc:
        return {"error": str(exc)}


def _dict_factory(cursor: Any, row: tuple[Any, ...]) -> dict[str, Any]:
    return dict(zip([column[0] for column in cursor.description], row))
