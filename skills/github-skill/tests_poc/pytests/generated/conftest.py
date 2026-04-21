"""Generated (POC) shared fixtures for skill grading tests.

These fixtures load the OpenHands event log produced by `run_agent.py`.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest


def _load_events() -> list[dict]:
    events_path = os.environ.get("EVENTS_JSON", "/workspace/output/events.json")
    path = Path(events_path)
    if not path.exists():
        pytest.fail(f"Event log not found at {events_path}")
    return json.loads(path.read_text())


@pytest.fixture(scope="session")
def events() -> list[dict]:
    return _load_events()


@pytest.fixture(scope="session")
def terminal_commands(events: list[dict]) -> list[str]:
    return [
        e["command"]
        for e in events
        if e.get("action_type") == "terminal" and e.get("command")
    ]
