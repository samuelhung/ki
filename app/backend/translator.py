"""Translate English news content to Chinese using DeepSeek API."""

from __future__ import annotations

import logging
from dataclasses import dataclass

from .deepseek_client import chat

logger = logging.getLogger(__name__)


@dataclass
class TranslationResult:
    text: str
    success: bool
    error: str | None = None


def _call_deepseek(system_prompt: str, user_prompt: str, max_tokens: int, timeout: int) -> TranslationResult:
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt},
    ]
    content = chat(messages, temperature=0.3, max_tokens=max_tokens, timeout=timeout)
    if content is None:
        return TranslationResult(text="", success=False, error="DeepSeek API not configured or call failed")
    return TranslationResult(text=content, success=True)


def translate(text: str, max_chars: int = 5000) -> TranslationResult:
    """Translate English text to Chinese using DeepSeek Chat API."""
    if not text or not text.strip():
        return TranslationResult(text=text, success=True)

    truncated = text[:max_chars] if len(text) > max_chars else text

    system_prompt = (
        "你是一个专业的新闻翻译助手。将以下英文新闻内容翻译成简洁流畅的中文。"
        "要求：\n"
        "1. 保持原意，不添加不存在的细节\n"
        "2. 中文风格自然流畅，符合新闻语体\n"
        "3. 保留专有名词（人名、地名、公司名）的英文原名\n"
        "4. 只输出翻译结果，不要加任何解释或前缀"
    )

    return _call_deepseek(
        system_prompt=system_prompt,
        user_prompt=f"请翻译以下新闻内容：\n\n{truncated}",
        max_tokens=4096,
        timeout=60,
    )


def translate_title(title: str) -> TranslationResult:
    """Translate a news title to Chinese (short, optimized prompt)."""
    if not title or not title.strip():
        return TranslationResult(text=title, success=True)

    system_prompt = (
        "你是一个专业的新闻标题翻译助手。将英文新闻标题翻译成简洁的中文。"
        "只输出翻译结果，不要加引号、解释或前缀。"
    )

    return _call_deepseek(
        system_prompt=system_prompt,
        user_prompt=f"翻译：{title}",
        max_tokens=256,
        timeout=30,
    )
