"""Knowledge Graph API — entity CRUD, graph data, path queries."""

from __future__ import annotations

import json as _json
import logging
import uuid

from fastapi import APIRouter

from ..db import connect

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/entities", tags=["knowledge-graph"])

ENTITY_TYPES = [
    "person", "organization", "location", "concept",
    "event", "theory", "book", "metric",
]

RELATION_TYPES = [
    "claims", "refutes", "extends", "causes",
    "belongs_to", "contrasts", "cites", "synergizes",
]


def _store_entities(event_id: str, entities: list, relations: list) -> None:
    """Write extracted entities and relations to the database.

    Deduplicates entities by name+type (hard match). Merges aliases.
    Newer entities update the summary if it was previously empty.
    """
    if not entities:
        return

    with connect() as conn:
        # Skip RSS-sourced events — knowledge graph only covers curated content
        row = conn.execute(
            "SELECT s.type FROM events e LEFT JOIN sources s ON e.source_id = s.id WHERE e.id = ?",
            (event_id,),
        ).fetchone()
        if row and row["type"] == "rss":
            logger.info("Skipping entity storage for RSS event %s", event_id)
            return

        for ent in entities:
            name = (ent.get("name") or "").strip()
            etype = (ent.get("type") or "concept").strip()
            summary = (ent.get("summary") or "").strip()[:200]
            category = (ent.get("category") or "").strip()

            if not name or etype not in ENTITY_TYPES:
                continue

            # Hard dedup: same name + type
            existing = conn.execute(
                "SELECT id, aliases_json, summary FROM entities WHERE name = ? AND type = ?",
                (name, etype),
            ).fetchone()

            if existing:
                eid = existing["id"]
                # Merge aliases
                try:
                    old_aliases = _json.loads(existing["aliases_json"])
                except (_json.JSONDecodeError, TypeError):
                    old_aliases = []
                conn.execute(
                    "UPDATE entities SET aliases_json = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
                    (_json.dumps(old_aliases), eid),
                )
                # Update summary if it was empty
                if not existing["summary"] and summary:
                    conn.execute(
                        "UPDATE entities SET summary = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
                        (summary, eid),
                    )
            else:
                eid = f"ent-{uuid.uuid4().hex[:12]}"
                conn.execute(
                    """INSERT INTO entities (id, name, type, aliases_json, summary, category)
                       VALUES (?, ?, ?, '[]', ?, ?)""",
                    (eid, name, etype, summary, category),
                )

            # Link event to entity
            conn.execute(
                "INSERT OR IGNORE INTO event_entities (event_id, entity_id, relevance, confidence)"
                " VALUES (?, ?, 'medium', 1.0)",
                (event_id, eid),
            )

        # Store relations
        for rel in relations:
            src = (rel.get("source") or "").strip()
            tgt = (rel.get("target") or "").strip()
            rtype = (rel.get("type") or "").strip()

            if not src or not tgt or rtype not in RELATION_TYPES:
                continue

            # Resolve entity names to IDs
            src_row = conn.execute(
                "SELECT id FROM entities WHERE name = ?", (src,)
            ).fetchone()
            tgt_row = conn.execute(
                "SELECT id FROM entities WHERE name = ?", (tgt,)
            ).fetchone()

            if not src_row or not tgt_row:
                continue

            # Avoid duplicates
            exists = conn.execute(
                """SELECT id FROM entity_relations
                   WHERE source_entity_id = ? AND target_entity_id = ? AND relation_type = ?""",
                (src_row["id"], tgt_row["id"], rtype),
            ).fetchone()

            if not exists:
                evidence = [{"event_id": event_id, "relevance": "medium"}]
                conn.execute(
                    """INSERT INTO entity_relations (source_entity_id, target_entity_id, relation_type, evidence_json)
                       VALUES (?, ?, ?, ?)""",
                    (src_row["id"], tgt_row["id"], rtype, _json.dumps(evidence)),
                )

    logger.info(
        "Stored %d entities + %d relations for event %s",
        len(entities), len(relations), event_id,
    )


# ── API Routes ──


