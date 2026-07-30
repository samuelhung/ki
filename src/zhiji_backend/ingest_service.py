"""Application service for creating and synchronously processing ingests."""

from __future__ import annotations

import hashlib
import json
import re
import shutil
import tempfile
import uuid
from datetime import UTC, datetime
from pathlib import Path

from . import transcript_revision_service

_CONCEPT_SYSTEM_PROMPT = "你是严谨的知识整理助手，为概念提供结构化、准确的解释。回答简洁专业，避免冗长。如有参考文档，必须基于原文摘录依据，不可凭空发挥。"
_CONCEPT_FORMAT = "请按以下格式输出（使用 Markdown）：\n\n## 核心定义\n（一到两句话厘清概念）\n\n## 关键机制/原理\n1. ...\n2. ...\n\n{evidence}## 适用范围/前提假设\n\n## 关联概念\n- 概念A\n- 概念B"
_CONCEPT_EVIDENCE = "## 原文依据\n（从下方参考文档中摘录与该概念直接相关的原文段落。要求：\n- 每条引用独立成段，末尾标注 [文档N]\n- 引用原文关键句，而非自行概括\n- 若无直接相关原文，标注「参考文档中未直接涉及」）\n\n"
_DEGRADED_LOG = "module=%s task=%s status=degraded error_class=%s error_code=%s"
_ERROR_LOG = "module=%s task=%s status=error error_class=%s error_code=%s"
_AI_TITLE_LOG = "AI generated title for %s: %s -> %s"
_SUMMARY_NONE_LOG = "AI summarization returned None for %s — API may be unavailable"
_CLASSIFY_LOG = "Classification failed for %s — non-blocking"
_SOURCE_SQL = "INSERT OR IGNORE INTO sources (id, name, type, url, topic, priority, enabled) VALUES (?, ?, 'manual', '', ?, 'medium', 1)"
_EVENT_SQL = "INSERT INTO events (id, source_id, title, url, topic, importance, actionability, decision, status, content_type) VALUES (?, ?, ?, '', ?, 4, 4, 'digest', 'processing', ?)"
_CONCEPT_SQL = "INSERT INTO events (id, source_id, title, url, topic, importance, actionability, decision, status, content_type, ai_summary, created_at) VALUES (?, 'user-concept', ?, '', ?, 4, 4, 'digest', 'completed', 'concept', ?, ?)"
_UPDATE_EVENT_SQL = "UPDATE events SET raw_summary = ?, ai_summary = COALESCE(?, ai_summary), overview = COALESCE(?, overview), status = 'completed', last_error = NULL, video_path = ?, audio_path = ?, document_path = ?, video_md5 = COALESCE(?, video_md5), title = CASE WHEN title = '待处理' OR title = '' THEN ? ELSE title END WHERE id = ?"

FILE_TYPE_MAP = {
    "document": {".md", ".txt", ".markdown", ".json", ".csv", ".log", ".pdf", ".epub"},
    "audio_file": {".mp3", ".wav", ".m4a", ".aac", ".flac", ".ogg", ".opus", ".wma"},
    "video_file": {".mp4", ".mov", ".avi", ".mkv", ".webm", ".mts", ".ts", ".flv"},
}


def _execute(conn, statement, *values):
    return conn.execute(statement, values)


def detect_ingest_type(filename, *, file_type_map=FILE_TYPE_MAP):
    if not filename:
        return None
    suffix = Path(filename).suffix.lower()
    return next(
        (kind for kind, extensions in file_type_map.items() if suffix in extensions),
        None,
    )


def md5_file(path):
    try:
        return hashlib.md5(path.read_bytes()).hexdigest()
    except Exception:
        return None


def set_progress(event_id, stages, *, connect_fn):
    with connect_fn() as conn:
        conn.execute(
            "UPDATE events SET progress_stages = ? WHERE id = ?",
            (json.dumps(stages, ensure_ascii=False), event_id),
        )


def create_event(
    ingest_type, content, topic, title="", content_type="event", *, dependencies
):
    dependencies["init_db_fn"]()
    event_id = f"evt-ingest-{uuid.uuid4().hex[:12]}"
    source_id = "douyin" if ingest_type == "douyin_share" else "user-upload"
    with dependencies["connect_fn"]() as conn:
        source_name = "抖音分享" if source_id == "douyin" else "用户上传"
        _execute(conn, _SOURCE_SQL, source_id, source_name, topic)
        values = [event_id, source_id, title or "待处理", topic, content_type]
        _execute(conn, _EVENT_SQL, *values)
    dependencies["enqueue_fn"](event_id, ingest_type, content, topic, title)
    return {"event_id": event_id, "status": "processing", "type": ingest_type}


