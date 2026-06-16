# 辅导中心 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在 KI 内构建独立的「辅导中心」模块——将 6 个 Hermes study skills 的核心逻辑（prompt 模板 + 工作流）迁移到 KI 后端，用 DeepSeek v4 生成讲题稿（孩子版 + 家长版），并生成 MD/HTML/PDF 三格式产物。

**Architecture:** 独立数据表 `study_materials` 与 KI 现有 `events` 完全隔离；独立路由 `study_routes.py`；前端三个新页面（列表/详情/错题本）；HTML 模板引擎用 Python 字符串模板 + AI 填内容；PDF 用 Chrome headless subprocess 生成；OCR 复用现有 swift 脚本。

**Tech Stack:** FastAPI + React/Vite + TailwindCSS + SQLite（同 KI），Python `string.Template`，Chrome headless，macOS Vision framework（sips + swift OCR）

---

## 文件结构

```
Create:
  app/backend/routes/study_routes.py      — 辅导中心全部 API 端点
  app/backend/study/
    __init__.py
    prompts.py                            — 各学科 prompt 模板
    templates.py                          — HTML 模板引擎（语文/数学/英语三套）
    pipeline.py                           — 生成管线（OCR→AI 讲解→格式渲染→PDF）
  app/frontend/src/pages/Study.tsx        — 辅导中心列表页
  app/frontend/src/pages/StudyDetail.tsx  — 讲题详情页（孩子版/家长版 + 格式切换）
  app/frontend/src/pages/StudyMistakes.tsx— 错题本

Modify:
  app/backend/db.py                       — 新增 study_materials 表 + 索引
  app/backend/main.py                     — 注册 study_router
  app/backend/config_manager.py           — 新增 study 模块默认配置
  app/frontend/src/App.tsx                — 注册三个路由
  app/frontend/src/components/Sidebar.tsx — 新增「辅导中心」入口
  app/frontend/src/components/BottomTabBar.tsx — 同步入口
  app/frontend/src/pages/SystemDoc.tsx    — 更新功能体系
```

---

## Phase 0 — 数据模型与基础设施（Task 1-3）

### Task 1: 数据库表与索引

**Files:**
- Modify: `app/backend/db.py`

- [ ] **Step 1: 在 `init_db` 中新增 `study_materials` 表**

在 `init_db()` 函数末尾的 `conn.executescript` 块中添加：

```python
# 辅导中心 — 学习资料
conn.executescript("""
    CREATE TABLE IF NOT EXISTS study_materials (
        id              TEXT PRIMARY KEY,
        subject         TEXT NOT NULL DEFAULT '',
        grade           TEXT DEFAULT '',
        study_type      TEXT NOT NULL DEFAULT '',
        title           TEXT NOT NULL DEFAULT '',
        source_type     TEXT DEFAULT 'manual',
        raw_content     TEXT DEFAULT '',
        child_version   TEXT DEFAULT '',
        parent_version  TEXT DEFAULT '',
        formats_json    TEXT DEFAULT '{}',
        status          TEXT DEFAULT 'draft',
        score           INTEGER,
        is_correct      INTEGER,
        mistake_tags    TEXT DEFAULT '[]',
        tags_json       TEXT DEFAULT '[]',
        created_at      TEXT NOT NULL DEFAULT (datetime('now')),
        updated_at      TEXT NOT NULL DEFAULT (datetime('now'))
    );
    CREATE INDEX IF NOT EXISTS idx_study_subject
        ON study_materials(subject);
    CREATE INDEX IF NOT EXISTS idx_study_type
        ON study_materials(study_type);
    CREATE INDEX IF NOT EXISTS idx_study_status
        ON study_materials(status);
    CREATE INDEX IF NOT EXISTS idx_study_created
        ON study_materials(created_at);
""")
```

- [ ] **Step 2: 重启服务验证建表**

```bash
lsof -ti:9120 | xargs kill -9 && sleep 1
cd app && python -m uvicorn backend.main:app --host 0.0.0.0 --port 9120
```

验证：
```bash
sqlite3 data/intelligence.sqlite ".schema study_materials"
```

- [ ] **Step 3: Commit**

```bash
git add app/backend/db.py
git commit -m "feat: 新增 study_materials 表，辅导中心数据模型"
```

---

### Task 2: Prompt 模板提取

**Files:**
- Create: `app/backend/study/__init__.py`
- Create: `app/backend/study/prompts.py`

- [ ] **Step 1: 创建 `study/prompts.py`**

