from unittest.mock import patch

from fastapi.testclient import TestClient

from zhiji_backend.main import app
from zhiji_backend.routes import study_routes
from zhiji_backend.routes.study_routes import _normalize_review_result
from zhiji_backend.study.pipeline import _parse_json_object

client = TestClient(app)


def test_static_study_routes_reach_their_declared_endpoints(monkeypatch):
    def response_for(endpoint):
        return lambda *args, **kwargs: {"endpoint": endpoint}

    monkeypatch.setattr(
        study_routes._material, "get_material", response_for("get_material")
    )
    monkeypatch.setattr(
        study_routes._material, "list_materials", response_for("list_materials")
    )
    monkeypatch.setattr(
        study_routes._material, "list_mistakes", response_for("list_mistakes")
    )
    monkeypatch.setattr(study_routes._material, "get_stats", response_for("get_stats"))
    monkeypatch.setattr(
        study_routes._material, "create_material", response_for("create_material")
    )
    monkeypatch.setattr(
        study_routes._intake, "upload_and_ocr", response_for("upload_and_ocr")
    )
    monkeypatch.setattr(
        study_routes._intake, "upload_image", response_for("upload_image")
    )

    responses = {
        "list_materials": client.get("/api/study/list"),
        "list_mistakes": client.get("/api/study/mistakes/list"),
        "get_stats": client.get("/api/study/stats"),
        "create_material": client.post(
            "/api/study/create", json={"subject": "语文", "study_type": "阅读"}
        ),
        "upload_and_ocr": client.post(
            "/api/study/upload", files={"file": ("sheet.pdf", b"data")}
        ),
        "upload_image": client.post(
            "/api/study/upload-image", files={"file": ("page.jpg", b"data")}
        ),
    }

    for endpoint, response in responses.items():
        assert response.status_code == 200
        assert response.json() == {"endpoint": endpoint}


def test_normalize_review_result_sets_persisted_review_fields():
    assert _normalize_review_result(
        {
            "score": 72,
            "mistake_tags": ["审题"],
            "review_content": "复盘内容",
        }
    ) == {
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
    assert _parse_json_object(
        '```json\n{"is_correct":0,"mistake_tags":["审题"]}\n```'
    ) == {
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