def create_concept(
    title, topic, description="", force_ai=False, context_docs=None, *, dependencies
):
    dependencies["init_db_fn"]()
    log = dependencies["logger"]
    from .ai_client import chat
    from .classifier import classify_content

    concept_id = f"evt-concept-{uuid.uuid4().hex[:12]}"
    now_ts = datetime.now(UTC).strftime("%Y-%m-%d %H:%M")
    parts = []
    index_parts = []
    for document in context_docs or []:
        content = document.get("content", "")
        if content.strip():
            number = len(parts) + 1
            doc_title = document.get("title", "未知文档")
            parts.append(f"[文档{number}] 《{doc_title}》\n{content.strip()}")
            index_parts.append(f"[文档{number}] 《{doc_title}》")
    docs_block = "\n\n".join(parts)
    docs_index = "\n".join(index_parts)

    ai_summary = ""
    if not description.strip() or force_ai:
        try:
            seed = description.strip()
            prompt = f"请为以下概念提供结构化的解释说明：\n\n概念名称：{title}\n"
            prompt += f"参考简述：{seed}\n\n" if seed else "\n"
            prompt += _CONCEPT_FORMAT.format(
                evidence=_CONCEPT_EVIDENCE if docs_block else ""
            )
            if docs_block:
                prompt += (
                    f"\n\n参考文档原文：\n{docs_block}\n\n参考文档清单：\n{docs_index}"
                )
            messages = [
                {"role": "system", "content": _CONCEPT_SYSTEM_PROMPT},
                {"role": "user", "content": prompt},
            ]
            ai_summary = chat(
                messages,
                temperature=0.3,
                max_tokens=1500,
                module="ingest_pipeline",
                task="summarize",
            )
        except Exception as exc:
            log.warning("Concept AI auto-complete failed for %s: %s", title, exc)

    final_topic = topic if topic and topic != "uncategorized" else ""
    if not final_topic:
        try:
            final_topic = classify_content(
                title, description.strip() or ai_summary or title
            )
            log.info("Concept '%s' auto-classified as '%s'", title, final_topic)
        except Exception as exc:
            log.warning("Concept classification failed for %s: %s", title, exc)
            final_topic = "认知"

    concepts_dir = dependencies["ingest_root"].parent / "concepts"
    concepts_dir.mkdir(parents=True, exist_ok=True)
    concept_md = f"# {title}\n\n创建时间：{now_ts}\n\n---\n\n"
    if ai_summary:
        concept_md += ai_summary + "\n"
    elif description.strip():
        concept_md += description.strip() + "\n"
    (concepts_dir / f"{concept_id}.md").write_text(concept_md, encoding="utf-8")
    with dependencies["connect_fn"]() as conn:
        values = [concept_id, title, final_topic, ai_summary or description, now_ts]
        _execute(conn, _CONCEPT_SQL, *values)
    return {"event_id": concept_id, "status": "completed", "ai_summary": ai_summary}


def _stages(spec):
    return [
        {"key": key, "label": label, "status": "active" if index == 0 else "pending"}
        for index, (key, label) in enumerate(
            item.split(":", 1) for item in spec.split(",")
        )
    ]


def _advance(stages, index, event_id, progress):
    stages[index]["status"], stages[index + 1]["status"] = "done", "active"
    progress(event_id, stages)


def _document_content(content, title, topic, event_id, deps):
    from .ingest.document import process_document

    progress = deps["set_progress_fn"]
    path = Path(content)
    if path.suffix.lower() == ".pdf":
        from .ingest.pdf_ocr import detect_pdf_type

        is_scan = detect_pdf_type(path) == "scan"
    else:
        is_scan = False
    if is_scan:
        stages = _stages("render:渲染页面,ocr:OCR 识别,done:完成")
        progress(event_id, stages)

        def on_progress(current: int, total: int):
            stages[0]["status"] = "done"
            stages[1].update(status="active", label=f"OCR 识别 ({current}/{total} 页)")
            progress(event_id, stages)

        result = process_document(
            content, title=title, topic=topic, on_progress=on_progress
        )
    else:
        stages = _stages("parse:解析文档,done:完成")
        progress(event_id, stages)
        result = process_document(content, title=title, topic=topic)
    for stage in stages:
        stage["status"] = "done"
    progress(event_id, stages)
    return result["text"], result.get("title", title) or title, stages, None


