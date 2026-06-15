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

    presigned = client.create_pre_signed_url(
        HttpMethodType.GET,
        TOS_BUCKET,
        object_key,
        TOS_EXPIRES,
    )
    return presigned.signed_url if hasattr(presigned, "signed_url") else str(presigned)


def submit_transcription(audio_url: str) -> dict:
    """Submit audio for transcription and return response with task_id."""
    payload = {
        "app": {"appid": VOLC_API_KEY, "token": "placeholder", "cluster": VOLC_RESOURCE_ID},
        "user": {"uid": "ki-user"},
        "audio": {"url": audio_url, "format": "mp3"},
        "request": {
            "model_name": VOLC_MODEL_NAME,
            "enable_itn": True,
            "enable_punc": True,
            "enable_speaker_info": False,
        },
    }

    resp = requests.post(SUBMIT_URL, json=payload, timeout=30)
    resp.raise_for_status()
    return resp.json()


def query_transcription(task_id: str) -> dict:
    """Query transcription result by task_id."""
    payload = {
        "app": {"appid": VOLC_API_KEY, "token": "placeholder", "cluster": VOLC_RESOURCE_ID},
        "user": {"uid": "ki-user"},
        "request": {"model_name": VOLC_MODEL_NAME},
        "audio": {"task_id": task_id},
    }

    resp = requests.post(QUERY_URL, json=payload, timeout=30)
    resp.raise_for_status()
    return resp.json()


def transcribe(audio_path: Path, poll_interval: int = 3, max_wait: int = 300) -> str:
    """Full pipeline: upload → submit → poll → return transcript text."""
    # Upload
    audio_url = upload_to_tos(audio_path)

    # Submit
    submit_resp = submit_transcription(audio_url)
    task_id = submit_resp.get("result", {}).get("task_id") or submit_resp.get("task_id")
    if not task_id:
        raise RuntimeError(f"Volc submit failed: {submit_resp}")

    # Poll
    elapsed = 0
    while elapsed < max_wait:
        time.sleep(poll_interval)
        elapsed += poll_interval

        result = query_transcription(task_id)
        status = result.get("result", {}).get("status") or result.get("status", "")
        if status == "finished":
            # Extract text from response
            sentences = result.get("result", {}).get("sentences", [])
            if sentences:
                return "\n".join(s.get("text", "") for s in sentences)
            # Alternative field
            text = result.get("result", {}).get("text", "")
            if text:
                return text
            # Last resort
            return str(result)
        elif status in ("failed", "error"):
            raise RuntimeError(f"Volc transcription failed: {result}")

    raise TimeoutError(f"Volc transcription timed out after {max_wait}s")
