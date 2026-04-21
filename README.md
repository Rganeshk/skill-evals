# skill-evals

Dockerized evaluations for testing the **OpenHands Software Agent SDK** with skills from ClawdHub.

Inspired by [JiyangZhang/skilltest](https://github.com/JiyangZhang/skilltest), but uses the **OpenHands agent runtime** instead of Claude Code.

## How It Works

```
┌─────────────────────────────────────────────────────┐
│                  Docker Container                    │
│                                                      │
│  ┌──────────┐    ┌���─────────────┐    ┌───────────┐  │
│  │ SKILL.md │───>│ OpenHands    │───>│ events.json│  │
│  │ prompt   │    │ Agent (SDK)  │    │ stdout.txt │  │
│  └──────────┘    └──────────────┘    │ summary.txt│  │
│                        │              └───────────┘  │
│                   ┌────▼────┐                        │
│                   │ gh CLI  │                        │
│                   │ git     │                        │
│                   │ python  │                        │
│                   └─────────┘                        │
└─────────────────────────────────────────────────────┘
                         │
                    ┌────▼────┐
                    │ pytest  │  (grades events.json)
                    │ graders │
                    └─────────┘
```

1. The **SKILL.md** is injected into the agent's context (prepended to the prompt)
2. The **OpenHands agent** runs inside Docker with tools (terminal, file editor)
3. All agent events (terminal commands, file edits, messages) are captured to **events.json**
4. **Pytest graders** run **inside Docker** (same `openhands-eval` image family) by default, reading `events.json` from the mounted results dir. Set `GRADE_ON_HOST=1` to grade with host Python instead.

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
│           └── pytests/         # Event-based grading scripts
│               ├── conftest.py  # Fixtures: events, terminal_commands, etc.
│               ├── test_pr_ci_status.py
│               ├── test_list_runs.py
│               ├── test_failed_logs.py
│               ├── test_api_pr_details.py
│               └── test_json_issue_list.py
├── run_eval.sh                  # Run a single test case
├── run_all_evals.sh             # Run all test cases for a skill
├── .github/workflows/
│   └── run-evals.yml            # CI pipeline
└── pyproject.toml
```

## Quick Start

### Prerequisites

- Docker
- Python 3.11+ on the host (for `run_eval.sh` YAML + pytest) with `pyyaml` and `pytest`
- `LLM_API_KEY` env var (Anthropic API key)
- `GITHUB_TOKEN` or `GH_TOKEN` (the container passes both; `gh` reads `GH_TOKEN`)

### Run a single test

```bash
# Build images
docker build -t openhands-eval:latest -f docker/Dockerfile.openhands docker/
docker build -t openhands-eval-github:latest -f skills/github-skill/Dockerfile .

# Run one test
export LLM_API_KEY=your-anthropic-key
export GITHUB_TOKEN=your-github-token
./run_eval.sh skills/github-skill pr-ci-status
```

### Run all tests for a skill

```bash
export LLM_API_KEY=your-anthropic-key
export GITHUB_TOKEN=your-github-token
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
