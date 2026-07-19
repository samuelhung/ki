import atexit
import os
import shutil
import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
TEST_ZHIJI_HOME = Path(tempfile.mkdtemp(prefix="zhiji-pytest-home-")).resolve()
os.environ["ZHIJI_HOME"] = str(TEST_ZHIJI_HOME)

from zhiji_backend.db import init_db

init_db()


def _remove_test_home() -> None:
    shutil.rmtree(TEST_ZHIJI_HOME, ignore_errors=True)


atexit.register(_remove_test_home)


def pytest_sessionfinish(session, exitstatus) -> None:
    _remove_test_home()
