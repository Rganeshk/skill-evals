"""Shared fixtures for GitHub skill grading tests.

Loads the OpenHands event log from events.json (written by run_agent.py)
and provides fixtures for inspecting terminal commands, file edits, and
conversation summary — matching the patterns used in the existing
OpenHands behavior tests (b07-b35).
"""
from __future__ import annotations

import json
import os
from pathlib import Path

import pytest


def _load_events() -> list[dict]:
    """Load the event log produced by run_agent.py."""
    events_path = os.environ.get(
        "EVENTS_JSON", "/workspace/output/events.json"
    )
    path = Path(events_path)
    if not path.exists():
        pytest.fail(f"Event log not found at {events_path}")
    with open(path) as f:
        return json.load(f)


def _load_summary() -> str:
    """Load the conversation summary produced by run_agent.py."""
    summary_path = os.environ.get(
        "SUMMARY_TXT", "/workspace/output/summary.txt"
    )
    path = Path(summary_path)
    if not path.exists():
        return ""
    return path.read_text()


@pytest.fixture(scope="session")
def events() -> list[dict]:
    """Full event log as a list of dicts."""
    return _load_events()


@pytest.fixture(scope="session")
def terminal_commands(events: list[dict]) -> list[str]:
    """All terminal commands the agent executed.

    Equivalent to _extract_terminal_commands() in the OpenHands behavior tests.
    """
    return [
        e["command"]
        for e in events
        if e.get("action_type") == "terminal" and e.get("command")
    ]


@pytest.fixture(scope="session")
def terminal_events(events: list[dict]) -> list[dict]:
    """All terminal action events (with command, exit_code, etc.)."""
    return [e for e in events if e.get("action_type") == "terminal"]


@pytest.fixture(scope="session")
def file_edit_events(events: list[dict]) -> list[dict]:
    """All file editing events."""
    return [
        e for e in events
        if e.get("type") == "ActionEvent"
        and e.get("file_command") in ("create", "str_replace", "insert", "undo_edit")
    ]


@pytest.fixture(scope="session")
def conversation_summary() -> str:
    """Human-readable conversation summary."""
    return _load_summary()


@pytest.fixture(scope="session")
def agent_output() -> str:
    """Raw stdout from the agent run (for backward compat with skilltest pattern)."""
    stdout_path = os.environ.get(
        "STDOUT_TXT", "/workspace/output/stdout.txt"
    )
    path = Path(stdout_path)
    return path.read_text() if path.exists() else ""
