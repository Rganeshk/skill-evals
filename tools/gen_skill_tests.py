#!/usr/bin/env python3
from __future__ import annotations

import argparse
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

try:
    import yaml
except ModuleNotFoundError as e:  # pragma: no cover
    raise SystemExit(
        "PyYAML is required. Install with: python -m pip install pyyaml"
    ) from e


@dataclass(frozen=True)
class TerminalContains:
    all: list[str]


@dataclass(frozen=True)
class EvalCase:
    id: str
    prompt: str
    terminal_contains: TerminalContains
    forbid: list[str]


FENCE_RE = re.compile(r"```(?P<lang>[a-zA-Z0-9_-]+)\n(?P<body>[\s\S]*?)\n```", re.M)


def _slug_to_py_filename(case_id: str) -> str:
    return f"test_{case_id.replace('-', '_')}.py"


def _safe_yaml_load(s: str) -> Any:
    try:
        return yaml.safe_load(s)
    except Exception as e:  # pragma: no cover
        raise ValueError(f"Failed to parse YAML: {e}") from e


def _extract_eval_cases_from_skill_md(skill_md: str) -> list[EvalCase]:
    """Extract eval cases from the first fenced ```yaml block containing eval_cases."""
    for m in FENCE_RE.finditer(skill_md):
        if m.group("lang").lower() != "yaml":
            continue
        data = _safe_yaml_load(m.group("body"))
        if not isinstance(data, dict) or "eval_cases" not in data:
            continue
        return _parse_eval_cases(data["eval_cases"])
    raise ValueError(
        "No eval cases found. Add a fenced ```yaml block containing top-level `eval_cases:` "
        "or pass --cases-yaml <path>."
    )


def _parse_eval_cases(raw: Any) -> list[EvalCase]:
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

        if not isinstance(case_id, str) or not case_id.strip():
            raise ValueError(f"eval_cases[{i}].id must be a non-empty string")
        if not isinstance(prompt, str) or not prompt.strip():
            raise ValueError(f"eval_cases[{i}].prompt must be a non-empty string")
        if not isinstance(forbid, list) or not all(isinstance(x, str) for x in forbid):
            raise ValueError(f"eval_cases[{i}].forbid must be a list[str] (or omitted)")
        if not isinstance(asserts, list):
            raise ValueError(f"eval_cases[{i}].asserts must be a list")

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

        cases.append(
            EvalCase(
                id=case_id.strip(),
                prompt=prompt.strip(),
                terminal_contains=TerminalContains(all=term_contains),
                forbid=[x.strip() for x in forbid if x.strip()],
            )
        )
    return cases


def _render_conftest() -> str:
    return '''"""Generated (POC) shared fixtures for skill grading tests.

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

    return f'''"""Generated (POC) grader for: {case.id}.

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


def _write_text(path: Path, content: str, overwrite: bool) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists() and not overwrite:
        raise FileExistsError(f"Refusing to overwrite existing file: {path}")
    path.write_text(content, encoding="utf-8")


def _build_tests_yaml(cases: list[EvalCase], pytests_pkg: str) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for c in cases:
        test_file = _slug_to_py_filename(c.id)
        out.append(
            {
                "name": c.id,
                "prompt": c.prompt,
                "expectations": [
                    {
                        "text": f"Agent executes a command containing tokens: {', '.join(c.terminal_contains.all)}",
                        "oracle": "pytest",
                        "pytest_path": f"tests/pytests/{pytests_pkg}/{test_file}",
                    }
                ],
            }
        )
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description="POC: generate tests.yaml + pytest graders from eval_cases YAML.")
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
    ap.add_argument("--pytests-pkg", type=str, default="generated", help="Subfolder name under tests/pytests/ (default: generated).")
    ap.add_argument("--overwrite", action="store_true", help="Overwrite existing generated files.")

    args = ap.parse_args()
    skill_dir: Path = args.skill_dir
    skill_md_path = skill_dir / "SKILL.md"
    if not skill_md_path.exists():
        raise SystemExit(f"SKILL.md not found at {skill_md_path}")

    out_dir: Path = args.out_dir or (skill_dir / "tests_poc")
    if out_dir.resolve() == (skill_dir / "tests").resolve():
        raise SystemExit(
            "Refusing to write into the existing tests/ directory for this POC. "
            "Use a separate --out-dir (default is tests_poc/)."
        )

    if args.cases_yaml:
        data = _safe_yaml_load(args.cases_yaml.read_text(encoding="utf-8"))
        if not isinstance(data, dict) or "eval_cases" not in data:
            raise SystemExit("--cases-yaml must be a mapping containing top-level eval_cases")
        cases = _parse_eval_cases(data["eval_cases"])
    else:
        cases = _extract_eval_cases_from_skill_md(skill_md_path.read_text(encoding="utf-8"))

    pytests_pkg = args.pytests_pkg.strip().strip("/").strip()
    if not pytests_pkg:
        raise SystemExit("--pytests-pkg must be non-empty")

    # Write outputs
    tests_yaml_path = out_dir / "tests.yaml"
    pytests_dir = out_dir / "pytests" / pytests_pkg
    conftest_path = pytests_dir / "conftest.py"

    _write_text(conftest_path, _render_conftest(), overwrite=args.overwrite)
    for c in cases:
        _write_text(pytests_dir / _slug_to_py_filename(c.id), _render_test_py(c), overwrite=args.overwrite)

    tests_yaml = _build_tests_yaml(cases, pytests_pkg=pytests_pkg)
    _write_text(tests_yaml_path, yaml.safe_dump(tests_yaml, sort_keys=False), overwrite=args.overwrite)

    print(f"Wrote: {tests_yaml_path}")
    print(f"Wrote: {pytests_dir}/ (conftest.py + {len(cases)} test files)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