def _media_content(content, title, event_id, ingest_type, work_dir, deps):
    from .ingest.volc_transcriber import transcribe

    progress = deps["set_progress_fn"]
    if ingest_type == "audio_file":
        stages = _stages("transcribe:语音转写,done:完成")
        progress(event_id, stages)
        text = transcribe(Path(content))
        _advance(stages, 0, event_id, progress)
        return text, title, stages, None
    from .ingest.media import extract_audio

    stages = _stages("extract:提取音频,transcribe:语音转写,done:完成")
    progress(event_id, stages)
    videos_dir = deps["videos_dir"]
    resolve = deps["resolve_under_fn"]
    videos_dir.mkdir(parents=True, exist_ok=True)
    shutil.copy2(
        content,
        resolve(videos_dir, f"{event_id}{Path(content).suffix}", must_exist=False),
    )
    audio_path = work_dir / "extracted.wav"
    extract_audio(Path(content), audio_path)
    _advance(stages, 0, event_id, progress)
    text = transcribe(audio_path)
    _advance(stages, 1, event_id, progress)
    return text, title, stages, None


def _douyin_content(content, title, event_id, work_dir, deps):
    from .ingest import volc_transcriber as volc
    from .ingest.douyin import download_video, parse_share_text
    from .ingest.media import extract_audio

    stages = _stages(
        "parse:解析链接,download:下载视频,persist:保存视频,extract:提取音频,tos:上传 TOS,transcribe:语音转写,summarize:AI 总结,writedb:写入数据库,classify:自动分类,done:完成"
    )
    progress = deps["set_progress_fn"]
    progress(event_id, stages)
    info = parse_share_text(str(content))
    _advance(stages, 0, event_id, progress)
    video_path = work_dir / "video.mp4"
    download_video(info["download_url"], video_path, session=info.get("_session"))
    _advance(stages, 1, event_id, progress)
    videos_dir = deps["videos_dir"]
    videos_dir.mkdir(parents=True, exist_ok=True)
    persistent_video = deps["resolve_under_fn"](
        videos_dir, f"{event_id}.mp4", must_exist=False
    )
    shutil.copy2(video_path, persistent_video)
    video_md5 = deps["md5_file_fn"](persistent_video)
    _advance(stages, 2, event_id, progress)
    audio_path = work_dir / "audio.wav"
    extract_audio(video_path, audio_path)
    _advance(stages, 3, event_id, progress)
    audio_url = volc.upload_to_tos(audio_path)
    _advance(stages, 4, event_id, progress)
    req_id, logid = volc.submit_transcription(audio_url)
    text = volc.poll_result(req_id, logid)
    _advance(stages, 5, event_id, progress)
    raw_title = info.get("platform_title", "")
    if raw_title:
        clean = re.sub(r"\s*[#＃][^\s#＃@]+", "", raw_title)
        clean = re.sub(r"\s*@\S+", "", clean).strip().rstrip("，,。.")
        title = clean if clean else ""
    title = title or raw_title
    with deps["connect_fn"]() as conn:
        _execute(
            conn,
            "UPDATE events SET url = ? WHERE id = ?",
            info.get("share_url", ""),
            event_id,
        )
    return text, title, stages, video_md5


def _persist_upload(content, event_id, directory, resolve):
    directory.mkdir(parents=True, exist_ok=True)
    path = resolve(directory, f"{event_id}{Path(content).suffix}", must_exist=False)
    shutil.copy2(content, path)
    return str(path)


