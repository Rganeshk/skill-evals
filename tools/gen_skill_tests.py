#!/usr/bin/env python3
"""Generate tests.yaml, pytest graders, and LLM judge config from eval_cases YAML.

Reads declarative eval case definitions (from a sidecar YAML file or a fenced block
in SKILL.md) and emits:

- ``tests_poc/tests.yaml`` — prompts, pytest expectations, auto-generated ``llm_judge``
- ``tests_poc/pytests/<pkg>/test_*.py`` — token-based terminal command graders
- ``tests_poc/pytests/<pkg>/conftest.py`` — shared fixtures for event-log grading

Each eval case requires ``terminal_contains`` asserts. When ``llm_judge`` is omitted,
a default rubric and criteria are derived from the prompt, required tokens, and
forbidden operations. Cases may override rubric/criteria via an optional ``llm_judge``
block in the source YAML.
"""
from __future__ import annotations

import argparse
import re
import textwrap
from dataclasses import dataclass
from pathlib import Path
from typing import Any

try:
    import yaml
except ModuleNotFoundError as e:  # pragma: no cover
    raise SystemExit(
        "PyYAML is required. Install with: python -m pip install pyyaml"
    ) from e


DEFAULT_MIN_SCORE = 0.7


@dataclass(frozen=True)
class TerminalContains:
    all: list[str]


@dataclass(frozen=True)
class JudgeCriterion:
    name: str
    description: str


@dataclass(frozen=True)
class LlmJudgeConfig:
    enabled: bool
    min_score: float
    rubric: str
    criteria: list[JudgeCriterion]


@dataclass(frozen=True)
class EvalCase:
    id: str
    prompt: str
    terminal_contains: TerminalContains
    forbid: list[str]
    llm_judge: LlmJudgeConfig | None = None


FENCE_RE = re.compile(r"```(?P<lang>[a-zA-Z0-9_-]+)\n(?P<body>[\s\S]*?)\n```", re.M)


def _slug_to_py_filename(case_id: str) -> str:
    return f"test_{case_id.replace('-', '_')}.py"


def _safe_yaml_load(s: str) -> Any:
    try:
        return yaml.safe_load(s)
    except Exception as e:  # pragma: no cover
        raise ValueError(f"Failed to parse YAML: {e}") from e


def _parse_judge_criteria(raw: Any, index: int) -> list[JudgeCriterion]:
    if raw is None:
        return []
    if not isinstance(raw, list):
        raise ValueError(f"eval_cases[{index}].llm_judge.criteria must be a list")
    out: list[JudgeCriterion] = []
    for j, item in enumerate(raw):
        if not isinstance(item, dict):
            raise ValueError(f"eval_cases[{index}].llm_judge.criteria[{j}] must be a mapping")
        name = item.get("name")
        desc = item.get("description", "")
        if not isinstance(name, str) or not name.strip():
            raise ValueError(
                f"eval_cases[{index}].llm_judge.criteria[{j}].name must be a non-empty string"
            )
        out.append(JudgeCriterion(name=name.strip(), description=str(desc).strip()))
    return out


def default_llm_judge(case: EvalCase) -> LlmJudgeConfig:
    """Build a default LLM judge rubric from prompt, tokens, and forbid list."""
    tokens = case.terminal_contains.all
    token_list = ", ".join(tokens)
    forbid = case.forbid

    rubric = textwrap.dedent(
        f"""\
        The agent was given this task:
        {case.prompt.strip()}

        A passing run demonstrates task understanding and executes a terminal command
        containing all required tokens: {token_list}.
        """
    ).strip()

    if forbid:
        rubric += (
            "\n\nThe agent must NOT perform forbidden operations: "
            + ", ".join(forbid)
            + "."
        )

    criteria = [
        JudgeCriterion(
            name="task_understanding",
            description="Agent understood and attempted the user request",
        ),
        JudgeCriterion(
            name="tool_use_quality",
            description=f"Agent executed a command containing required tokens: {token_list}",
        ),
    ]
    if forbid:
        criteria.append(
            JudgeCriterion(
                name="safety",
                description="No forbidden operations: " + ", ".join(forbid),
            )
        )

    return LlmJudgeConfig(
        enabled=True,
        min_score=DEFAULT_MIN_SCORE,
        rubric=rubric,
        criteria=criteria,
    )