```python
"""辅导中心 — DeepSeek prompt 模板（提取自 Hermes study skills）"""

# ── 分流规则 ──

SUBJECT_TYPE_MAP = {
    "语文": ["阅读理解", "作文", "看图写话", "仿写", "句子训练"],
    "数学": ["应用题", "计算题", "几何题", "单位换算", "行程问题"],
    "英语": ["阅读理解", "完形填空", "单词", "语法", "翻译", "写作"],
}

# ── 阅读理解 — 语文（reading-comprehension-pipeline） ──

READING_CHINESE_SYSTEM = """你是小学语文阅读理解辅导专家。你的任务是根据原文和题目，生成完整的讲题稿。
讲题稿包含孩子版（可直接给孩子看）和家长版（供家长辅导用）。"""

READING_CHINESE_USER = """请为以下阅读理解生成完整讲题稿。

## 原文
{raw_content}

{extra_instructions}

## 输出格式要求

请按以下结构输出 Markdown（用 ## 标题）：

## 一、原文
（原样保留）

## 二、题目
（逐题列出，纯净排版）

## 三、逐题讲解
每题包含：
### 第N题
#### 参考答案
（贴近老师标准，语言简洁）
#### 详细解题思路
按以下顺序展开：
1. 这道题考什么
2. 先看题干，圈出关键词
3. 回原文哪里找答案
4. 关键词/关键句是什么
5. 为什么答案是这个
6. 答案是怎么组织语言的
7. 易错点
8. 家长怎么讲（逐句引导话术）
9. 这类题以后怎么做
{child_answer_section}

## 四、适合直接誊写的整洁答案
（只放最终答案，不混入讲解内容）
"""

# ── 数学应用题（math-word-problem-coach） ──

MATH_SYSTEM = """你是小学数学辅导专家。你的任务是讲解数学题，不仅要给答案，更要讲清楚「怎么列式」「为什么这样算」。
目标是让孩子能学会方法，让家长能直接拿去讲。"""

MATH_USER = """请为以下数学题生成完整讲题稿。

## 题目
{raw_content}

{extra_instructions}

## 输出格式要求

## 一、题目

## 二、逐题讲解
每题包含：
### 第N题
#### 题目分析
- 考什么
- 已知条件
- 要求什么
#### 解题思路
（先算什么，为什么）
#### 列式 / 计算过程
（每一步都写清楚）
#### 最终答案
（带单位）
#### 易错提醒
#### 家长怎么讲
{child_answer_section}

## 三、同类题方法总结
"""

# ── 英语辅导（english-study-coach） ──

ENGLISH_SYSTEM = """你是小学英语辅导专家。你的任务是讲解英语练习题，默认提供中英对照。
讲解以学生能懂为准，不堆语法术语。"""

ENGLISH_USER = """请为以下英语练习生成完整讲题稿。

## 原文/题目
{raw_content}

{extra_instructions}

## 输出格式要求

## 一、原文（含中文对照）
（按句或自然语块，英文原句 + 中文意思）

## 二、题目（含中文翻译）

## 三、逐题讲解
每题包含：
### 第N题
- 题型判断
- 题目翻译
- 正确答案
- 为什么选这个 / 为什么这样判断
- 关键句定位（英文原句 + 中文）
- 易错提醒
- 生词短语补充
{child_answer_section}

## 四、可直接誊写的整洁答案
"""

# ── 错题复盘（mistake-review-coach） ──

MISTAKE_SYSTEM = """你是学习辅导专家。你的任务是分析错题，找出真正的错因，并给出举一反三的同类练习。
不要只说「粗心」——要找知识点或步骤层面的真正问题。"""

MISTAKE_USER = """请分析以下错题，生成错题复盘讲义。

## 错题信息
原题: {raw_content}
正确答案: {correct_answer}
孩子作答: {child_answer}

## 输出格式

## 一、原题回顾

## 二、错因分析
（区分：审题错误 / 概念不清 / 计算失误 / 表达不完整 / 粗心）

## 三、正确做法

## 四、方法总结

## 五、举一反三（1-3道同类练习）
"""
```

- [ ] **Step 2: Commit**

```bash
git add app/backend/study/
git commit -m "feat: 辅导中心 prompt 模板 — 语文/数学/英语/错题"
```

---

### Task 3: HTML 模板引擎

**Files:**
- Create: `app/backend/study/templates.py`

- [ ] **Step 1: 创建三套 HTML 模板**