@router.get("/graph")
def get_graph_data(limit: int = 200):
    """Return full graph data: nodes (entities) + edges (relations).

    Includes event_entities counts for node sizing.
    """
    with connect() as conn:
        entities = conn.execute(
            """SELECT e.id, e.name, e.type, e.summary, e.category,
                      (SELECT COUNT(*) FROM event_entities ee WHERE ee.entity_id = e.id) as event_count,
                      (SELECT COUNT(*) FROM entity_relations er WHERE er.source_entity_id = e.id OR er.target_entity_id = e.id) as relation_count
               FROM entities e
               ORDER BY relation_count DESC, event_count DESC
               LIMIT ?""",
            (limit,),
        ).fetchall()

        relations = conn.execute(
            """SELECT er.id, er.source_entity_id, er.target_entity_id, er.relation_type, er.weight
               FROM entity_relations er
               INNER JOIN entities e1 ON e1.id = er.source_entity_id
               INNER JOIN entities e2 ON e2.id = er.target_entity_id
               ORDER BY er.weight DESC
               LIMIT ?""",
            (limit * 3,),
        ).fetchall()

    nodes = [
        {
            "id": r["id"],
            "name": r["name"],
            "type": r["type"],
            "summary": r["summary"] or "",
            "category": r["category"] or "",
            "event_count": r["event_count"],
            "relation_count": r["relation_count"],
        }
        for r in entities
    ]

    edges = [
        {
            "id": str(r["id"]),
            "source": r["source_entity_id"],
            "target": r["target_entity_id"],
            "type": r["relation_type"],
            "weight": r["weight"],
        }
        for r in relations
    ]

    return {"nodes": nodes, "edges": edges}


@router.get("/graph/entity/{entity_id}")
def get_entity_detail(entity_id: str):
    """Get entity detail with related events, entities, and relations."""
    with connect() as conn:
        entity = conn.execute(
            """SELECT e.*,
                      (SELECT COUNT(*) FROM event_entities ee WHERE ee.entity_id = e.id) as event_count
               FROM entities e WHERE e.id = ?""",
            (entity_id,),
        ).fetchone()

        if not entity:
            return {"error": "Entity not found"}, 404

        # Related events
        events = conn.execute(
            """SELECT ev.id, ev.title, ev.topic, ev.status, ev.overview, ee.relevance
               FROM event_entities ee
               INNER JOIN events ev ON ev.id = ee.event_id
               WHERE ee.entity_id = ?
               ORDER BY ev.created_at DESC LIMIT 20""",
            (entity_id,),
        ).fetchall()

        # Related entities (connected via relations)
        related = conn.execute(
            """SELECT
                 CASE WHEN er.source_entity_id = ? THEN er.target_entity_id ELSE er.source_entity_id END as other_id,
                 CASE WHEN er.source_entity_id = ? THEN er.relation_type ELSE NULL END as out_type,
                 CASE WHEN er.target_entity_id = ? THEN er.relation_type ELSE NULL END as in_type,
                 er.weight
               FROM entity_relations er
               WHERE er.source_entity_id = ? OR er.target_entity_id = ?
               ORDER BY er.weight DESC LIMIT 30""",
            (entity_id, entity_id, entity_id, entity_id, entity_id),
        ).fetchall()

        # Get names for related entities
        related_ids = {r["other_id"] for r in related}
        name_map = {}
        if related_ids:
            placeholders = ",".join("?" * len(related_ids))
            name_rows = conn.execute(
                f"SELECT id, name, type FROM entities WHERE id IN ({placeholders})",
                tuple(related_ids),
            ).fetchall()
            name_map = {r["id"]: {"name": r["name"], "type": r["type"]} for r in name_rows}

    return {
        "entity": {
            "id": entity["id"],
            "name": entity["name"],
            "type": entity["type"],
            "summary": entity["summary"] or "",
            "category": entity["category"] or "",
            "aliases": _json.loads(entity["aliases_json"]) if entity["aliases_json"] else [],
            "first_seen_at": entity["first_seen_at"],
            "event_count": entity["event_count"],
        },
        "events": [
            {
                "id": e["id"],
                "title": e["title"],
                "topic": e["topic"] or "",
                "status": e["status"],
                "overview": (e["overview"] or "")[:200],
                "relevance": e["relevance"],
            }
            for e in events
        ],
        "related_entities": [
            {
                "id": r["other_id"],
                "name": name_map.get(r["other_id"], {}).get("name", r["other_id"]),
                "type": name_map.get(r["other_id"], {}).get("type", ""),
                "relation_type": r["out_type"] or r["in_type"] or "",
                "direction": "out" if r["out_type"] else "in",
                "weight": r["weight"],
            }
            for r in related
            if r["other_id"] in name_map
        ],
    }


