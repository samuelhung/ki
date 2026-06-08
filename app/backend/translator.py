"""Translate English news content to Chinese using DeepSeek API."""

from __future__ import annotations

import json
import logging
import os
import urllib.request
from dataclasses import dataclass
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class TranslationResult:
    text: str
    success: bool
    error: str | None = None


def _deepseek_api_key() -> str | None:
    key = os.getenv("DEEPSEEK_API_KEY", "")
    if not key or key == "***":
        return None
    return key


def _deepseek_base_url() -> str:
    return os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com")


def _call_deepseek(system_prompt: str, user_prompt: str, max_tokens: int, timeout: int) -> TranslationResult:
    api_key = _deepseek_api_key()
    if not api_key:
        return TranslationResult(text="", success=False, error="DEEPSEEK_API_KEY not configured")

    payload: dict[str, Any] = {
        "model": "deepseek-chat",
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        "temperature": 0.3,
        "max_tokens": max_tokens,
    }

    data = json.dumps(payload).encode("utf-8")
    base_url = _deepseek_base_url().rstrip("/")
    url = f"{base_url}/v1/chat/completions"

    req = urllib.request.Request(
        url,
        data=data,
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}",
        },
        method="POST",
    )

    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = json.loads(resp.read().decode("utf-8"))
            content = body["choices"][0]["message"]["content"].strip()
            return TranslationResult(text=content, success=True)
    except urllib.error.HTTPError as e:
        error_body = ""
        try:
            error_body = e.read().decode("utf-8")[:200]
        except Exception as read_err:
            logger.warning("Failed to read DeepSeek error body: %s", read_err)
        msg = f"HTTP {e.code}: {error_body}"
        logger.warning("DeepSeek translation HTTP error: %s", msg)
        return TranslationResult(text="", success=False, error=msg)
    except Exception as e:
        msg = str(e)[:200]
        logger.warning("DeepSeek translation network error: %s", msg)
        return TranslationResult(text="", success=False, error=msg)


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