```python
"""辅导中心 — HTML 讲题稿模板引擎"""

# ── 语文讲题稿 HTML ──

CHINESE_STUDY_HTML = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<title>{title}</title>
<style>
  @page {{ size: A4; margin: 16mm 14mm; }}
  body {{ font-family: "PingFang SC", "Hiragino Sans GB", sans-serif; font-size: 14px; line-height: 1.9; color: #1a1a1a; max-width: 700px; margin: 0 auto; }}
  h1 {{ font-size: 22px; text-align: center; margin: 24px 0 32px; color: #111; }}
  h2 {{ font-size: 18px; margin: 28px 0 14px; padding-bottom: 6px; border-bottom: 2px solid #e0e0e0; color: #333; }}
  h3 {{ font-size: 16px; margin: 20px 0 10px; color: #444; }}
  h4 {{ font-size: 14px; margin: 12px 0 6px; color: #555; }}
  .passage {{ background: #fafafa; padding: 20px; border-radius: 8px; margin: 16px 0; line-height: 2; }}
  .question-block {{ margin: 24px 0; padding-left: 12px; border-left: 3px solid #d0d0d0; }}
  .answer {{ background: #f6f9fc; padding: 14px 18px; border-radius: 6px; margin: 12px 0; border-left: 3px solid #4a90d9; }}
  .answer-label {{ font-size: 12px; color: #4a90d9; font-weight: 600; margin-bottom: 6px; }}
  .detail {{ margin: 10px 0; padding: 12px 14px; background: #fefefe; border-radius: 4px; }}
  .detail-item {{ margin: 6px 0; }}
  .mistake {{ background: #fff8f0; padding: 10px 14px; border-radius: 4px; margin: 8px 0; border-left: 3px solid #e8962e; }}
  .tip {{ background: #f0f7f4; padding: 10px 14px; border-radius: 4px; margin: 8px 0; border-left: 3px solid #5ba88c; }}
  .clean-answers {{ margin-top: 32px; padding: 16px 20px; background: #fafafa; border-radius: 8px; }}
  .clean-answers h3 {{ margin-top: 0; }}
  .clean-answers p {{ margin: 6px 0; padding-left: 1em; text-indent: -1em; }}
  @media print {{ body {{ font-size: 13px; }} }}
</style>
</head>
<body>
<h1>{title}</h1>
{body}
</body>
</html>"""

# ── 数学讲题稿 HTML ──

MATH_STUDY_HTML = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<title>{title}</title>
<style>
  @page {{ size: A4; margin: 16mm 14mm; }}
  body {{ font-family: "PingFang SC", "Hiragino Sans GB", sans-serif; font-size: 14px; line-height: 1.9; color: #1a1a1a; max-width: 700px; margin: 0 auto; }}
  h1 {{ font-size: 22px; text-align: center; margin: 24px 0 32px; }}
  h2 {{ font-size: 18px; margin: 28px 0 14px; padding-bottom: 6px; border-bottom: 2px solid #e0e0e0; }}
  h3 {{ font-size: 16px; margin: 20px 0 10px; }}
  .problem {{ background: #fafafa; padding: 16px 20px; border-radius: 8px; margin: 16px 0; }}
  .steps {{ margin: 12px 0; padding: 14px 18px; background: #f6f9fc; border-radius: 6px; border-left: 3px solid #3b82f6; }}
  .step {{ margin: 8px 0; }}
  .formula {{ font-family: "Times New Roman", serif; font-size: 15px; background: #eef2ff; padding: 2px 8px; border-radius: 3px; }}
  .answer-box {{ background: #f0fdf4; padding: 12px 16px; border-radius: 6px; margin: 10px 0; border-left: 3px solid #22c55e; }}
  .final-answer {{ font-size: 18px; font-weight: 700; color: #166534; }}
  .mistake {{ background: #fff8f0; padding: 10px 14px; border-radius: 4px; margin: 8px 0; border-left: 3px solid #e8962e; }}
  .tip {{ background: #f0f7f4; padding: 10px 14px; border-radius: 4px; margin: 8px 0; border-left: 3px solid #5ba88c; }}
  @media print {{ body {{ font-size: 13px; }} }}
</style>
</head>
<body>
<h1>{title}</h1>
{body}
</body>
</html>"""

# ── 英语讲题稿 HTML（参照 Unit4 范本） ──

ENGLISH_STUDY_HTML = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<title>{title}</title>
<style>
  @page {{ size: A4; margin: 12mm 11mm; }}
  body {{ font-family: "Times New Roman", "PingFang SC", sans-serif; font-size: 13px; line-height: 1.8; color: #1a1a1a; max-width: 750px; margin: 0 auto; }}
  h1 {{ font-size: 20px; text-align: center; margin: 20px 0 24px; color: #16829c; }}
  h2 {{ font-size: 16px; margin: 24px 0 12px; color: #16829c; border-bottom: 1px solid #95d8e1; padding-bottom: 4px; }}
  h3 {{ font-size: 14px; margin: 16px 0 8px; color: #0d5c6e; }}
  .sheet {{ background: #f8fcfd; padding: 18px; border: 1px solid #95d8e1; border-radius: 6px; margin: 16px 0; }}
  .q {{ background: #f0f4f5; padding: 12px 14px; margin: 10px 0; border-radius: 4px; border-left: 3px solid #76c7d3; }}
  .answer {{ background: #e6f9f2; padding: 12px 14px; margin: 10px 0; border-radius: 4px; border-left: 3px solid #5ba88c; }}
  .answer-label {{ font-size: 11px; color: #5ba88c; font-weight: 700; text-transform: uppercase; margin-bottom: 4px; }}
  .tip {{ background: #fff8e8; padding: 10px 14px; margin: 8px 0; border-radius: 4px; border-left: 3px solid #e8962e; }}
  .tip-label {{ font-size: 11px; color: #e8962e; font-weight: 700; }}
  .en {{ font-family: "Times New Roman", serif; font-style: italic; }}
  .cn {{ color: #555; }}
  .vocab {{ display: inline-block; background: #eef2ff; padding: 1px 6px; border-radius: 3px; margin: 2px; font-size: 12px; }}
  .clean-answers {{ margin-top: 28px; padding: 14px 18px; background: #fafafa; border-radius: 6px; }}
  @media print {{ body {{ font-size: 12px; }} }}
</style>
</head>
<body>
<h1>{title}</h1>
{body}
</body>
</html>"""


def render_chinese_html(title: str, body_html: str) -> str:
    return CHINESE_STUDY_HTML.format(title=title, body=body_html)


def render_math_html(title: str, body_html: str) -> str:
    return MATH_STUDY_HTML.format(title=title, body=body_html)


def render_english_html(title: str, body_html: str) -> str:
    return ENGLISH_STUDY_HTML.format(title=title, body=body_html)


def render_html(subject: str, title: str, body_html: str) -> str:
    """根据学科选择对应 HTML 模板"""
    if subject == "英语":
        return render_english_html(title, body_html)
    elif subject == "数学":
        return render_math_html(title, body_html)
    else:
        return render_chinese_html(title, body_html)
```

