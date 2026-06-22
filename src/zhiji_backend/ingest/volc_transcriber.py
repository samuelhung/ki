"""Volcengine transcription — TOS upload + AUC bigmodel async transcription."""

from __future__ import annotations

import os
import time
import uuid
from pathlib import Path

import requests  # type: ignore

VOLC_API_KEY = os.getenv("VOLC_API_KEY", "")
VOLC_RESOURCE_ID = os.getenv("VOLC_RESOURCE_ID", "volc.seedasr.auc")
VOLC_MODEL_NAME = os.getenv("VOLC_MODEL_NAME", "bigmodel")
TOS_ENDPOINT = os.getenv("TOS_ENDPOINT", "tos-cn-beijing.volces.com")
TOS_REGION = os.getenv("TOS_REGION", "cn-beijing")
TOS_BUCKET = os.getenv("TOS_BUCKET", "douyin11")
TOS_AK = os.getenv("TOS_AK", "")
TOS_SK = os.getenv("TOS_SK", "")
TOS_EXPIRES = 7200

SUBMIT_URL = "https://openspeech.bytedance.com/api/v3/auc/bigmodel/submit"
QUERY_URL = "https://openspeech.bytedance.com/api/v3/auc/bigmodel/query"


def upload_to_tos(audio_path: Path) -> str:
    """Upload audio to volc TOS and return a public download URL."""
    try:
        from tos import TosClientV2  # type: ignore
    except ImportError as e:
        raise RuntimeError("缺少依赖 tos：请先安装 `pip install tos`") from e

    client = TosClientV2(ak=TOS_AK, sk=TOS_SK, endpoint=TOS_ENDPOINT, region=TOS_REGION)
    object_key = f"asr-upload/{uuid.uuid4().hex}{audio_path.suffix}"

    client.put_object_from_file(TOS_BUCKET, object_key, str(audio_path))

    # Generate presigned URL for public access
    from tos.enum import HttpMethodType  # type: ignore

    presigned = client.pre_signed_url(
        HttpMethodType.Http_Method_Get,
        TOS_BUCKET,
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
                "model_name": VOLC_MODEL_NAME,
                "enable_punc": True,
                "enable_itn": True,
            },
        },
        headers={
            "X-Api-Key": VOLC_API_KEY,
            "X-Api-Resource-Id": VOLC_RESOURCE_ID,
            "X-Api-Request-Id": req_id,
            "X-Api-Sequence": "-1",
        },
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
            headers={
                "X-Api-Key": VOLC_API_KEY,
                "X-Api-Resource-Id": VOLC_RESOURCE_ID,
                "X-Api-Request-Id": req_id,
                "X-Tt-Logid": logid,
            },
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