def process_ingest(
    event_id: str, ingest_type: str, content, topic: str, title: str, *, dependencies
):
    deps = dependencies
    deps["safe_identifier_fn"](event_id)
    log = deps["logger"]
    work_dir = Path(tempfile.mkdtemp())
    try:
        progress = deps["set_progress_fn"]
        if ingest_type == "document":
            text, title, stages, video_md5 = _document_content(
                content, title, topic, event_id, deps
            )
        elif ingest_type in ("audio_file", "video_file"):
            text, title, stages, video_md5 = _media_content(
                content, title, event_id, ingest_type, work_dir, deps
            )
        elif ingest_type == "douyin_share":
            text, title, stages, video_md5 = _douyin_content(
                content, title, event_id, work_dir, deps
            )
        else:
            raise ValueError(f"Unknown ingest type: {ingest_type}")
        deps["transcripts_dir"].mkdir(parents=True, exist_ok=True)
        deps["resolve_under_fn"](
            deps["transcripts_dir"], f"{event_id}.md", must_exist=False
        ).write_text(text, encoding="utf-8")
        ai_summary = overview = None
        try:
            from .summarizer import summarize_transcript

            need_ai_title = (
                not title
                or bool(re.match(r"^[\s#＃@]+$", title or ""))
                or ingest_type in ("video_file", "audio_file")
                or (
                    ingest_type == "douyin_share"
                    and not re.search(r"[。！？）」\"'」』]$", title)
                )
            )
            result = summarize_transcript(text, title=title, need_title=need_ai_title)
            if result is not None:
                ai_summary = result.get("summary", "")
                overview = result.get("overview", "")
                if need_ai_title and result.get("suggested_title"):
                    old_title, title = title, result["suggested_title"]
                    log.info(_AI_TITLE_LOG, event_id, old_title[:40], title)
                deps["summaries_dir"].mkdir(parents=True, exist_ok=True)
                deps["resolve_under_fn"](
                    deps["summaries_dir"], f"{event_id}.md", must_exist=False
                ).write_text(ai_summary or "", encoding="utf-8")
            else:
                log.warning(_SUMMARY_NONE_LOG, event_id)
        except Exception as exc:
            error = (
                deps["module_name"],
                event_id,
                type(exc).__name__,
                deps["classify_task_error_fn"](exc),
            )
            log.warning(_DEGRADED_LOG, *error)
        if ingest_type == "douyin_share":
            _advance(stages, 6, event_id, progress)
        video_path = audio_path_col = document_path_col = None
        if ingest_type == "video_file":
            video_path = str(deps["videos_dir"] / f"{event_id}{Path(content).suffix}")
        elif ingest_type == "douyin_share":
            video_path = str(deps["videos_dir"] / f"{event_id}.mp4")
        elif ingest_type == "audio_file":
            audio_path_col = _persist_upload(
                content, event_id, deps["audio_dir"], deps["resolve_under_fn"]
            )
        elif ingest_type == "document":
            document_path_col = _persist_upload(
                content, event_id, deps["documents_dir"], deps["resolve_under_fn"]
            )
        with deps["connect_fn"]() as conn:
            values = [text, ai_summary, overview]
            values += [video_path, audio_path_col, document_path_col]
            values += [video_md5, title or "待处理", event_id]
            _execute(conn, _UPDATE_EVENT_SQL, *values)
        transcript_state = transcript_revision_service.ensure_initialized(
            event_id,
            connect_fn=deps["connect_fn"],
            initial_content=text,
            summary_published=False,
        )
        artifact_marked = transcript_revision_service.mark_artifact_revision(
            event_id,
            transcript_state.active_revision_id,
            connect_fn=deps["connect_fn"],
            transcripts_dir=deps["transcripts_dir"],
        )
        if not artifact_marked:
            raise RuntimeError("transcript artifact publication was not verified")
        if ai_summary:
            transcript_revision_service.mark_summary_revision(
                event_id,
                transcript_state.active_revision_id,
                connect_fn=deps["connect_fn"],
            )
        if ingest_type == "douyin_share":
            _advance(stages, 7, event_id, progress)
        try:
            from .classifier import classify_event

            classify_event(event_id)
        except Exception:
            log.warning(_CLASSIFY_LOG, event_id, exc_info=True)
        stages[-1]["status"] = "done"
        progress(event_id, stages)
    except Exception as exc:
        error_msg = deps["sanitize_task_error_fn"](exc)
        with deps["connect_fn"]() as conn:
            _execute(
                conn,
                "UPDATE events SET status = 'error', last_error = ? WHERE id = ?",
                error_msg,
                event_id,
            )
        error = (
            deps["module_name"],
            event_id,
            type(exc).__name__,
            deps["classify_task_error_fn"](exc),
        )
        log.error(_ERROR_LOG, *error)
        raise
    finally:
        shutil.rmtree(work_dir, ignore_errors=True)
