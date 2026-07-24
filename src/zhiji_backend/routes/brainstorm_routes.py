"""Brainstorm question CRUD, answering, conversation, and contemplation endpoints."""

from __future__ import annotations

import logging
import uuid
from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, Query
from pydantic import BaseModel, field_validator

from .. import (
    brainstorm_answer_service,
    brainstorm_concept_service,
    brainstorm_contemplation_service,
    brainstorm_conversation_service,
    brainstorm_question_service,
)
from ..ai_client import chat
from ..classifier import classify_content
from ..db import connect
from ..paths import BRAINSTORM_DIR
from ..security.constraints import (
    MAX_OFFSET,
    MAX_PAGE_SIZE,
    BoundedIdentifierList,
    SafeIdentifier,
    SafeIdentifierList,
    safe_identifier,
)
from ..security.paths import resolve_under, safe_unlink_under

logger = logging.getLogger(__name__)

router = APIRouter()


def _brainstorm_md_path(question_id: str) -> Path:
    safe_identifier(question_id)
    return resolve_under(BRAINSTORM_DIR, f"{question_id}.md", must_exist=False)


def _safe_brainstorm_unlink(question_id: str) -> None:
    try:
        safe_unlink_under(BRAINSTORM_DIR, f"{question_id}.md")
    except Exception:
        logger.warning("Refusing to delete unsafe brainstorm artifact", exc_info=True)


@router.get("/api/brainstorm")
def list_brainstorm_questions(
    status: str | None = None,
    topic: str | None = None,
    offset: int = Query(0, ge=0, le=MAX_OFFSET),
    limit: int = Query(200, ge=1, le=MAX_PAGE_SIZE),
) -> dict[str, object]:
    """List brainstorm questions, newest first. Optional topic filter."""
    return brainstorm_question_service.list_brainstorm_questions(
        status,
        topic,
        offset,
        limit,
        connect_fn=connect,
        logger=logger,
    )


@router.get("/api/brainstorm/topic-counts")
def brainstorm_topic_counts() -> dict[str, int]:
    """Return question counts per topic for brainstorm tabs."""
    return brainstorm_question_service.brainstorm_topic_counts(
        connect_fn=connect, logger=logger
    )


@router.get("/api/brainstorm/{question_id}")
def get_brainstorm_question(question_id: SafeIdentifier) -> dict[str, object]:
    """Get a single brainstorm question with its answered_event_ids and latest answer."""
    return brainstorm_question_service.get_brainstorm_question(
        question_id,
        connect_fn=connect,
        markdown_path_fn=_brainstorm_md_path,
        logger=logger,
    )


def _extract_latest_answer(md_path: Path) -> str:
    return brainstorm_answer_service._extract_latest_answer(md_path)


class CreateQuestionRequest(BaseModel):
    question: str


@router.post("/api/brainstorm")
def create_brainstorm_question(request: CreateQuestionRequest) -> dict[str, object]:
    """Manually create a brainstorm question and its .md file."""
    return brainstorm_question_service.create_brainstorm_question(
        request,
        connect_fn=connect,
        classify_fn=classify_content,
        markdown_path_fn=_brainstorm_md_path,
        uuid_fn=uuid.uuid4,
        now_fn=datetime.now,
        logger=logger,
    )


@router.delete("/api/brainstorm/{question_id}")
def delete_brainstorm_question(question_id: SafeIdentifier) -> dict[str, object]:
    """Delete a brainstorm question and its .md file."""
    return brainstorm_question_service.delete_brainstorm_question(
        question_id,
        connect_fn=connect,
        unlink_fn=_safe_brainstorm_unlink,
        logger=logger,
    )


class QuestionBatchRequest(BaseModel):
    question_ids: SafeIdentifierList


@router.post("/api/brainstorm/batch-delete")
def batch_delete_brainstorm_questions(
    payload: QuestionBatchRequest,
) -> dict[str, object]:
    """Delete multiple brainstorm questions and their .md files."""
    return brainstorm_question_service.batch_delete_brainstorm_questions(
        payload,
        connect_fn=connect,
        unlink_fn=_safe_brainstorm_unlink,
        logger=logger,
    )