def resolve_llm_judge(
    case: EvalCase,
    override: dict[str, Any] | None,
    *,
    emit_judge: bool,
    index: int,
) -> LlmJudgeConfig | None:
    if not emit_judge:
        return None

    if override is not None and override.get("enabled") is False:
        return None

    base = default_llm_judge(case)

    if override is None:
        return base

    min_score = float(override.get("min_score", base.min_score))
    if not 0.0 <= min_score <= 1.0:
        raise ValueError(f"eval_cases[{index}].llm_judge.min_score must be between 0 and 1")

    rubric = override.get("rubric", base.rubric)
    if not isinstance(rubric, str) or not rubric.strip():
        raise ValueError(f"eval_cases[{index}].llm_judge.rubric must be a non-empty string")

    criteria_override = _parse_judge_criteria(override.get("criteria"), index)
    criteria = criteria_override if criteria_override else base.criteria

    return LlmJudgeConfig(
        enabled=True,
        min_score=min_score,
        rubric=rubric.strip(),
        criteria=criteria,
    )


def _parse_eval_cases(raw: Any, *, emit_judge: bool = True) -> list[EvalCase]:
    if not isinstance(raw, list):
        raise ValueError("eval_cases must be a list")

    cases: list[EvalCase] = []
    for i, item in enumerate(raw):
        if not isinstance(item, dict):
            raise ValueError(f"eval_cases[{i}] must be a mapping")

        case_id = item.get("id")
        prompt = item.get("prompt")
        asserts = item.get("asserts")
        forbid = item.get("forbid") or []
        judge_raw = item.get("llm_judge")

        if not isinstance(case_id, str) or not case_id.strip():
            raise ValueError(f"eval_cases[{i}].id must be a non-empty string")
        if not isinstance(prompt, str) or not prompt.strip():
            raise ValueError(f"eval_cases[{i}].prompt must be a non-empty string")
        if not isinstance(forbid, list) or not all(isinstance(x, str) for x in forbid):
            raise ValueError(f"eval_cases[{i}].forbid must be a list[str] (or omitted)")
        if not isinstance(asserts, list):
            raise ValueError(f"eval_cases[{i}].asserts must be a list")
        if judge_raw is not None and not isinstance(judge_raw, dict):
            raise ValueError(f"eval_cases[{i}].llm_judge must be a mapping")

        term_contains: list[str] | None = None
        for a in asserts:
            if not isinstance(a, dict):
                continue
            if a.get("type") == "terminal_contains":
                all_tokens = a.get("all")
                if not isinstance(all_tokens, list) or not all(
                    isinstance(x, str) for x in all_tokens
                ):
                    raise ValueError(
                        f"eval_cases[{i}].asserts terminal_contains.all must be list[str]"
                    )
                term_contains = all_tokens
                break

        if not term_contains:
            raise ValueError(
                f"eval_cases[{i}] must include an asserts entry like "
                "{type: terminal_contains, all: [...]}"
            )

        stub = EvalCase(
            id=case_id.strip(),
            prompt=prompt.strip(),
            terminal_contains=TerminalContains(all=term_contains),
            forbid=[x.strip() for x in forbid if x.strip()],
        )
        llm_judge = resolve_llm_judge(stub, judge_raw, emit_judge=emit_judge, index=i)

        cases.append(
            EvalCase(
                id=stub.id,
                prompt=stub.prompt,
                terminal_contains=stub.terminal_contains,
                forbid=stub.forbid,
                llm_judge=llm_judge,
            )
        )
    return cases


def _extract_eval_cases_from_skill_md(skill_md: str, *, emit_judge: bool = True) -> list[EvalCase]:
    """Extract eval cases from the first fenced ```yaml block containing eval_cases."""
    for m in FENCE_RE.finditer(skill_md):
        if m.group("lang").lower() != "yaml":
            continue
        data = _safe_yaml_load(m.group("body"))
        if not isinstance(data, dict) or "eval_cases" not in data:
            continue
        return _parse_eval_cases(data["eval_cases"], emit_judge=emit_judge)
    raise ValueError(
        "No eval cases found. Add a fenced ```yaml block containing top-level `eval_cases:` "
        "or pass --cases-yaml <path>."
    )


def _render_conftest() -> str:
    return '''"""Generated shared fixtures for skill grading tests.

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
'''


def _render_test_py(case: EvalCase) -> str:
    tokens = case.terminal_contains.all
    forbid = case.forbid
    token_checks = " and ".join([f"{t!r} in c" for t in tokens]) or "False"
    forbid_tuple = "(" + ", ".join([repr(x) for x in forbid]) + ("," if len(forbid) == 1 else "") + ")"

    return f'''"""Generated grader for: {case.id}.

Asserts the agent executed a terminal command containing required tokens.
"""


def test_terminal_contains_required_tokens(terminal_commands: list[str]):
    matching = [c for c in terminal_commands if {token_checks}]
    assert matching, (
        "Expected a terminal command containing all required tokens.\\n"
        f"Required tokens: {tokens!r}\\n"
        f"Commands executed: {{terminal_commands}}"
    )


def test_no_forbidden_ops(terminal_commands: list[str]):
    forbidden = {forbid_tuple}
    bad = [c for c in terminal_commands if any(f in c for f in forbidden)]
    assert not bad, f"Forbidden operations detected: {{bad}}"
'''