@router.get("/graph/path")
def find_path(source_id: str, target_id: str):
    """Find the shortest path between two entities (BFS up to depth 4)."""
    with connect() as conn:
        # Verify both entities exist
        s = conn.execute("SELECT name FROM entities WHERE id = ?", (source_id,)).fetchone()
        t = conn.execute("SELECT name FROM entities WHERE id = ?", (target_id,)).fetchone()
        if not s or not t:
            return {"error": "Entity not found"}, 404

        # Build adjacency list (undirected)
        rows = conn.execute(
            "SELECT source_entity_id, target_entity_id, relation_type FROM entity_relations"
        ).fetchall()

    adj: dict[str, list[tuple[str, str]]] = {}
    for r in rows:
        adj.setdefault(r["source_entity_id"], []).append((r["target_entity_id"], r["relation_type"]))
        adj.setdefault(r["target_entity_id"], []).append((r["source_entity_id"], r["relation_type"]))

    # BFS
    from collections import deque
    queue: deque = deque([(source_id, [source_id], [])])
    visited = {source_id}

    while queue:
        node, path_ids, path_types = queue.popleft()
        if len(path_ids) > 5:  # max depth
            continue
        if node == target_id:
            # Resolve entity names
            with connect() as conn:
                name_rows = conn.execute(
                    f"SELECT id, name, type FROM entities WHERE id IN ({','.join('?'*len(path_ids))})",
                    tuple(path_ids),
                ).fetchall()
                names = {r["id"]: {"name": r["name"], "type": r["type"]} for r in name_rows}

            return {
                "found": True,
                "path": [
                    {
                        "entity_id": pid,
                        "name": names.get(pid, {}).get("name", pid),
                        "type": names.get(pid, {}).get("type", ""),
                        "relation_to_next": path_types[i] if i < len(path_types) else None,
                    }
                    for i, pid in enumerate(path_ids)
                ],
            }

        for neighbor, rtype in adj.get(node, []):
            if neighbor not in visited:
                visited.add(neighbor)
                queue.append((neighbor, path_ids + [neighbor], path_types + [rtype]))

    return {"found": False, "path": []}


@router.get("/graph/series/{series_id}")
def get_series_graph(series_id: str):
    """Get knowledge graph filtered to entities within a series."""
    with connect() as conn:
        # Get member event IDs
        series = conn.execute(
            "SELECT member_ids FROM series WHERE id = ?", (series_id,)
        ).fetchone()
        if not series:
            return {"error": "Series not found"}, 404

        try:
            member_ids = _json.loads(series["member_ids"])
        except (_json.JSONDecodeError, TypeError):
            member_ids = []

        if not member_ids:
            return {"nodes": [], "edges": []}

        # Entities from these events
        placeholders = ",".join("?" * len(member_ids))
        entity_ids = {
            r[0]
            for r in conn.execute(
                f"SELECT DISTINCT entity_id FROM event_entities WHERE event_id IN ({placeholders})",
                tuple(member_ids),
            ).fetchall()
        }

        if not entity_ids:
            return {"nodes": [], "edges": []}

        # Nodes
        e_placeholders = ",".join("?" * len(entity_ids))
        nodes = conn.execute(
            f"SELECT id, name, type, summary, category FROM entities WHERE id IN ({e_placeholders})",
            tuple(entity_ids),
        ).fetchall()

        # Edges (only if both entities are in the set)
        edges = conn.execute(
            f"""SELECT id, source_entity_id, target_entity_id, relation_type, weight
                FROM entity_relations
                WHERE source_entity_id IN ({e_placeholders})
                  AND target_entity_id IN ({e_placeholders})""",
            tuple(entity_ids) + tuple(entity_ids),
        ).fetchall()

    return {
        "nodes": [
            {"id": r["id"], "name": r["name"], "type": r["type"],
             "summary": r["summary"] or "", "category": r["category"] or ""}
            for r in nodes
        ],
        "edges": [
            {"id": str(r["id"]), "source": r["source_entity_id"], "target": r["target_entity_id"],
             "type": r["relation_type"], "weight": r["weight"]}
            for r in edges
        ],
    }


@router.get("/search")
def search_entities(q: str = "", limit: int = 20):
    """Search entities by name (LIKE match)."""
    if not q:
        return {"results": []}

    with connect() as conn:
        rows = conn.execute(
            """SELECT id, name, type, summary, category FROM entities
               WHERE name LIKE ? OR aliases_json LIKE ?
               ORDER BY name LIMIT ?""",
            (f"%{q}%", f"%{q}%", limit),
        ).fetchall()

    return {
        "results": [
            {"id": r["id"], "name": r["name"], "type": r["type"],
             "summary": r["summary"] or "", "category": r["category"] or ""}
            for r in rows
        ],
    }


