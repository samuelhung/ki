from unittest.mock import patch

from fastapi.testclient import TestClient

from zhiji_backend.main import app
from zhiji_backend.routes.study_routes import _normalize_review_result
from zhiji_backend.study.pipeline import _parse_json_object

client = TestClient(app)


def test_normalize_review_result_sets_persisted_review_fields():
    assert _normalize_review_result({
        "score": 72,
        "mistake_tags": ["审题"],
        "review_content": "复盘内容",
    }) == {
        "score": 72,
        "mistake_tags": ["审题"],
        "review_content": "复盘内容",
        "status": "reviewed",
        "is_correct": 0,
    }


def test_normalize_review_result_handles_text_extension_response():
    assert _normalize_review_result("复盘内容") == {
        "review_content": "复盘内容",
        "status": "reviewed",
        "is_correct": 0,
        "mistake_tags": [],
    }


def test_parse_json_object_accepts_fenced_ai_output():
    assert _parse_json_object('```json\n{"is_correct":0,"mistake_tags":["审题"]}\n```') == {
        "is_correct": 0,
        "mistake_tags": ["审题"],
    }


@patch("zhiji_backend.ingest.pdf_ocr.process_pdf", return_value={"text": "recognized"})
def test_study_upload_accepts_minimal_valid_pdf(mock_process_pdf):
    response = client.post(
        "/api/study/upload",
        data={"category": "练习"},
        files={"file": ("sheet.pdf", b"%PDF-1.4\n%%EOF\n", "application/pdf")},
    )

    assert response.status_code == 200
    assert response.json()["text"] == "recognized"


def test_study_upload_rejects_spoofed_pdf():
    response = client.post(
        "/api/study/upload",
        data={"category": "练习"},
        files={"file": ("sheet.pdf", b"not a pdf", "application/pdf")},
    )

    assert response.status_code == 422


@patch("zhiji_backend.routes.study_routes.max_bytes_for_kind", return_value=4)
def test_study_upload_rejects_oversized_image(mock_limit):
    response = client.post(
        "/api/study/upload",
        files={"file": ("page.png", b"\x89PNG\r\n\x1a\n", "image/png")},
    )

    assert response.status_code == 413


@patch("zhiji_backend.routes.study_routes._ocr_image_path", return_value="题目内容")
def test_study_upload_image_accepts_minimal_valid_image(mock_ocr):
    response = client.post(
        "/api/study/upload-image",
        files={"file": ("page.jpg", b"\xff\xd8\xff\xe0" + b"x" * 16, "image/jpeg")},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "draft"
    detail = client.get(f"/api/study/{data['material_id']}")
    assert detail.json()["raw_content"] == "题目内容"


def test_study_upload_image_rejects_spoofed_image():
    response = client.post(
        "/api/study/upload-image",
        files={"file": ("page.jpg", b"not a jpeg", "image/jpeg")},
    )

    assert response.status_code == 422
