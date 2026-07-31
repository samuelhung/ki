"""Validated AI punctuation and semantic paragraphing for transcripts."""

from __future__ import annotations

import threading
import time
import uuid
from collections.abc import Callable
from dataclasses import dataclass, replace
from typing import Literal

from . import ai_client
from . import transcript_revision_service as revisions

TASK_TTL_SECONDS = 30 * 60
MAX_RETAINED_TASKS = 100

body_sequence = revisions.body_sequence
RevisionConflictError = revisions.RevisionConflictError


class TaskNotFoundError(LookupError):
    pass


class TaskExpiredError(LookupError):
    pass


class TaskCapacityError(RuntimeError):
    pass


class TaskNotReadyError(RuntimeError):
    pass


class SegmentationOutputError(ValueError):
    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


@dataclass(frozen=True)
class TranscriptChunk:
    prefix: str
    core: str
    suffix: str


@dataclass
class SegmentationTask:
    id: str
    event_id: str
    base_revision_id: str
    source: str
    status: Literal["processing", "ready", "failed", "confirmed"]
    preview: str = ""
    error_code: str = ""
    completed_chunks: int = 0
    total_chunks: int = 0
    created_at: float = 0.0
    confirmed_revision_id: str | None = None


_TASKS: dict[str, SegmentationTask] = {}
_TASKS_LOCK = threading.Lock()


def _is_terminal(task: SegmentationTask) -> bool:
    return task.status in {"ready", "failed", "confirmed"}


def _is_expired(task: SegmentationTask, now: float) -> bool:
    return task.status != "confirmed" and now - task.created_at > TASK_TTL_SECONDS


def _prune_tasks(now: float) -> None:
    for task_id, task in list(_TASKS.items()):
        if _is_expired(task, now):
            del _TASKS[task_id]
    while len(_TASKS) >= MAX_RETAINED_TASKS:
        terminal = [task for task in _TASKS.values() if _is_terminal(task)]
        if not terminal:
            raise TaskCapacityError("segmentation task capacity reached")
        oldest = min(terminal, key=lambda task: task.created_at)
        del _TASKS[oldest.id]


def split_cores(
    text: str, max_chars: int = 6000, context_chars: int = 300
) -> list[TranscriptChunk]:
    if max_chars <= 0 or context_chars < 0:
        raise ValueError("invalid chunk sizing")
    chunks: list[TranscriptChunk] = []
    start = 0
    while start < len(text):
        hard_end = min(len(text), start + max_chars)
        end = hard_end
        if hard_end < len(text):
            lower = start + max(1, int(max_chars * 0.8))
            window = text[lower:hard_end]
            paragraph = window.rfind("\n\n")
            if paragraph >= 0:
                end = lower + paragraph + 2
            else:
                sentence_end = -1
                for index, char in enumerate(window):
                    if char in "。！？!?；;.\n":
                        sentence_end = index
                if sentence_end >= 0:
                    end = lower + sentence_end + 1
                else:
                    whitespace_end = -1
                    for index, char in enumerate(window):
                        if char.isspace():
                            whitespace_end = index
                    if whitespace_end >= 0:
                        end = lower + whitespace_end + 1
        if end <= start:
            end = hard_end
        chunks.append(
            TranscriptChunk(
                prefix=text[max(0, start - context_chars) : start],
                core=text[start:end],
                suffix=text[end : end + context_chars],
            )
        )
        start = end
    return chunks


def segment_core(
    core: str,
    prefix: str,
    suffix: str,
    *,
    chat_fn: Callable[..., str | None] = ai_client.chat,
) -> str:
    system_prompt = """你只负责中文语义分段和标点校正。
必须完整保留核心文本中的所有正文字符、数字、英文大小写、符号及其顺序。
只允许增删或调整 Unicode 标点、空格和换行；不得补写、删减、替换或重排正文。
只读上文和只读下文仅用于理解语义，不得复制到输出。
只输出处理后的核心文本，不要解释，不要使用 Markdown 代码块。"""
    messages = [
        {"role": "system", "content": system_prompt},
        {
            "role": "user",
            "content": (
                f"<<<只读上文>>>\n{prefix}\n"
                f"<<<核心文本>>>\n{core}\n"
                f"<<<只读下文>>>\n{suffix}"
            ),
        },
    ]
    result = chat_fn(
        messages,
        temperature=0.1,
        max_tokens=max(2048, len(core) * 2),
        timeout=180,
        module="ingest_pipeline",
        task="segment_transcript",
    )
    if result is None:
        raise SegmentationOutputError("provider_error")
    if not result.strip():
        raise SegmentationOutputError("empty_output")
    return result


