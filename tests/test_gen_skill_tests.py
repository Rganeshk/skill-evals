"""Unit tests for tools/gen_skill_tests.py."""

from __future__ import annotations

import sys
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
import gen_skill_tests  # noqa: E402


def test_default_llm_judge_includes_safety_when_forbid_present() -> None:
    case = gen_skill_tests.EvalCase(
        id="pr-checks",
        prompt="Check PR #42",
        terminal_contains=gen_skill_tests.TerminalContains(all=["gh", "pr", "checks"]),
        forbid=["git push"],
    )
    cfg = gen_skill_tests.default_llm_judge(case)
    assert cfg.enabled is True
    assert cfg.min_score == gen_skill_tests.DEFAULT_MIN_SCORE
    assert "git push" in cfg.rubric
    assert any(c.name == "safety" for c in cfg.criteria)


def test_resolve_llm_judge_honors_override_rubric() -> None:
    case = gen_skill_tests.EvalCase(
        id="run-list",
        prompt="List runs",
        terminal_contains=gen_skill_tests.TerminalContains(all=["gh", "run", "list"]),
        forbid=[],
    )
    override = {"rubric": "Custom rubric for workflow listing.", "min_score": 0.8}
    cfg = gen_skill_tests.resolve_llm_judge(case, override, emit_judge=True, index=0)
    assert cfg is not None
    assert cfg.rubric == "Custom rubric for workflow listing."
    assert cfg.min_score == 0.8
    # Default criteria when override omits criteria
    assert any(c.name == "tool_use_quality" for c in cfg.criteria)


def test_resolve_llm_judge_disabled_via_enabled_false() -> None:
    case = gen_skill_tests.EvalCase(
        id="x",
        prompt="p",
        terminal_contains=gen_skill_tests.TerminalContains(all=["gh"]),
        forbid=[],
    )
    assert gen_skill_tests.resolve_llm_judge(
        case, {"enabled": False}, emit_judge=True, index=0
    ) is None


def test_build_tests_yaml_emits_llm_judge_and_correct_paths(tmp_path: Path) -> None:
    skill_dir = tmp_path / "skill"
    out_dir = skill_dir / "tests_poc"
    out_dir.mkdir(parents=True)

    case = gen_skill_tests.EvalCase(
        id="pr-checks",
        prompt="Check PR",
        terminal_contains=gen_skill_tests.TerminalContains(all=["gh", "pr"]),
        forbid=["git push"],
        llm_judge=gen_skill_tests.default_llm_judge(
            gen_skill_tests.EvalCase(
                id="pr-checks",
                prompt="Check PR",
                terminal_contains=gen_skill_tests.TerminalContains(all=["gh", "pr"]),
                forbid=["git push"],
            )
        ),
    )

    rows = gen_skill_tests._build_tests_yaml([case], "generated", "tests_poc")
    assert rows[0]["llm_judge"]["enabled"] is True
    assert rows[0]["expectations"][0]["pytest_path"] == (
        "tests_poc/pytests/generated/test_pr_checks.py"
    )


def test_parse_eval_cases_from_yaml_with_judge_override() -> None:
    raw = [
        {
            "id": "run-list",
            "prompt": "List runs",
            "asserts": [{"type": "terminal_contains", "all": ["gh", "run", "list"]}],
            "forbid": ["git push"],
            "llm_judge": {"min_score": 0.75, "rubric": "List workflow runs correctly."},
        }
    ]
    cases = gen_skill_tests._parse_eval_cases(raw, emit_judge=True)
    assert len(cases) == 1
    assert cases[0].llm_judge is not None
    assert cases[0].llm_judge.min_score == 0.75
    assert "List workflow runs" in cases[0].llm_judge.rubric


def test_main_generates_judge_blocks(tmp_path: Path) -> None:
    skill_dir = tmp_path / "github-skill"
    skill_dir.mkdir()
    (skill_dir / "SKILL.md").write_text("# skill\n", encoding="utf-8")

    cases_yaml = skill_dir / "eval-cases.yaml"
    cases_yaml.write_text(
        yaml.safe_dump(
            {
                "eval_cases": [
                    {
                        "id": "pr-checks",
                        "prompt": "Check PR #42",
                        "asserts": [
                            {
                                "type": "terminal_contains",
                                "all": ["gh", "pr", "checks", "42"],
                            }
                        ],
                        "forbid": ["git push"],
                    }
                ]
            }
        ),
        encoding="utf-8",
    )

    rc = gen_skill_tests.main(
        [
            "--skill-dir",
            str(skill_dir),
            "--cases-yaml",
            str(cases_yaml),
            "--overwrite",
        ]
    )
    assert rc == 0

    generated = yaml.safe_load((skill_dir / "tests_poc" / "tests.yaml").read_text())
    assert "llm_judge" in generated[0]
    assert generated[0]["llm_judge"]["enabled"] is True
