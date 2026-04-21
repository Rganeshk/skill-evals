# skill-evals

Dockerized evaluations for testing the **OpenHands Software Agent SDK** with skills from ClawdHub.

Inspired by [JiyangZhang/skilltest](https://github.com/JiyangZhang/skilltest), but uses the **OpenHands agent runtime** instead of Claude Code.

## How It Works

1. The **SKILL.md** is injected into the agent's context (prepended to the prompt)
2. The **OpenHands agent** runs inside Docker with tools (terminal, file editor)
3. All agent events (terminal commands, file edits, messages) are captured to **events.json**
4. **Pytest graders** run **inside Docker** (same `openhands-eval` image family) by default, reading `events.json` from the mounted results dir. Set `GRADE_ON_HOST=1` to grade with host Python instead.

## Requirements

- **Docker** — Docker Desktop (or another engine) installed and running.
- **Host Python 3.11+** with **PyYAML** — used by `run_eval.sh` and `run_all_evals.sh` to read `tests/tests.yaml`. Install with `python -m pip install pyyaml` or `python3 -m pip install pyyaml` (use the same interpreter you run the scripts with).
- **Host pytest** — only needed if you set `GRADE_ON_HOST=1`. Default grading runs in Docker and does not require pytest on the host.
- **`LLM_API_KEY`** — **OpenAI** API key (`sk-...`) for the agent in the container (via LiteLLM). Optional: `LLM_BASE_URL` (default in scripts is `https://api.openai.com/v1`) and `LLM_MODEL` (e.g. `openai/gpt-4o-mini`); model and base URL must be the same provider.
- **`GITHUB_TOKEN` or `GH_TOKEN`** — GitHub personal access token passed into the container; `gh` reads **`GH_TOKEN`**. Needs scopes appropriate for the skill (e.g. repo read for private repos).
- **Network** — pulls Docker images and model API calls during evals.

To use **Anthropic** instead, set `LLM_BASE_URL=https://api.anthropic.com` and a Claude model name (e.g. `claude-sonnet-4-20250514`), and use an Anthropic API key in `LLM_API_KEY`.

## Structure

```
skill-evals/
├── docker/
│   ├── Dockerfile.openhands     # Base image: Python 3.12 + OpenHands SDK
│   ├── entrypoint.sh            # Launches run_agent.py, captures output
│   └── run_agent.py             # OpenHands agent runner + event serializer
├── skills/
│   └── github-skill/            # GitHub gh CLI skill eval
│       ├── SKILL.md             # Skill definition (steipete/github)
│       ├── Dockerfile           # Extends base with gh CLI
│       └── tests/
│           ├── tests.yaml       # Test case definitions
│           └── pytests/
│               └── github/      # Event-based grading (fixtures + tests)
│                   ├── conftest.py
│                   ├── test_pr_checks.py
│                   ├── test_run_list.py
│                   ├── test_run_view_failed.py
│                   ├── test_api_query.py
│                   └── test_issue_list_json.py
├── run_eval.sh                  # Run a single test case
├── run_all_evals.sh             # Run all test cases for a skill
├── .github/workflows/
│   └── run-evals.yml            # CI pipeline
└── pyproject.toml
```

## Quick Start

Meet the **[Requirements](#requirements)** first, then:

### Run a single test

```bash
# Build images
docker build -t openhands-eval:latest -f docker/Dockerfile.openhands docker/
docker build -t openhands-eval-github:latest -f skills/github-skill/Dockerfile .

# Run one test (OpenAI)
export LLM_API_KEY="sk-..."                    # OpenAI API key
export LLM_BASE_URL="https://api.openai.com/v1"  # optional; this is the default in run_eval.sh
export LLM_MODEL="openai/gpt-4o-mini"          # optional; must match OpenAI + base URL
export GITHUB_TOKEN="ghp_..."                  # or GH_TOKEN — for gh inside Docker

./run_eval.sh skills/github-skill pr-checks
```

### Run all tests for a skill

```bash
export LLM_API_KEY="sk-..."
export GITHUB_TOKEN="ghp_..."
./run_all_evals.sh skills/github-skill
```

### Results

After each run, results are saved to `skills/<skill>/eval-results/<test-name>/`:
- `events.json` — full OpenHands event log
- `summary.txt` — human-readable conversation
- `stdout.txt` — raw agent output
- `grading.txt` — pytest results

## Adding New Skills

1. Create `skills/<skill-name>/`
2. Add `SKILL.md` (from ClawdHub or custom)
3. Add `Dockerfile` if the skill needs extra tools installed
4. Create `tests/tests.yaml` with test cases
5. Write pytest graders in `tests/pytests/`

## Skills Under Evaluation

| Skill | Source | Tests | What it tests |
|-------|--------|-------|---------------|
| GitHub (`gh` CLI) | [steipete/github](https://clawhub.ai/steipete/github) | 5 | PR checks, run listing, failed logs, API queries, JSON output |