@router.get("/stats")
def get_graph_stats():
    """Get knowledge graph statistics."""
    with connect() as conn:
        total_entities = conn.execute("SELECT COUNT(*) FROM entities").fetchone()[0]
        total_relations = conn.execute("SELECT COUNT(*) FROM entity_relations").fetchone()[0]
        total_links = conn.execute("SELECT COUNT(*) FROM event_entities").fetchone()[0]

        type_counts = conn.execute(
            "SELECT type, COUNT(*) as cnt FROM entities GROUP BY type ORDER BY cnt DESC"
        ).fetchall()

        relation_counts = conn.execute(
            "SELECT relation_type, COUNT(*) as cnt FROM entity_relations GROUP BY relation_type ORDER BY cnt DESC"
        ).fetchall()

    return {
        "total_entities": total_entities,
        "total_relations": total_relations,
        "total_event_links": total_links,
        "by_type": [{"type": r["type"], "count": r["cnt"]} for r in type_counts],
        "by_relation": [{"type": r["relation_type"], "count": r["cnt"]} for r in relation_counts],
    }


@router.get("/graph/entity/{entity_id}/insight")
def get_entity_insight(entity_id: str):
    """Generate constructive analysis for an entity based on its associated content.

    Collects the entity's profile, linked events with their summaries, and
    related entities with relationship types, then asks the AI to produce
    actionable insights in structured markdown.
    """
    from ..ai_client import chat

    with connect() as conn:
        entity = conn.execute(
            "SELECT id, name, type, summary, category FROM entities WHERE id = ?",
            (entity_id,),
        ).fetchone()
        if not entity:
            return {"error": "Entity not found"}, 404

        # Linked events with overview/summary
        events = conn.execute(
            """SELECT ev.title, ev.overview, ev.ai_summary, ev.topic, ev.status
               FROM event_entities ee
               JOIN events ev ON ev.id = ee.event_id
               WHERE ee.entity_id = ?
               ORDER BY ev.created_at DESC LIMIT 15""",
            (entity_id,),
        ).fetchall()

        # Related entities with relationship types
        related = conn.execute(
            """SELECT DISTINCT
                 CASE WHEN er.source_entity_id = ? THEN e2.name ELSE e1.name END as other_name,
                 CASE WHEN er.source_entity_id = ? THEN e2.type ELSE e1.type END as other_type,
                 er.relation_type
               FROM entity_relations er
               JOIN entities e1 ON e1.id = er.source_entity_id
               JOIN entities e2 ON e2.id = er.target_entity_id
               WHERE er.source_entity_id = ? OR er.target_entity_id = ?
               LIMIT 30""",
            (entity_id, entity_id, entity_id, entity_id),
        ).fetchall()

    # Build context for AI
    lines = [
        f"## 实体信息",
        f"- 名称: {entity['name']}",
        f"- 类型: {entity['type']}",
        f"- 摘要: {entity['summary'] or '无'}",
        f"- 所属类别: {entity['category'] or '无'}",
    ]

    if events:
        lines.append("\n## 关联内容")
        for i, ev in enumerate(events, 1):
            summary = ev["overview"] or ev["ai_summary"] or ""
            summary = summary[:300] + "..." if len(summary) > 300 else summary
            lines.append(f"\n### [{i}] {ev['title']}")
            lines.append(f"- 主题: {ev['topic'] or '无'}")
            if summary:
                lines.append(f"- 内容: {summary}")

    if related:
        lines.append("\n## 关联实体与关系")
        for r in related:
            lines.append(f"- {r['other_name']}（{r['other_type']}）— {r['relation_type']}")

    context = "\n".join(lines)

    system_prompt = """你是一位知识分析专家。请基于提供的实体信息及其关联内容和关联实体，进行建设性思考，输出结构化分析。

要求：
1. 使用 Markdown 格式
2. 包含以下板块（有内容才写，没有则跳过）：
   - **核心定位**：一句话总结该实体在知识网络中的角色
   - **关键洞察**：2-4 条基于关联内容的深度发现
   - **脉络关联**：该实体与其他实体的关系揭示了什么模式
   - **待探索方向**：2-3 个值得深入研究的问题或方向
3. 语言精炼，避免空话套话
4. 每个洞察要有具体内容支撑，不要泛泛而谈"""

    raw = chat(
        [{"role": "system", "content": system_prompt}, {"role": "user", "content": context}],
        temperature=0.5,
        max_tokens=2048,
        timeout=90,
        module="knowledge_graph",
        task="entity_insight",
    )

    if not raw:
        return {"error": "AI analysis unavailable"}, 503

    return {"insight": raw.strip()}
