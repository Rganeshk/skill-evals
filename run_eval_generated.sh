#!/usr/bin/env bash
# run_eval_generated.sh — Run a single generated (POC) test case.
#
# This runner is intentionally separate from run_eval.sh to avoid affecting
# existing test cases under skills/*/tests/.
#
# Usage:
#   ./run_eval_generated.sh <skill-dir> <test-name>
#
# Defaults:
#   - Reads tests from: <skill-dir>/tests_poc/tests.yaml
#   - Grades with:      <skill-dir>/tests_poc/pytests/*/test_<slug>.py
#   - Writes results:   <skill-dir>/eval-results-generated/<test-name>/
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

SKILL_DIR="$REPO_ROOT/$SKILL_DIR"
TESTS_ROOT="${TESTS_ROOT:-$SKILL_DIR/tests_poc}"
RESULTS_BASE="${RESULTS_BASE:-$SKILL_DIR/eval-results-generated}"
RESULTS_DIR="$RESULTS_BASE/$TEST_NAME"

if [ ! -f "$SKILL_DIR/SKILL.md" ]; then
    echo "ERROR: $SKILL_DIR/SKILL.md not found" >&2
    exit 1
fi

require_docker_image "$AGENT_IMAGE"
require_docker_image "$GRADE_IMAGE"

TESTS_YAML="$TESTS_ROOT/tests.yaml"
if [ ! -f "$TESTS_YAML" ]; then
    echo "ERROR: $TESTS_YAML not found" >&2
    echo "Run generator first, e.g.:" >&2
    echo "  python tools/gen_skill_tests.py --skill-dir \"$SKILL_DIR\" --cases-yaml ... --out-dir \"$TESTS_ROOT\"" >&2
    exit 1
fi

log_stage "Parsing prompt for generated test: $TEST_NAME"
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

mkdir -p "$RESULTS_DIR"
echo "$PROMPT" > "$RESULTS_DIR/prompt.txt"
cp "$SKILL_DIR/SKILL.md" "$RESULTS_DIR/skill.md"

log_stage "Running generated eval: $TEST_NAME"
echo "Skill:      $SKILL_DIR"
echo "Tests root: $TESTS_ROOT"
echo "Prompt:     ${PROMPT:0:100}..."
echo "Results:    $RESULTS_DIR"

if [ -z "${LLM_API_KEY:-}" ]; then
    echo "ERROR: LLM_API_KEY is required" >&2
    exit 1
fi

GH_AUTH_TOKEN="${GITHUB_TOKEN:-${GH_TOKEN:-}}"
if [ -z "$GH_AUTH_TOKEN" ]; then
    echo "WARNING: GITHUB_TOKEN (or GH_TOKEN) is unset — gh inside Docker will not authenticate." >&2
fi

TEST_SLUG="${TEST_NAME//-/_}"
PYTEST_GRADER=""
for grader_pkg in "$TESTS_ROOT/pytests"/*/; do
    [ -d "$grader_pkg" ] || continue
    candidate="${grader_pkg}test_${TEST_SLUG}.py"
    if [ -f "$candidate" ]; then
        PYTEST_GRADER="$candidate"
        break
    fi
done
if [ -z "$PYTEST_GRADER" ]; then
    echo "ERROR: No grader found: $TESTS_ROOT/pytests/*/test_${TEST_SLUG}.py" >&2
    exit 1
fi

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