- [ ] **Step 2: Commit**

```bash
git add app/backend/study/templates.py
git commit -m "feat: 辅导中心 HTML 模板引擎 — 语文/数学/英语三套样式"
```

---

## Phase 1 — 后端 API（Task 4-6）

### Task 4: study_routes.py — CRUD 端点

**Files:**
- Create: `app/backend/routes/study_routes.py`

- [ ] **Step 1: 创建路由文件**

```python
"""辅导中心 API — CRUD + 统计"""

from __future__ import annotations

import json
import logging
import uuid
from pathlib import Path

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from ..db import connect, init_db

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/study", tags=["study"])

# ── 请求模型 ──

class StudyCreateRequest(BaseModel):
    subject: str
    study_type: str
    title: str = ""
    raw_content: str = ""
    grade: str = ""
    source_type: str = "manual"

class StudyUpdateRequest(BaseModel):
    title: str | None = None
    subject: str | None = None
    grade: str | None = None
    study_type: str | None = None
    score: int | None = None
    is_correct: int | None = None
    status: str | None = None

class StudyMistakeRequest(BaseModel):
    correct_answer: str = ""
    child_answer: str = ""


# ── 列表 ──

@router.get("/list")
def list_materials(
    subject: str = Query(""),
    study_type: str = Query(""),
    status: str = Query(""),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
):
    """列出学习资料，支持按学科/题型/状态筛选"""
    init_db()
    conditions = []
    params: dict = {}

    if subject:
        conditions.append("subject = :subject")
        params["subject"] = subject
    if study_type:
        conditions.append("study_type = :study_type")
        params["study_type"] = study_type
    if status:
        conditions.append("status = :status")
        params["status"] = status

    where = " AND ".join(conditions) if conditions else "1=1"
    offset = (page - 1) * page_size

    with connect() as conn:
        total = conn.execute(
            f"SELECT COUNT(*) FROM study_materials WHERE {where}", params
        ).fetchone()[0]

        rows = conn.execute(
            f"""SELECT id, subject, grade, study_type, title, source_type,
                       status, score, is_correct, created_at, updated_at
                FROM study_materials
                WHERE {where}
                ORDER BY created_at DESC
                LIMIT :limit OFFSET :offset""",
            {**params, "limit": page_size, "offset": offset},
        ).fetchall()

    return {
        "items": [dict(r) for r in rows],
        "total": total,
        "page": page,
        "page_size": page_size,
    }


# ── 详情 ──

@router.get("/{material_id}")
def get_material(material_id: str):
    """获取学习资料完整详情（含孩子版/家长版/格式）"""
    init_db()
    with connect() as conn:
        row = conn.execute(
            "SELECT * FROM study_materials WHERE id = ?", (material_id,)
        ).fetchone()

    if not row:
        raise HTTPException(status_code=404, detail="资料不存在")

    d = dict(row)
    for field in ("formats_json", "mistake_tags", "tags_json"):
        try:
            d[field] = json.loads(d[field])
        except (json.JSONDecodeError, TypeError):
            d[field] = {}
    return d


# ── 创建 ──

@router.post("/create")
def create_material(req: StudyCreateRequest):
    """提交学习资料（手动录入或文件上传后调用）"""
    init_db()
    material_id = f"study-{uuid.uuid4().hex[:12]}"

    with connect() as conn:
        conn.execute(
            """INSERT INTO study_materials
               (id, subject, grade, study_type, title, source_type, raw_content, status)
               VALUES (?, ?, ?, ?, ?, ?, ?, 'draft')""",
            (material_id, req.subject, req.grade, req.study_type,
             req.title or "未命名", req.source_type, req.raw_content),
        )

    return {
        "material_id": material_id,
        "status": "draft",
    }


# ── 更新 ──

@router.put("/{material_id}")
def update_material(material_id: str, req: StudyUpdateRequest):
    """更新学习资料（批改、标注对错等）"""
    init_db()
    updates = {}
    for field in ("title", "subject", "grade", "study_type", "score", "is_correct", "status"):
        val = getattr(req, field, None)
        if val is not None:
            updates[field] = val

    if not updates:
        return {"updated": material_id, "fields": []}

    updates["updated_at"] = None  # trigger DEFAULT

    set_clause = ", ".join(
        f"{k} = :{k}" for k in updates
    ).replace("updated_at = :updated_at", "updated_at = datetime('now')")
    params = {k: v for k, v in updates.items() if v is not None}

    with connect() as conn:
        conn.execute(
            f"UPDATE study_materials SET {set_clause} WHERE id = :id",
            {**params, "id": material_id},
        )

    return {"updated": material_id, "fields": list(updates.keys())}


# ── 删除 ──

@router.delete("/{material_id}")
def delete_material(material_id: str):
    """删除学习资料"""
    init_db()
    with connect() as conn:
        conn.execute("DELETE FROM study_materials WHERE id = ?", (material_id,))
    return {"deleted": material_id}


# ── 错题本 ──

@router.get("/mistakes/list")
def list_mistakes(
    subject: str = Query(""),
    page: int = Query(1, ge=1),
    page_size: int = Query(50),
):
    """列出错题（is_correct = 0）"""
    init_db()
    conditions = ["is_correct = 0"]
    params: dict = {}

    if subject:
        conditions.append("subject = :subject")
        params["subject"] = subject

    where = " AND ".join(conditions)
    offset = (page - 1) * page_size

    with connect() as conn:
        total = conn.execute(
            f"SELECT COUNT(*) FROM study_materials WHERE {where}", params
        ).fetchone()[0]

        rows = conn.execute(
            f"""SELECT id, subject, grade, study_type, title, score,
                       mistake_tags, created_at
                FROM study_materials
                WHERE {where}
                ORDER BY created_at DESC
                LIMIT :limit OFFSET :offset""",
            {**params, "limit": page_size, "offset": offset},
        ).fetchall()

    items = []
    for r in rows:
        d = dict(r)
        try:
            d["mistake_tags"] = json.loads(d["mistake_tags"])
        except Exception:
            d["mistake_tags"] = []
        items.append(d)

    return {"items": items, "total": total, "page": page}


# ── 统计 ──

@router.get("/stats")
def get_stats():
    """各科统计 + 正确率"""
    init_db()
    with connect() as conn:
        rows = conn.execute(
            """SELECT subject,
                      COUNT(*) as total,
                      SUM(CASE WHEN is_correct = 1 THEN 1 ELSE 0 END) as correct,
                      SUM(CASE WHEN is_correct = 0 THEN 1 ELSE 0 END) as wrong,
                      SUM(CASE WHEN status = 'draft' THEN 1 ELSE 0 END) as drafts
               FROM study_materials
               GROUP BY subject
               ORDER BY total DESC"""
        ).fetchall()
    return {"by_subject": [dict(r) for r in rows]}
```

