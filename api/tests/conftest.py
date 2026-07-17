"""Test fixtures. Runs the API in dev posture against an isolated SQLite file."""
import os, sys, tempfile, pathlib

# import the api package (tests live in api/tests, app modules in api/)
API_DIR = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(API_DIR))

os.environ.setdefault("APP_ENV", "dev")
os.environ.setdefault("AUTH_DISABLED", "1")
os.environ.setdefault("APP_DB_PATH", os.path.join(tempfile.gettempdir(), "cfc_test_app.db"))

import pytest
from fastapi.testclient import TestClient


@pytest.fixture(scope="session")
def client():
    from main import app
    with TestClient(app) as c:
        yield c
