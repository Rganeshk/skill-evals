#!/usr/bin/env bash
# run_eval.sh — Build images, run a single test case, and grade it.
#
# Usage:
#   ./run_eval.sh <skill-dir> <test-name>
#
# Example:
#   ./run_eval.sh skills/github-skill pr-checks
#
# Prerequisites:
#   - Docker installed and running
#   - LLM_API_KEY set (e.g. ANTHROPIC_API_KEY)
#   - GITHUB_TOKEN or GH_TOKEN set (gh authenticates via GH_TOKEN inside the container)
#
# Environment variables:
#   LLM_MODEL       — model name (default: openai/gpt-4o-mini; must match LLM_BASE_URL provider)
#   LLM_API_KEY     — API key for the LLM provider (required)
#   LLM_BASE_URL    — API base (default: https://api.openai.com/v1). Use https://api.anthropic.com for Claude.
#   MAX_ITERATIONS  — max agent steps (default: 50)
#   GITHUB_TOKEN or GH_TOKEN — passed into the container as both names (gh reads GH_TOKEN)
#   GRADE_IMAGE     — image for pytest grading (default: openhands-eval:latest; needs pytest in image)
#   GRADE_ON_HOST=1 — set to run pytest on the host instead of Docker (debug only)
#   SKIP_LLM_JUDGE=1  — skip LLM-as-a-Judge phase
#   JUDGE_MODEL       — judge model (default: same as LLM_MODEL)
#   JUDGE_API_KEY     — judge API key (default: LLM_API_KEY)
set -eu -o pipefail

REPO_ROOT="$(cd "$(dirname "$0")" && pwd)"
# shellcheck source=scripts/lib/common.sh
source "$REPO_ROOT/scripts/lib/common.sh"

require_python_with_yaml
require_docker

SKILL_DIR="${1:?Usage: $0 <skill-dir> <test-name>}"
TEST_NAME="${2:?Usage: $0 <skill-dir> <test-name>}"

AGENT_IMAGE="${AGENT_IMAGE:-openhands-eval-github:latest}"
GRADE_IMAGE="${GRADE_IMAGE:-openhands-eval:latest}"

# ── Resolve paths ───────────────────────────────────────────────────
SKILL_DIR="$REPO_ROOT/$SKILL_DIR"
RESULTS_DIR="$SKILL_DIR/eval-results/$TEST_NAME"

if [ ! -f "$SKILL_DIR/SKILL.md" ]; then
    echo "ERROR: $SKILL_DIR/SKILL.md not found" >&2
    exit 1
fi

require_docker_image "$AGENT_IMAGE"
require_docker_image "$GRADE_IMAGE"

# ── Parse the test prompt from tests.yaml ───────────────────────────
TESTS_YAML="$SKILL_DIR/tests/tests.yaml"
if [ ! -f "$TESTS_YAML" ]; then
    echo "ERROR: $TESTS_YAML not found" >&2
    exit 1
fi