- [ ] **Step 2: 注册路由到 main.py**

```python
# main.py — 添加:
from .routes.study_routes import router as study_router
# ...
app.include_router(study_router)
```

- [ ] **Step 3: 注册到 config_manager.py 的 prompt_registry**

在 `MODULE_MAP` 中新增：
```python
"study": {
    "reading_chinese": "study/prompts.py",
    "math": "study/prompts.py",
    "english": "study/prompts.py",
    "mistake": "study/prompts.py",
}
```

- [ ] **Step 4: Commit**

```bash
git add app/backend/routes/study_routes.py app/backend/main.py app/backend/config_manager.py
git commit -m "feat: 辅导中心 CRUD API — 列表/详情/创建/更新/删除/错题/统计"
```

---

### Task 5: 生成管线（AI 讲题 + 三格式输出）

**Files:**
- Create: `app/backend/study/pipeline.py`

- [ ] **Step 1: 创建生成管线**

```python
"""辅导中心 — 讲题稿生成管线"""

from __future__ import annotations

import json
import logging
import subprocess
import tempfile
from pathlib import Path

from ..deepseek_client import chat
from ..db import connect
from .prompts import (
    READING_CHINESE_SYSTEM, READING_CHINESE_USER,
    MATH_SYSTEM, MATH_USER,
    ENGLISH_SYSTEM, ENGLISH_USER,
    MISTAKE_SYSTEM, MISTAKE_USER,
)
from .templates import render_html

logger = logging.getLogger(__name__)

STUDY_DATA_DIR = Path(__file__).resolve().parents[3] / "data" / "study"
STUDY_DATA_DIR.mkdir(parents=True, exist_ok=True)

CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"


def generate_lecture_notes(
    material_id: str,
    subject: str,
    study_type: str,
    raw_content: str,
    extra_instructions: str = "",
    child_answer: str = "",
) -> dict:
    """生成讲题稿（孩子版 + 家长版），返回 md/html/pdf 路径"""

    # ── 选 prompt ──
    if subject == "数学":
        system = MATH_SYSTEM
        user_template = MATH_USER
    elif subject == "英语":
        system = ENGLISH_SYSTEM
        user_template = ENGLISH_USER
    else:
        system = READING_CHINESE_SYSTEM
        user_template = READING_CHINESE_USER

    # ── 孩子错答补充 ──
    child_section = ""
    if child_answer:
        child_section = f"""
#### 孩子作答情况
（孩子原答：{child_answer}）
- 对错程度判断
- 真正问题在哪
- 错因归类（回文定位不准 / 审题对象抓错 / 信息提取不完整 / 概括不准 / 表达不规范）
- 订正引导
"""

    user = user_template.format(
        raw_content=raw_content,
        extra_instructions=extra_instructions,
        child_answer_section=child_section,
    )

    # ── 调 DeepSeek ──
    messages = [
        {"role": "system", "content": system},
        {"role": "user", "content": user},
    ]

    md_content = chat(
        messages,
        temperature=0.3,
        max_tokens=16384,
        timeout=300,
        module="study",
        task=f"{subject}_{study_type}",
    )

    if not md_content:
        raise RuntimeError("AI 生成讲题稿失败：空响应")

    # ── 写 MD ──
    md_dir = STUDY_DATA_DIR / material_id
    md_dir.mkdir(parents=True, exist_ok=True)

    md_path = md_dir / "讲题稿版.md"
    md_path.write_text(md_content, encoding="utf-8")

    # ── 生成 HTML ──
    title = md_content.split("\n")[0].lstrip("#").strip() or material_id
    html = render_html(subject, title, _md_to_html_body(md_content))
    html_path = md_dir / "讲题稿打印版.html"
    html_path.write_text(html, encoding="utf-8")

    # ── 生成 PDF ──
    pdf_path = md_dir / "讲题稿版.pdf"
    _html_to_pdf(html_path, pdf_path)

    # ── 回写 DB ──
    formats = {
        "md": str(md_path),
        "html": str(html_path),
        "pdf": str(pdf_path),
    }

    # 拆分孩子版/家长版（家长版含所有讲解细节）
    child_version = _extract_child_version(md_content)
    parent_version = md_content  # 家长版 = 完整版

    with connect() as conn:
        conn.execute(
            """UPDATE study_materials
               SET child_version = ?, parent_version = ?,
                   formats_json = ?, status = 'ready',
                   updated_at = datetime('now')
               WHERE id = ?""",
            (child_version, parent_version, json.dumps(formats, ensure_ascii=False), material_id),
        )

    return {
        "material_id": material_id,
        "status": "ready",
        "formats": formats,
    }


def generate_mistake_review(
    material_id: str,
    raw_content: str,
    correct_answer: str,
    child_answer: str,
) -> dict:
    """生成错题复盘讲义"""
    user = MISTAKE_USER.format(
        raw_content=raw_content,
        correct_answer=correct_answer,
        child_answer=child_answer,
    )

    messages = [
        {"role": "system", "content": MISTAKE_SYSTEM},
        {"role": "user", "content": user},
    ]

    md_content = chat(
        messages,
        temperature=0.3,
        max_tokens=4096,
        timeout=180,
        module="study",
        task="mistake_review",
    )

    if not md_content:
        raise RuntimeError("AI 生成错题复盘失败")

    md_dir = STUDY_DATA_DIR / material_id
    md_dir.mkdir(parents=True, exist_ok=True)

    # 追加到已有讲题稿
    existing_path = md_dir / "讲题稿版.md"
    if existing_path.exists():
        existing = existing_path.read_text(encoding="utf-8")
        combined = existing + "\n\n---\n\n## 错题复盘\n\n" + md_content
    else:
        combined = md_content
    existing_path.write_text(combined, encoding="utf-8")

    # 更新 HTML/PDF
    title = combined.split("\n")[0].lstrip("#").strip() or material_id
    subject = _get_material_subject(material_id)
    html = render_html(subject or "语文", title, _md_to_html_body(combined))
    html_path = md_dir / "讲题稿打印版.html"
    html_path.write_text(html, encoding="utf-8")

    pdf_path = md_dir / "讲题稿版.pdf"
    _html_to_pdf(html_path, pdf_path)

    formats = {
        "md": str(existing_path),
        "html": str(html_path),
        "pdf": str(pdf_path),
    }

    with connect() as conn:
        conn.execute(
            """UPDATE study_materials
               SET parent_version = ?, formats_json = ?,
                   updated_at = datetime('now')
               WHERE id = ?""",
            (combined, json.dumps(formats, ensure_ascii=False), material_id),
        )

    return {"material_id": material_id, "formats": formats}


# ── Helpers ──

def _md_to_html_body(md: str) -> str:
    """极简 Markdown→HTML 转换（仅 ##/###/** 等基础语法）"""
    import re
    lines = md.split("\n")
    result = []
    in_list = False

    for line in lines:
        # 标题
        if line.startswith("#### "):
            if in_list: result.append("</ul>"); in_list = False
            result.append(f"<h4>{line[5:]}</h4>")
        elif line.startswith("### "):
            if in_list: result.append("</ul>"); in_list = False
            result.append(f"<h3>{line[4:]}</h3>")
        elif line.startswith("## "):
            if in_list: result.append("</ul>"); in_list = False
            result.append(f"<h2>{line[3:]}</h2>")
        elif line.startswith("# "):
            if in_list: result.append("</ul>"); in_list = False
            result.append(f"<h1>{line[2:]}</h1>")
        # 列表
        elif line.strip().startswith("- "):
            content = _fmt(line.strip()[2:])
            if not in_list: result.append("<ul>"); in_list = True
            result.append(f"<li>{content}</li>")
        elif re.match(r"^\d+\.\s", line.strip()):
            content = _fmt(re.sub(r"^\d+\.\s", "", line.strip()))
            if not in_list: result.append("<ul>"); in_list = True
            result.append(f"<li>{content}</li>")
        # 空行
        elif not line.strip():
            if in_list: result.append("</ul>"); in_list = False
            result.append("<br>")
        # 正文
        else:
            if in_list: result.append("</ul>"); in_list = False
            result.append(f"<p>{_fmt(line)}</p>")

    if in_list: result.append("</ul>")
    return "\n".join(result)


def _fmt(text: str) -> str:
    """加粗处理"""
    import re
    return re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", text)


def _html_to_pdf(html_path: Path, pdf_path: Path):
    """Chrome headless 生成 PDF"""
    try:
        subprocess.run(
            [
                CHROME,
                "--headless", "--disable-gpu", "--no-sandbox",
                f"--print-to-pdf={pdf_path}",
                f"file://{html_path.resolve()}",
            ],
            check=True,
            timeout=60,
            capture_output=True,
        )
    except FileNotFoundError:
        logger.warning("Chrome not found at %s, skipping PDF", CHROME)
    except subprocess.TimeoutExpired:
        logger.warning("PDF generation timed out for %s", pdf_path)


def _extract_child_version(md_content: str) -> str:
    """提取孩子版（去掉「家长怎么讲」「详细解题思路」等家长专属内容）"""
    # 策略：保留前四分之一 + 参考答案 + 整洁答案
    parts = md_content.split("## ")
    child_parts = []
    for part in parts:
        if "家长怎么讲" in part or "详细解题思路" in part:
            # 只保留「参考答案」行
            lines = part.split("\n")
            kept = [lines[0]]  # 标题
            for i, line in enumerate(lines):
                if "参考答案" in line:
                    kept.extend(lines[i:])
                    break
            child_parts.append("\n".join(kept))
        else:
            child_parts.append(part)
    return "## ".join(child_parts)


def _get_material_subject(material_id: str) -> str | None:
    with connect() as conn:
        row = conn.execute(
            "SELECT subject FROM study_materials WHERE id = ?", (material_id,)
        ).fetchone()
    return row["subject"] if row else None
```