def _llm_judge_to_yaml_dict(config: LlmJudgeConfig) -> dict[str, Any]:
    return {
        "enabled": config.enabled,
        "min_score": config.min_score,
        "rubric": config.rubric,
        "criteria": [
            {"name": c.name, "description": c.description} for c in config.criteria
        ],
    }


def _write_text(path: Path, content: str, overwrite: bool) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists() and not overwrite:
        raise FileExistsError(f"Refusing to overwrite existing file: {path}")
    path.write_text(content, encoding="utf-8")


def _tests_yaml_prefix(out_dir: Path, skill_dir: Path) -> str:
    rel = out_dir.resolve().relative_to(skill_dir.resolve())
    return rel.as_posix()


def _build_tests_yaml(
    cases: list[EvalCase],
    pytests_pkg: str,
    tests_prefix: str,
) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for c in cases:
        test_file = _slug_to_py_filename(c.id)
        entry: dict[str, Any] = {
            "name": c.id,
            "prompt": c.prompt,
            "expectations": [
                {
                    "text": (
                        "Agent executes a command containing tokens: "
                        + ", ".join(c.terminal_contains.all)
                    ),
                    "oracle": "pytest",
                    "pytest_path": f"{tests_prefix}/pytests/{pytests_pkg}/{test_file}",
                }
            ],
        }
        if c.llm_judge is not None:
            entry["llm_judge"] = _llm_judge_to_yaml_dict(c.llm_judge)
        out.append(entry)
    return out


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        description="Generate tests.yaml, pytest graders, and LLM judge config from eval_cases YAML."
    )
    ap.add_argument("--skill-dir", type=Path, required=True, help="Path to skill directory (contains SKILL.md).")
    ap.add_argument(
        "--out-dir",
        type=Path,
        default=None,
        help="Output directory. Default: <skill-dir>/tests_poc (does not touch existing tests/).",
    )
    ap.add_argument(
        "--cases-yaml",
        type=Path,
        default=None,
        help="Optional sidecar YAML containing top-level eval_cases.",
    )
    ap.add_argument(
        "--pytests-pkg",
        type=str,
        default="generated",
        help="Subfolder name under pytests/ (default: generated).",
    )
    ap.add_argument("--overwrite", action="store_true", help="Overwrite existing generated files.")
    ap.add_argument(
        "--no-llm-judge",
        action="store_true",
        help="Do not emit llm_judge blocks in generated tests.yaml.",
    )

    args = ap.parse_args(argv)
    skill_dir: Path = args.skill_dir
    skill_md_path = skill_dir / "SKILL.md"
    if not skill_md_path.exists():
        raise SystemExit(f"SKILL.md not found at {skill_md_path}")

    out_dir: Path = args.out_dir or (skill_dir / "tests_poc")
    if out_dir.resolve() == (skill_dir / "tests").resolve():
        raise SystemExit(
            "Refusing to write into the existing tests/ directory. "
            "Use a separate --out-dir (default is tests_poc/)."
        )

    emit_judge = not args.no_llm_judge

    if args.cases_yaml:
        data = _safe_yaml_load(args.cases_yaml.read_text(encoding="utf-8"))
        if not isinstance(data, dict) or "eval_cases" not in data:
            raise SystemExit("--cases-yaml must be a mapping containing top-level eval_cases")
        cases = _parse_eval_cases(data["eval_cases"], emit_judge=emit_judge)
    else:
        cases = _extract_eval_cases_from_skill_md(
            skill_md_path.read_text(encoding="utf-8"),
            emit_judge=emit_judge,
        )

    pytests_pkg = args.pytests_pkg.strip().strip("/").strip()
    if not pytests_pkg:
        raise SystemExit("--pytests-pkg must be non-empty")

    tests_prefix = _tests_yaml_prefix(out_dir, skill_dir)

    tests_yaml_path = out_dir / "tests.yaml"
    pytests_dir = out_dir / "pytests" / pytests_pkg
    conftest_path = pytests_dir / "conftest.py"

    _write_text(conftest_path, _render_conftest(), overwrite=args.overwrite)
    for c in cases:
        _write_text(pytests_dir / _slug_to_py_filename(c.id), _render_test_py(c), overwrite=args.overwrite)

    tests_yaml = _build_tests_yaml(cases, pytests_pkg=pytests_pkg, tests_prefix=tests_prefix)
    _write_text(tests_yaml_path, yaml.safe_dump(tests_yaml, sort_keys=False), overwrite=args.overwrite)

    judge_count = sum(1 for c in cases if c.llm_judge is not None)
    print(f"Wrote: {tests_yaml_path}")
    print(f"Wrote: {pytests_dir}/ (conftest.py + {len(cases)} test files)")
    if emit_judge:
        print(f"LLM judge blocks: {judge_count}/{len(cases)} test cases")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