log_stage "Parsing prompt for test: $TEST_NAME"
PROMPT=$("$PYTHON_CMD" -c "
import yaml, sys
with open('$TESTS_YAML') as f:
    tests = yaml.safe_load(f)
for t in tests:
    if t['name'] == '$TEST_NAME':
        print(t['prompt'].strip())
        sys.exit(0)
print('ERROR: Test not found: $TEST_NAME', file=sys.stderr)
sys.exit(1)
")

# ── Prepare workspace ──────────────────────────────────────────────
mkdir -p "$RESULTS_DIR"
echo "$PROMPT" > "$RESULTS_DIR/prompt.txt"
cp "$SKILL_DIR/SKILL.md" "$RESULTS_DIR/skill.md"

log_stage "Running eval: $TEST_NAME"
echo "Skill:   $SKILL_DIR"
echo "Prompt:  ${PROMPT:0:100}..."
echo "Results: $RESULTS_DIR"

if [ -z "${LLM_API_KEY:-}" ]; then
    echo "ERROR: LLM_API_KEY is required" >&2
    exit 1
fi

GH_AUTH_TOKEN="${GITHUB_TOKEN:-${GH_TOKEN:-}}"
if [ -z "$GH_AUTH_TOKEN" ]; then
    echo "WARNING: GITHUB_TOKEN (or GH_TOKEN) is unset — gh inside Docker will not authenticate." >&2
fi

# Pytest grader module: tests/pytests/<package>/test_<slug>.py (slug = test name with '-' → '_')
TEST_SLUG="${TEST_NAME//-/_}"
PYTEST_GRADER=""
for grader_pkg in "$SKILL_DIR/tests/pytests"/*/; do
    [ -d "$grader_pkg" ] || continue
    candidate="${grader_pkg}test_${TEST_SLUG}.py"
    if [ -f "$candidate" ]; then
        PYTEST_GRADER="$candidate"
        break
    fi
done
if [ -z "$PYTEST_GRADER" ]; then
    echo "ERROR: No grader found: tests/pytests/*/test_${TEST_SLUG}.py under $SKILL_DIR" >&2
    exit 1
fi

# ── Run the agent in Docker ────────────────────────────────────────
log_stage "Agent execution (Docker: $AGENT_IMAGE)"
docker run --rm \
    -v "$RESULTS_DIR/prompt.txt:/workspace/prompt.txt:ro" \
    -v "$RESULTS_DIR/skill.md:/workspace/skill.md:ro" \
    -v "$RESULTS_DIR:/workspace/output" \
    -e "LLM_API_KEY=${LLM_API_KEY}" \
    -e "LLM_MODEL=${LLM_MODEL:-openai/gpt-4o-mini}" \
    -e "LLM_BASE_URL=${LLM_BASE_URL:-https://api.openai.com/v1}" \
    -e "MAX_ITERATIONS=${MAX_ITERATIONS:-50}" \
    -e "GITHUB_TOKEN=${GH_AUTH_TOKEN}" \
    -e "GH_TOKEN=${GH_AUTH_TOKEN}" \
    "$AGENT_IMAGE"

if [ ! -f "$RESULTS_DIR/events.json" ]; then
    echo "ERROR: Agent did not produce events.json at $RESULTS_DIR/events.json" >&2
    exit 1
fi

log_stage "Agent run complete — grading with pytest"

# ── Grade with pytest (Docker by default; matches agent environment) ─
_skill_root="${SKILL_DIR%/}"
PYTEST_REL="${PYTEST_GRADER#"${_skill_root}/"}"
GRADE_EXIT=0

if [ "${GRADE_ON_HOST:-}" = "1" ]; then
    echo "Grading mode: host pytest"
    EVENTS_JSON="$RESULTS_DIR/events.json" \
    SUMMARY_TXT="$RESULTS_DIR/summary.txt" \
    STDOUT_TXT="$RESULTS_DIR/stdout.txt" \
        "$PYTHON_CMD" -m pytest "$PYTEST_GRADER" \
            -v --tb=short \
            -o "cache_dir=$RESULTS_DIR/.pytest_cache" \
            2>&1 | tee "$RESULTS_DIR/grading.txt" || GRADE_EXIT=$?
else
    echo "Grading mode: Docker ($GRADE_IMAGE)"
    # cache_dir on /out — /skill is read-only (avoids PytestCacheWarning)
    docker run --rm \
        --entrypoint bash \
        -e PYTHONDONTWRITEBYTECODE=1 \
        -e "EVENTS_JSON=/out/events.json" \
        -e "SUMMARY_TXT=/out/summary.txt" \
        -e "STDOUT_TXT=/out/stdout.txt" \
        -v "$SKILL_DIR:/skill:ro" \
        -v "$RESULTS_DIR:/out" \
        -w /skill \
        "$GRADE_IMAGE" \
        -c 'set -o pipefail && python -m pytest "'"$PYTEST_REL"'" -v --tb=short -o cache_dir=/out/.pytest_cache 2>&1 | tee /out/grading.txt' \
        || GRADE_EXIT=$?
fi

log_stage "Grading complete"
echo "Results saved to: $RESULTS_DIR"

if [ "$GRADE_EXIT" -ne 0 ]; then
    echo "ERROR: Pytest grading failed (exit code $GRADE_EXIT)" >&2
    exit "$GRADE_EXIT"
fi

# ── LLM-as-a-Judge (optional; configured per test in tests.yaml) ─────
JUDGE_EXIT=0
if [ "${SKIP_LLM_JUDGE:-}" != "1" ]; then
    log_stage "LLM-as-a-Judge validation"
    if "$PYTHON_CMD" "$REPO_ROOT/tools/llm_judge.py" \
        --results-dir "$RESULTS_DIR" \
        --tests-yaml "$TESTS_YAML" \
        --test-name "$TEST_NAME" \
        2>&1 | tee "$RESULTS_DIR/judge.txt"; then
        :
    else
        JUDGE_EXIT=$?
    fi
fi

if [ "$JUDGE_EXIT" -ne 0 ]; then
    echo "ERROR: LLM judge validation failed (exit code $JUDGE_EXIT)" >&2
    exit "$JUDGE_EXIT"
fi