- [ ] **Step 2: 在 study_routes.py 中添加生成端点**

```python
# study_routes.py 追加:

class GenerateRequest(BaseModel):
    extra_instructions: str = ""

class MistakeReviewRequest(BaseModel):
    correct_answer: str
    child_answer: str


@router.post("/{material_id}/generate")
def generate_material(material_id: str, req: GenerateRequest):
    """AI 生成讲题稿（后台同步执行）"""
    init_db()
    with connect() as conn:
        row = conn.execute(
            "SELECT subject, study_type, raw_content FROM study_materials WHERE id = ?",
            (material_id,),
        ).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="资料不存在")

    try:
        from ..study.pipeline import generate_lecture_notes
        result = generate_lecture_notes(
            material_id=material_id,
            subject=row["subject"],
            study_type=row["study_type"],
            raw_content=row["raw_content"],
            extra_instructions=req.extra_instructions,
        )
        return result
    except Exception as e:
        logger.exception("生成讲题稿失败: %s", material_id)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/{material_id}/review")
def review_mistake(material_id: str, req: MistakeReviewRequest):
    """生成错题复盘讲义"""
    init_db()
    with connect() as conn:
        row = conn.execute(
            "SELECT raw_content FROM study_materials WHERE id = ?",
            (material_id,),
        ).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="资料不存在")

    try:
        from ..study.pipeline import generate_mistake_review
        result = generate_mistake_review(
            material_id=material_id,
            raw_content=row["raw_content"],
            correct_answer=req.correct_answer,
            child_answer=req.child_answer,
        )
        return result
    except Exception as e:
        logger.exception("错题复盘失败: %s", material_id)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{material_id}/file/{fmt}")
def get_study_file(material_id: str, fmt: str):
    """返回讲题稿文件（md/html）"""
    from fastapi.responses import FileResponse
    md_dir = STUDY_DATA_DIR / material_id
    if fmt == "md":
        path = md_dir / "讲题稿版.md"
    elif fmt == "html":
        path = md_dir / "讲题稿打印版.html"
    elif fmt == "pdf":
        path = md_dir / "讲题稿版.pdf"
    else:
        raise HTTPException(status_code=400, detail=f"不支持的格式: {fmt}")
    if not path.exists():
        raise HTTPException(status_code=404, detail="文件尚未生成")
    return FileResponse(path)
```