@router.post("/api/brainstorm/{question_id}/done")
def mark_brainstorm_done(question_id: SafeIdentifier) -> dict[str, object]:
    """Mark a brainstorm question as done."""
    return brainstorm_question_service.mark_brainstorm_done(
        question_id, connect_fn=connect, logger=logger
    )


class AnswerRequest(BaseModel):
    question_id: SafeIdentifier
    question: str
    event_ids: BoundedIdentifierList


@router.post("/api/brainstorm/answer")
def get_answer_for_question(request: AnswerRequest) -> dict[str, object]:
    """Given a brainstorm question and selected events, find the answer from the articles.
    Saves the answer to the question's .md file and tracks answered_event_ids.
    """
    return brainstorm_answer_service.get_answer_for_question(
        request,
        connect_fn=connect,
        chat_fn=chat,
        markdown_path_fn=_brainstorm_md_path,
        logger=logger,
        now_fn=datetime.now,
    )


# ---------------------------------------------------------------------------
# Conversation: multi-turn dialog + summary
# ---------------------------------------------------------------------------


class ConversationStartRequest(BaseModel):
    event_ids: SafeIdentifierList
    question: str


class ConversationMessageRequest(BaseModel):
    content: str


def _call_ai_chat(
    messages: list[dict],
    temperature: float = 0.3,
    max_tokens: int = 2000,
    module: str = "",
    task: str = "",
) -> str:
    return brainstorm_conversation_service._call_ai_chat(
        messages,
        temperature,
        max_tokens,
        module,
        task,
        chat_fn=chat,
    )


def _build_reference_docs(event_ids: list[str]) -> tuple[list[dict], dict[str, str]]:
    return brainstorm_conversation_service._build_reference_docs(
        event_ids, connect_fn=connect
    )


def _build_conversation_messages(
    question_id: str, role_filter: bool = True
) -> list[dict]:
    return brainstorm_conversation_service._build_conversation_messages(
        question_id, role_filter, connect_fn=connect
    )


def _parse_refs_from_answer(answer: str, id_to_idx: dict[str, str]) -> list[str]:
    return brainstorm_conversation_service._parse_refs_from_answer(answer, id_to_idx)


@router.post("/api/brainstorm/{question_id}/conversation/start")
def start_conversation(
    question_id: SafeIdentifier, request: ConversationStartRequest
) -> dict[str, object]:
    """Start a new conversation thread: lock reference docs, generate first answer."""
    return brainstorm_conversation_service.start_conversation(
        question_id,
        request,
        connect_fn=connect,
        call_ai_chat_fn=_call_ai_chat,
        build_reference_docs_fn=_build_reference_docs,
        parse_refs_fn=_parse_refs_from_answer,
        markdown_path_fn=_brainstorm_md_path,
        now_fn=datetime.now,
        logger=logger,
    )


@router.post("/api/brainstorm/{question_id}/conversation/message")
def send_conversation_message(
    question_id: SafeIdentifier, request: ConversationMessageRequest
) -> dict[str, object]:
    """Send a follow-up question in an existing conversation thread."""
    return brainstorm_conversation_service.send_conversation_message(
        question_id,
        request,
        connect_fn=connect,
        call_ai_chat_fn=_call_ai_chat,
        build_reference_docs_fn=_build_reference_docs,
        build_conversation_messages_fn=_build_conversation_messages,
        parse_refs_fn=_parse_refs_from_answer,
        markdown_path_fn=_brainstorm_md_path,
        now_fn=datetime.now,
        logger=logger,
    )


@router.get("/api/brainstorm/{question_id}/conversation")
def get_conversation(question_id: SafeIdentifier) -> dict[str, object]:
    """Get the full conversation history + locked event IDs for a question."""
    return brainstorm_conversation_service.get_conversation(
        question_id, connect_fn=connect
    )


