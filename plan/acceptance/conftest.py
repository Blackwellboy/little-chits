"""Shared fixtures for acceptance tests. Part of the contract: do not edit."""

import socket
import sys
import threading
import time
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
for p in (ROOT / "server", ROOT / "tests"):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))


def free_port() -> int:
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


@pytest.fixture(scope="session")
def fake_llm_url():
    """An OpenAI-compatible fake model on a random port (see tests/fake_llm.py)."""
    import uvicorn
    import fake_llm as F

    F.STATE["latency"] = 0.02
    F.STATE["garbage_rate"] = 0.0
    port = free_port()
    server = uvicorn.Server(uvicorn.Config(F.app, host="127.0.0.1", port=port, log_level="error"))
    th = threading.Thread(target=server.run, daemon=True)
    th.start()
    for _ in range(200):
        if server.started:
            break
        time.sleep(0.05)
    yield f"http://127.0.0.1:{port}/v1"
    server.should_exit = True
    th.join(timeout=5)


@pytest.fixture
def dead_url():
    return f"http://127.0.0.1:{free_port()}/v1"
