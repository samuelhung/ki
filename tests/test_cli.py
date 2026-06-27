import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from zhiji_backend.cli import _parse_version


def test_parse_version_supports_build_metadata():
    assert _parse_version("v1.3.8+83") == (1, 3, 8, 83)
    assert _parse_version("1.3.9") == (1, 3, 9)
    assert _parse_version("v1.4.0-beta+2") == (1, 4, 0, 2)
