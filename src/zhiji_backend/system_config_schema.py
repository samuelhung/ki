"""Strict request schemas for the system configuration API."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class StrictConfigModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class TaskConfigUpdate(StrictConfigModel):
    temperature: float | None = None
    max_tokens: int | None = None
    thinking: bool | None = None


class GeneralConfigUpdate(StrictConfigModel):
    model: str | None = None
    base_url: str | None = None
    api_key: str | None = None
    disk_cache: bool | None = None
    default_temperature: float | None = None
    default_max_tokens: int | None = None
    default_thinking: bool | None = None
    reasoning_effort: str | None = None


class IngestPipelineConfigUpdate(StrictConfigModel):
    summarize: TaskConfigUpdate | None = None
    classify: TaskConfigUpdate | None = None
    tag: TaskConfigUpdate | None = None
    translate: TaskConfigUpdate | None = None


class SeriesConfigUpdate(StrictConfigModel):
    discover: TaskConfigUpdate | None = None
    discover_stage1: TaskConfigUpdate | None = None
    discover_stage2: TaskConfigUpdate | None = None
    discover_by_topic: TaskConfigUpdate | None = None
    expand: TaskConfigUpdate | None = None
    suggest_name: TaskConfigUpdate | None = None
    intro: TaskConfigUpdate | None = None
    summary: TaskConfigUpdate | None = None
    paper: TaskConfigUpdate | None = None
    auto_suggest: TaskConfigUpdate | None = None


class BrainstormConfigUpdate(StrictConfigModel):
    answer: TaskConfigUpdate | None = None
    summary: TaskConfigUpdate | None = None
    contemplate: TaskConfigUpdate | None = None
    concept_extract: TaskConfigUpdate | None = None


class BriefingConfigUpdate(StrictConfigModel):
    briefing_quick: TaskConfigUpdate | None = None
    briefing_daily: TaskConfigUpdate | None = None


class TasksConfigUpdate(StrictConfigModel):
    judge: TaskConfigUpdate | None = None


class ConceptConfigUpdate(StrictConfigModel):
    auto_complete: TaskConfigUpdate | None = None


class StudyConfigUpdate(StrictConfigModel):
    math_应用题: TaskConfigUpdate | None = None
    英语_阅读理解: TaskConfigUpdate | None = None
    语文_阅读理解: TaskConfigUpdate | None = None
    study_mistake_review: TaskConfigUpdate | None = None
    mistake_review: TaskConfigUpdate | None = None
    lecture_notes: TaskConfigUpdate | None = None


class ChainAnalysisConfigUpdate(StrictConfigModel):
    analyze: TaskConfigUpdate | None = None
    report: TaskConfigUpdate | None = None
    extract_hints: TaskConfigUpdate | None = None


class ChainDataUpdateConfigUpdate(StrictConfigModel):
    ai_update: TaskConfigUpdate | None = None


class ChainDataCollectConfigUpdate(StrictConfigModel):
    ai_collect: TaskConfigUpdate | None = None


class ChainMetaConfigUpdate(StrictConfigModel):
    suggest_icon: TaskConfigUpdate | None = None


class ChainChatConfigUpdate(StrictConfigModel):
    chat: TaskConfigUpdate | None = None


class ChainDetectorConfigUpdate(StrictConfigModel):
    detect_hints: TaskConfigUpdate | None = None
    detect_new_chains: TaskConfigUpdate | None = None


class SystemConfigUpdate(StrictConfigModel):
    general: GeneralConfigUpdate | None = None
    ingest_pipeline: IngestPipelineConfigUpdate | None = None
    series: SeriesConfigUpdate | None = None
    brainstorm: BrainstormConfigUpdate | None = None
    briefing: BriefingConfigUpdate | None = None
    tasks: TasksConfigUpdate | None = None
    concept: ConceptConfigUpdate | None = None
    study: StudyConfigUpdate | None = None
    chain_analysis: ChainAnalysisConfigUpdate | None = None
    chain_data_update: ChainDataUpdateConfigUpdate | None = None
    chain_data_collect: ChainDataCollectConfigUpdate | None = None
    chain_meta: ChainMetaConfigUpdate | None = None
    chain_chat: ChainChatConfigUpdate | None = None
    chain_detector: ChainDetectorConfigUpdate | None = None