- [ ] **Step 5: Commit**

```bash
git add app/backend/study/pipeline.py app/backend/routes/study_routes.py
git commit -m "feat: 辅导中心生成管线 — AI讲题 + MD/HTML/PDF三格式输出"
```

---

### Task 6: OCR 集成

**Files:**
- Modify: `app/backend/study/pipeline.py`（新增 OCR 函数）

- [ ] **Step 1: 添加 OCR 支持**

```python
# pipeline.py 追加:

def ocr_image(image_path: Path) -> str:
    """使用 macOS Vision 框架对图片 OCR"""
    # 先缩小大图
    resized = image_path.parent / f"_ocr_{image_path.stem}.png"
    subprocess.run(
        ["sips", "-Z", "1200", str(image_path), "--out", str(resized)],
        check=True, capture_output=True,
    )

    # OCR 脚本路径（从 Hermes skills 中复制）
    ocr_script = Path("/Users/mrh/.hermes/skills/study/study-orchestrator/scripts/ocr_vision.swift")
    if not ocr_script.exists():
        logger.warning("OCR 脚本不存在: %s", ocr_script)
        return ""

    result = subprocess.run(
        ["swift", str(ocr_script), str(resized)],
        capture_output=True, text=True, timeout=60,
    )
    resized.unlink(missing_ok=True)
    return result.stdout.strip()
```

