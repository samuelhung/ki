from __future__ import annotations

import pytest

from zhiji_backend import prompt_registry
from zhiji_backend import transcript_segmentation_service as service


def _core_from_messages(messages: list[dict[str, str]]) -> str:
    payload = messages[-1]["content"]
    return payload.split("<<<核心文本>>>\n", 1)[1].split("\n<<<只读下文>>>", 1)[0]


def test_split_cores_reassembles_exact_source_at_preferred_boundaries():
    source = "第一段内容。\n\n第二段内容 还在继续，最后结束。"

    chunks = service.split_cores(source, max_chars=10, context_chars=3)

    assert "".join(chunk.core for chunk in chunks) == source
    assert all(len(chunk.core) <= 10 for chunk in chunks)
    assert chunks[0].suffix == source[len(chunks[0].core) : len(chunks[0].core) + 3]
    assert (
        chunks[-1].prefix == source[-len(chunks[-1].core) - 3 : -len(chunks[-1].core)]
    )


def test_segmentation_chunks_reassembles_and_validates_every_core():
    source = "第一句没有标点 第二句需要换段第三句结束"

    task = service.run_segmentation(
        "task-ready",
        "evt-1",
        "manual-1",
        source,
        chat_fn=lambda messages, **_kwargs: _core_from_messages(messages) + "。\n\n",
        chunk_size=8,
        now_fn=lambda: 100.0,
    )

    assert task.status == "ready"
    assert service.body_sequence(task.preview) == service.body_sequence(source)
    assert task.completed_chunks == task.total_chunks
    assert task.total_chunks > 1


@pytest.mark.parametrize(
    ("chat_fn", "error_code"),
    [
        (lambda _messages, **_kwargs: "", "empty_output"),
        (lambda _messages, **_kwargs: "正文被修改", "body_changed"),
        (lambda _messages, **_kwargs: None, "provider_error"),
    ],
)
def test_failed_chunk_fails_whole_task_without_partial_preview(chat_fn, error_code):
    task = service.run_segmentation(
        f"task-{error_code}",
        "evt-1",
        "manual-1",
        "必须完整保留的正文",
        chat_fn=chat_fn,
        chunk_size=5,
        now_fn=lambda: 100.0,
    )

    assert task.status == "failed"
    assert task.error_code == error_code
    assert task.preview == ""


def test_read_only_context_cannot_be_copied_into_core_output():
    def copy_prefix(messages, **_kwargs):
        payload = messages[-1]["content"]
        prefix = payload.split("<<<只读上文>>>\n", 1)[1].split("\n<<<核心文本>>>", 1)[0]
        return prefix + _core_from_messages(messages)

    task = service.run_segmentation(
        "task-context",
        "evt-1",
        "manual-1",
        "前文正文后文正文继续",
        chat_fn=copy_prefix,
        chunk_size=4,
        now_fn=lambda: 100.0,
    )

    assert task.status == "failed"
    assert task.error_code == "body_changed"
    assert task.preview == ""


def test_empty_source_fails_instead_of_becoming_ready_without_ai_output():
    task = service.run_segmentation(
        "task-empty-source",
        "evt-1",
        "manual-1",
        "",
        chat_fn=lambda _messages, **_kwargs: "不应调用",
        now_fn=lambda: 100.0,
    )

    assert task.status == "failed"
    assert task.error_code == "empty_output"
    assert task.preview == ""


def test_expired_unconfirmed_task_is_removed():
    service.create_task(
        "task-expired",
        "evt-1",
        "manual-1",
        "正文",
        now_fn=lambda: 100.0,
    )

    with pytest.raises(service.TaskExpiredError):
        service.get_task("task-expired", now_fn=lambda: 1900.1)
    with pytest.raises(service.TaskNotFoundError):
        service.get_task("task-expired", now_fn=lambda: 1900.2)


def test_confirmation_rejects_changed_base_and_is_idempotent():
    service.run_segmentation(
        "task-confirm",
        "evt-1",
        "manual-1",
        "正文",
        chat_fn=lambda messages, **_kwargs: _core_from_messages(messages),
        now_fn=lambda: 100.0,
    )
    calls: list[tuple[str, str]] = []

    with pytest.raises(service.RevisionConflictError):
        service.mark_confirmed(
            "task-confirm",
            active_revision_id="manual-2",
            confirm_fn=lambda preview, base: "segmented-never",
            now_fn=lambda: 101.0,
        )

    def confirm(preview: str, base: str) -> str:
        calls.append((preview, base))
        return "segmented-1"

    first = service.mark_confirmed(
        "task-confirm",
        active_revision_id="manual-1",
        confirm_fn=confirm,
        now_fn=lambda: 102.0,
    )
    repeated = service.mark_confirmed(
        "task-confirm",
        active_revision_id="manual-2",
        confirm_fn=lambda _preview, _base: "segmented-2",
        now_fn=lambda: 103.0,
    )

    assert first == repeated == "segmented-1"
    assert calls == [("正文", "manual-1")]
    assert service.get_task("task-confirm", now_fn=lambda: 5000.0).status == "confirmed"


def test_registry_caps_retained_tasks_by_dropping_oldest_terminal_entries():
    for index in range(service.MAX_RETAINED_TASKS + 1):
        service.run_segmentation(
            f"task-cap-{index}",
            "evt-1",
            "manual-1",
            "正文",
            chat_fn=lambda messages, **_kwargs: _core_from_messages(messages),
            now_fn=lambda index=index: 10_000.0 + index,
        )

    with pytest.raises(service.TaskNotFoundError):
        service.get_task("task-cap-0", now_fn=lambda: 10_200.0)
    assert (
        service.get_task(
            f"task-cap-{service.MAX_RETAINED_TASKS}", now_fn=lambda: 10_200.0
        ).status
        == "ready"
    )


def test_segment_core_uses_constrained_ai_contract_and_registry_prompt():
    captured: dict[str, object] = {}

    def chat(messages, **kwargs):
        captured["messages"] = messages
        captured["kwargs"] = kwargs
        return _core_from_messages(messages)

    assert (
        service.segment_core("核心正文", "只读上文", "只读下文", chat_fn=chat)
        == "核心正文"
    )
    system_prompt = captured["messages"][0]["content"]
    assert "只允许增删或调整 Unicode 标点、空格和换行" in system_prompt
    assert captured["kwargs"] == {
        "temperature": 0.1,
        "max_tokens": 2048,
        "timeout": 180,
        "module": "ingest_pipeline",
        "task": "segment_transcript",
    }
    assert prompt_registry.MODULE_MAP["ingest_pipeline"]["segment_transcript"] == (
        "transcript_segmentation_service.py",
        ["segment_core"],
    )
    prompts = prompt_registry.get_all_prompts()["ingest_pipeline"]["segment_transcript"]
    assert any("不得补写、删减、替换或重排正文" in value for value in prompts.values())