@router.post("/api/brainstorm/{question_id}/conversation/summary")
def generate_conversation_summary(question_id: SafeIdentifier) -> dict[str, object]:
    """Generate a structured summary of the full conversation thread."""
    return brainstorm_conversation_service.generate_conversation_summary(
        question_id,
        connect_fn=connect,
        call_ai_chat_fn=_call_ai_chat,
        build_reference_docs_fn=_build_reference_docs,
        build_conversation_messages_fn=_build_conversation_messages,
        parse_refs_fn=_parse_refs_from_answer,
        markdown_path_fn=_brainstorm_md_path,
        now_fn=datetime.now,
        logger=logger,
    )


# ---------------------------------------------------------------------------
# Contemplate: bidirectional matching between events and brainstorm questions
# ---------------------------------------------------------------------------


class ContemplateRequest(BaseModel):
    direction: str  # "event_to_questions" or "question_to_events"
    entity_id: str

    @field_validator("entity_id")
    @classmethod
    def validate_entity_id(cls, value: str) -> str:
        return safe_identifier(value)


@router.post("/api/brainstorm/contemplate")
def contemplate(request: ContemplateRequest) -> dict[str, object]:
    """Bidirectional smart matching:
    - event_to_questions: given an event, find brainstorm questions it might answer
    - question_to_events: given a question, find events that might answer it
    Skips already-linked pairs.
    """
    return brainstorm_contemplation_service.contemplate(
        request,
        contemplate_event_to_questions_fn=_contemplate_event_to_questions,
        contemplate_question_to_events_fn=_contemplate_question_to_events,
    )


@router.get("/api/brainstorm/event/{event_id}/linked-questions")
def get_linked_questions(event_id: SafeIdentifier) -> dict[str, object]:
    """Return brainstorm questions already linked to this event via brainstorm_event_links."""
    return brainstorm_contemplation_service.get_linked_questions(
        event_id, connect_fn=connect
    )


def _contemplate_event_to_questions(event_id: str) -> dict[str, object]:
    return brainstorm_contemplation_service._contemplate_event_to_questions(
        event_id,
        connect_fn=connect,
        call_contemplate_deepseek_fn=_call_contemplate_deepseek,
    )


def _contemplate_question_to_events(question_id: str) -> dict[str, object]:
    return brainstorm_contemplation_service._contemplate_question_to_events(
        question_id,
        connect_fn=connect,
        call_contemplate_deepseek_fn=_call_contemplate_deepseek,
    )


def _call_contemplate_deepseek(prompt: str) -> list[dict]:
    return brainstorm_contemplation_service._call_contemplate_deepseek(
        prompt, chat_fn=chat, logger=logger
    )


# ---------------------------------------------------------------------------
# Concept precipitation: extract concepts from summary and save to event store
# ---------------------------------------------------------------------------

class PrecipitateConceptRequest(BaseModel):
    question_id: SafeIdentifier
    name: str
    description: str = ""


def _create_concept(
    title: str,
    topic: str,
    description: str = "",
    force_ai: bool = False,
    context_docs: list[dict[str, str]] | None = None,
) -> dict:
    from ..routes.ingest_routes import _create_concept as create_concept

    return create_concept(
        title,
        topic,
        description,
        force_ai=force_ai,
        context_docs=context_docs,
    )


_DEFAULT_CREATE_CONCEPT = _create_concept


@router.get("/api/brainstorm/{question_id}/concepts")
def list_summary_concepts(question_id: SafeIdentifier) -> dict[str, object]:
    """Parse concepts from the summary — both primary concepts (概念定义) and related concepts (相关概念).
    Returns each concept with its description and whether it already exists in the system."""
    return brainstorm_concept_service.list_summary_concepts(
        question_id, connect_fn=connect
    )


@router.post("/api/brainstorm/concepts/precipitate")
def precipitate_concept(req: PrecipitateConceptRequest) -> dict[str, object]:
    """Save a concept from the brainstom summary into the event store as a concept entry."""
    from ..routes.ingest_routes import _create_concept as ingest_create_concept

    create_concept_fn = (
        ingest_create_concept
        if _create_concept is _DEFAULT_CREATE_CONCEPT
        else _create_concept
    )
    return brainstorm_concept_service.precipitate_concept(
        req,
        connect_fn=connect,
        build_reference_docs_fn=_build_reference_docs,
        create_concept_fn=create_concept_fn,
        logger=logger,
    )