- [ ] **Step 2: 在 study_routes.py 添加文件上传+OCR 端点**

```python
@router.post("/upload")
def upload_image(
    file: UploadFile = File(...),
    subject: str = Form("语文"),
    study_type: str = Form("阅读理解"),
    grade: str = Form(""),
):
    """上传题目图片 → OCR → 创建学习资料"""
    import tempfile
    suffix = Path(file.filename or "upload.jpg").suffix
    tmp = tempfile.NamedTemporaryFile(suffix=suffix, delete=False)
    tmp.write(file.file.read())
    tmp.close()
    tmp_path = Path(tmp.name)

    try:
        from ..study.pipeline import ocr_image
        raw_content = ocr_image(tmp_path)
        if not raw_content:
            raise HTTPException(status_code=400, detail="OCR 未提取到文字，请确认图片清晰")
    finally:
        tmp_path.unlink(missing_ok=True)

    title = raw_content.split("\n")[0][:40] if raw_content else "图片题目"
    return create_material(StudyCreateRequest(
        subject=subject,
        study_type=study_type,
        title=title,
        raw_content=raw_content,
        grade=grade,
        source_type="photo",
    ))
```

- [ ] **Step 3: Commit**

```bash
git add app/backend/study/pipeline.py app/backend/routes/study_routes.py
git commit -m "feat: 辅导中心 OCR 集成 — 拍照上传自动识别题目"
```

---

## Phase 2 — 前端（Task 7-10）

### Task 7: Study.tsx — 辅导中心列表页

**Files:**
- Create: `app/frontend/src/pages/Study.tsx`

页面布局（参照 Ingest.tsx 的吸顶布局）：
- 顶部：标题「辅导中心」+ 副标题 + 新建按钮
- Tab 栏：全部 / 语文 / 数学 / 英语（学科筛选）
- 列表：标题 / 学科 / 题型 / 状态 / 对错 / 时间 / 操作
- 新建弹窗：学科+题型下拉 → 手动录入文本或文件上传 → 创建

### Task 8: StudyDetail.tsx — 讲题详情页

**Files:**
- Create: `app/frontend/src/pages/StudyDetail.tsx`

页面布局（参照 SeriesDetail / EventDetailPage）：
- 面包屑：← 辅导中心
- 标题 + 元信息（学科/题型/年级/正确率）
- Tab 栏：孩子版 / 家长版
- 格式切换：MD / HTML / PDF
- 操作按钮：重新生成 / 批改 / 错题复盘
- PDF 内嵌 iframe、MD 用 react-markdown、HTML 内嵌 iframe

### Task 9: StudyMistakes.tsx — 错题本

**Files:**
- Create: `app/frontend/src/pages/StudyMistakes.tsx`

页面布局：
- 顶部：标题「错题本」+ 学科筛选
- 错题标签云（薄弱点可视化）
- 错题列表：每行 → 标题 / 学科 / 错因标签 / 时间
- 点击 → 进入 StudyDetail 详情

### Task 10: 导航入口注册

**Files:**
- Modify: `app/frontend/src/App.tsx`
- Modify: `app/frontend/src/components/Sidebar.tsx`
- Modify: `app/frontend/src/components/BottomTabBar.tsx`

Sidebar + BottomTabBar 各加一项：
```
📚 辅导中心    BookOpen 图标   text-amber-400   route: /study
```

App.tsx 注册路由：
```tsx
<Route path="/study" element={<Study />} />
<Route path="/study/:id" element={<StudyDetail />} />
<Route path="/study/mistakes" element={<StudyMistakes />} />
```

---

## 验证清单

- [ ] `python -c "from backend.db import init_db; init_db()"` — 建表成功
- [ ] `curl http://localhost:9120/api/study/list` — 列表接口正常
- [ ] `curl -X POST http://localhost:9120/api/study/create -d '{"subject":"数学","study_type":"应用题","raw_content":"小明有5个苹果..."}'` — 创建成功
- [ ] `curl -X POST http://localhost:9120/api/study/{id}/generate` — 生成讲题稿，检查 data/study/{id}/ 下三文件
- [ ] `npm run build` — 前端构建通过
- [ ] 浏览器 `localhost:9120/study` — 页面正常渲染
- [ ] 浏览器 `localhost:9120/study/:id` — 详情页三格式切换正常
- [ ] 浏览器 `localhost:9120/study/mistakes` — 错题本正常
- [ ] Sidebar + BottomTabBar 辅导中心入口可见，红点计数正常
