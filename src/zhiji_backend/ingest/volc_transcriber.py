"""Volcengine transcription — TOS upload + AUC bigmodel async transcription."""

from __future__ import annotations

import os
import time
import uuid
from pathlib import Path

import requests  # type: ignore

TOS_EXPIRES = 7200

SUBMIT_URL = "https://openspeech.bytedance.com/api/v3/auc/bigmodel/submit"
QUERY_URL = "https://openspeech.bytedance.com/api/v3/auc/bigmodel/query"


def _env(name: str, default: str = "") -> str:
    return os.getenv(name, default).strip()


def _volc_headers(req_id: str, logid: str | None = None) -> dict[str, str]:
    api_key = _env("VOLC_API_KEY") or _env("VOLC_APP_KEY")
    if not api_key:
        raise RuntimeError("VOLC_API_KEY 未配置，无法调用火山 AUC 转写")

    headers = {
        "X-Api-Key": api_key,
        "X-Api-Resource-Id": _env("VOLC_RESOURCE_ID", "volc.seedasr.auc"),
        "X-Api-Request-Id": req_id,
    }
    if logid:
        headers["X-Tt-Logid"] = logid
    else:
        headers["X-Api-Sequence"] = "-1"
    return headers


def upload_to_tos(audio_path: Path) -> str:
    """Upload audio to volc TOS and return a public download URL."""
    try:
        from tos import TosClientV2  # type: ignore
    except ImportError as e:
        raise RuntimeError("缺少依赖 tos：请先安装 `pip install tos`") from e

    client = TosClientV2(
        ak=_env("TOS_AK"),
        sk=_env("TOS_SK"),
        endpoint=_env("TOS_ENDPOINT", "tos-cn-beijing.volces.com"),
        region=_env("TOS_REGION", "cn-beijing"),
    )
    object_key = f"asr-upload/{uuid.uuid4().hex}{audio_path.suffix}"

    bucket = _env("TOS_BUCKET", "douyin11")
    client.put_object_from_file(bucket, object_key, str(audio_path))

    # Generate presigned URL for public access
    from tos.enum import HttpMethodType  # type: ignore

    presigned = client.pre_signed_url(
        HttpMethodType.Http_Method_Get,
        bucket,
        object_key,
        TOS_EXPIRES,
    )
    return presigned.signed_url


def submit_transcription(audio_url: str) -> tuple[str, str]:
    """Submit an audio URL to volc AUC for async transcription.

    Returns (request_id, log_id) tuple.
    """
    req_id = str(uuid.uuid4())
    resp = requests.post(
        SUBMIT_URL,
        json={
            "user": {"uid": "ki-local"},
            "audio": {
                "url": audio_url,
                "format": "wav",
            },
            "request": {
                "model_name": _env("VOLC_MODEL_NAME", "bigmodel"),
                "enable_punc": True,
                "enable_itn": True,
            },
        },
        headers=_volc_headers(req_id),
        timeout=15,
    )

    status = resp.headers.get("X-Api-Status-Code")
    msg = resp.headers.get("X-Api-Message", "")
    if status != "20000000":
        raise RuntimeError(f"volc AUC 提交失败：status={status}, msg={msg}")

    logid = resp.headers.get("X-Tt-Logid", "")
    return req_id, logid


def poll_result(req_id: str, logid: str, max_attempts: int = 200) -> str:
    """Poll volc AUC for transcription result.

    Returns transcribed text when done.

    Raises:
        RuntimeError: On API error.
        TimeoutError: If max_attempts exceeded.
    """
    for _ in range(max_attempts):
        time.sleep(3)

        resp = requests.post(
            QUERY_URL,
            json={},
            headers=_volc_headers(req_id, logid),
            timeout=15,
        )

        status = resp.headers.get("X-Api-Status-Code")
        if status == "20000000":
            data = resp.json()
            return data["result"]["text"]
        elif status != "20000001":
            raise RuntimeError(f"volc AUC 查询失败：status={status}")

    raise TimeoutError(f"转写超时（{max_attempts} 次轮询后仍未完成）")


def transcribe(audio_path: Path) -> str:
    """Full transcription pipeline: upload to TOS → submit to volc AUC → poll for result.

    Returns transcribed text.
    """
    audio_url = upload_to_tos(audio_path)
    req_id, logid = submit_transcription(audio_url)
    return poll_result(req_id, logid)
