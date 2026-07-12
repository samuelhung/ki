from zhiji_backend.routes.study_routes import _normalize_review_result
from zhiji_backend.study.pipeline import _parse_json_object


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