def create_task(
    task_id: str | None,
    event_id: str,
    base_revision_id: str,
    source: str,
    *,
    now_fn: Callable[[], float] = time.monotonic,
) -> SegmentationTask:
    now = now_fn()
    new_id = task_id or f"segment-{uuid.uuid4().hex}"
    with _TASKS_LOCK:
        _prune_tasks(now)
        if new_id in _TASKS:
            raise ValueError("duplicate segmentation task id")
        task = SegmentationTask(
            id=new_id,
            event_id=event_id,
            base_revision_id=base_revision_id,
            source=source,
            status="processing",
            created_at=now,
        )
        _TASKS[new_id] = task
        return replace(task)


def _task_for_update(task_id: str, now: float) -> SegmentationTask:
    task = _TASKS.get(task_id)
    if task is None:
        raise TaskNotFoundError(task_id)
    if _is_expired(task, now):
        del _TASKS[task_id]
        raise TaskExpiredError(task_id)
    return task


def get_task(
    task_id: str, *, now_fn: Callable[[], float] = time.monotonic
) -> SegmentationTask:
    with _TASKS_LOCK:
        return replace(_task_for_update(task_id, now_fn()))


def run_task(
    task_id: str,
    *,
    chat_fn: Callable[..., str | None] = ai_client.chat,
    chunk_size: int = 6000,
    context_chars: int = 300,
    now_fn: Callable[[], float] = time.monotonic,
) -> SegmentationTask:
    with _TASKS_LOCK:
        task = _task_for_update(task_id, now_fn())
        source = task.source
    chunks = split_cores(source, max_chars=chunk_size, context_chars=context_chars)
    with _TASKS_LOCK:
        task = _task_for_update(task_id, now_fn())
        task.total_chunks = len(chunks)

    outputs: list[str] = []
    try:
        if not chunks:
            raise SegmentationOutputError("empty_output")
        for chunk in chunks:
            output = segment_core(
                chunk.core,
                chunk.prefix,
                chunk.suffix,
                chat_fn=chat_fn,
            )
            try:
                revisions.assert_same_body(chunk.core, output)
            except revisions.BodyCharacterMismatchError as exc:
                raise SegmentationOutputError("body_changed") from exc
            outputs.append(output)
            with _TASKS_LOCK:
                task = _task_for_update(task_id, now_fn())
                task.completed_chunks += 1
        preview = "".join(outputs)
        try:
            revisions.assert_same_body(source, preview)
        except revisions.BodyCharacterMismatchError as exc:
            raise SegmentationOutputError("body_changed") from exc
    except SegmentationOutputError as exc:
        with _TASKS_LOCK:
            task = _task_for_update(task_id, now_fn())
            task.status = "failed"
            task.error_code = exc.code
            task.preview = ""
            return replace(task)
    except Exception:
        with _TASKS_LOCK:
            task = _task_for_update(task_id, now_fn())
            task.status = "failed"
            task.error_code = "provider_error"
            task.preview = ""
            return replace(task)

    with _TASKS_LOCK:
        task = _task_for_update(task_id, now_fn())
        task.status = "ready"
        task.preview = preview
        task.error_code = ""
        return replace(task)


def run_segmentation(
    task_id: str,
    event_id: str,
    base_revision_id: str,
    source: str,
    *,
    chat_fn: Callable[..., str | None] = ai_client.chat,
    chunk_size: int = 6000,
    context_chars: int = 300,
    now_fn: Callable[[], float] = time.monotonic,
) -> SegmentationTask:
    create_task(
        task_id,
        event_id,
        base_revision_id,
        source,
        now_fn=now_fn,
    )
    return run_task(
        task_id,
        chat_fn=chat_fn,
        chunk_size=chunk_size,
        context_chars=context_chars,
        now_fn=now_fn,
    )


def mark_confirmed(
    task_id: str,
    *,
    active_revision_id: str,
    confirm_fn: Callable[[str, str], str],
    now_fn: Callable[[], float] = time.monotonic,
) -> str:
    with _TASKS_LOCK:
        task = _task_for_update(task_id, now_fn())
        if task.confirmed_revision_id is not None:
            return task.confirmed_revision_id
        if task.status != "ready":
            raise TaskNotReadyError(task_id)
        if task.base_revision_id != active_revision_id:
            raise RevisionConflictError(active_revision_id)
        revision_id = confirm_fn(task.preview, task.base_revision_id)
        task.confirmed_revision_id = revision_id
        task.status = "confirmed"
        return task.confirmed_revision_id
