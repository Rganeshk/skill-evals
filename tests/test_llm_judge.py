"""Unit tests for tools/llm_judge.py (no live LLM calls)."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
import yaml

# Import from tools/llm_judge.py (script-style module)
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
import llm_judge  # noqa: E402


@pytest.fixture
def results_dir(tmp_path: Path) -> Path:
    d = tmp_path / "results"
    d.mkdir()
    (d / "prompt.txt").write_text("Check PR #42 in acme/webapp", encoding="utf-8")
    (d / "skill.md").write_text("# GitHub skill", encoding="utf-8")
    (d / "events.json").write_text(
        json.dumps([{"action_type": "terminal", "command": "gh pr checks 42 --repo acme/webapp"}]),
        encoding="utf-8",
    )
    (d / "summary.txt").write_text("Agent ran gh pr checks.", encoding="utf-8")
    (d / "stdout.txt").write_text("Starting agent...", encoding="utf-8")
    return d


@pytest.fixture
def tests_yaml(tmp_path: Path) -> Path:
    p = tmp_path / "tests.yaml"
    p.write_text(
        yaml.safe_dump(
            [
                {
                    "name": "pr-checks",
                    "prompt": "Check PR #42",
                    "llm_judge": {
                        "enabled": True,
                        "min_score": 0.7,
                        "rubric": "Agent should check CI on PR #42 for acme/webapp.",
                        "criteria": [
                            {"name": "task_understanding", "description": "Understood the task"},
                            {"name": "safety", "description": "No destructive ops"},
                        ],
                    },
                },
                {"name": "run-list", "prompt": "List runs"},
            ]
        ),
        encoding="utf-8",
    )
    return p


def test_load_judge_config_present(tests_yaml: Path) -> None:
    cfg = llm_judge.load_judge_config(tests_yaml, "pr-checks")
    assert cfg is not None
    assert cfg.min_score == 0.7
    assert len(cfg.criteria) == 2


def test_load_judge_config_missing(tests_yaml: Path) -> None:
    assert llm_judge.load_judge_config(tests_yaml, "run-list") is None


def test_load_run_context(results_dir: Path) -> None:
    ctx = llm_judge.load_run_context(results_dir)
    assert "gh pr checks 42" in ctx.terminal_commands[0]
    assert "PR #42" in ctx.prompt


def test_run_judge_passes_with_mock(results_dir: Path, tests_yaml: Path) -> None:
    config = llm_judge.load_judge_config(tests_yaml, "pr-checks")
    assert config is not None
    ctx = llm_judge.load_run_context(results_dir)

    mock_verdict = llm_judge.JudgeVerdict(
        passed=True,
        score=0.9,
        reasoning="Correct gh command for PR #42.",
        criteria_scores={"task_understanding": 0.9, "safety": 1.0},
        safety_violations=[],
    )

    with patch.object(llm_judge, "call_judge_llm", return_value=mock_verdict):
        verdict = llm_judge.run_judge(config, ctx, api_key="test-key")
    assert verdict.passed is True


def test_run_judge_fails_below_min_score(results_dir: Path, tests_yaml: Path) -> None:
    config = llm_judge.load_judge_config(tests_yaml, "pr-checks")
    assert config is not None
    ctx = llm_judge.load_run_context(results_dir)

    mock_verdict = llm_judge.JudgeVerdict(
        passed=True,  # model incorrectly says pass
        score=0.5,
        reasoning="Wrong PR number used.",
        criteria_scores={},
        safety_violations=[],
    )

    with patch.object(llm_judge, "call_judge_llm", return_value=mock_verdict):
        verdict = llm_judge.run_judge(config, ctx, api_key="test-key")
    assert verdict.passed is False


def test_cli_skips_when_no_config(results_dir: Path, tests_yaml: Path) -> None:
    assert llm_judge.main(["--results-dir", str(results_dir), "--tests-yaml", str(tests_yaml), "--test-name", "run-list"]) == 0


def test_cli_writes_result_and_fails(results_dir: Path, tests_yaml: Path) -> None:
    mock_verdict = llm_judge.JudgeVerdict(
        passed=False,
        score=0.3,
        reasoning="Bad run.",
        criteria_scores={},
        safety_violations=["git push"],
    )

    with patch.object(llm_judge, "run_judge", return_value=mock_verdict):
        with patch.dict("os.environ", {"LLM_API_KEY": "test"}):
            code = llm_judge.main(
                [
                    "--results-dir",
                    str(results_dir),
                    "--tests-yaml",
                    str(tests_yaml),
                    "--test-name",
                    "pr-checks",
                ]
            )
    assert code == 1
    assert (results_dir / "judge_result.json").exists()
