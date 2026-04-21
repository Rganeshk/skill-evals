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

pick_python_with_yaml() {
    for cmd in python3 python; do
        if command -v "$cmd" >/dev/null 2>&1 && "$cmd" -c "import yaml" 2>/dev/null; then
            echo "$cmd"
            return 0
        fi
    done
    return 1
}
if ! PYTHON_CMD=$(pick_python_with_yaml); then
    echo "ERROR: No python3/python on PATH can import yaml (PyYAML)." >&2
    echo "Install with: python -m pip install pyyaml" >&2
    exit 1
fi

SKILL_DIR="${1:?Usage: $0 <skill-dir> <test-name>}"
TEST_NAME="${2:?Usage: $0 <skill-dir> <test-name>}"

REPO_ROOT="$(cd "$(dirname "$0")" && pwd)"
SKILL_DIR="$REPO_ROOT/$SKILL_DIR"

TESTS_ROOT="${TESTS_ROOT:-$SKILL_DIR/tests_poc}"
RESULTS_BASE="${RESULTS_BASE:-$SKILL_DIR/eval-results-generated}"
RESULTS_DIR="$RESULTS_BASE/$TEST_NAME"

if [ ! -f "$SKILL_DIR/SKILL.md" ]; then
    echo "ERROR: $SKILL_DIR/SKILL.md not found" >&2
    exit 1
fi

TESTS_YAML="$TESTS_ROOT/tests.yaml"
if [ ! -f "$TESTS_YAML" ]; then
    echo "ERROR: $TESTS_YAML not found" >&2
    echo "Run generator first, e.g.:" >&2
    echo "  python tools/gen_skill_tests.py --skill-dir \"$SKILL_DIR\" --cases-yaml ... --out-dir \"$TESTS_ROOT\"" >&2
    exit 1
fi

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

echo "=== Running generated eval: $TEST_NAME ==="
echo "Skill:      $SKILL_DIR"
echo "Tests root: $TESTS_ROOT"
echo "Prompt:     ${PROMPT:0:100}..."
echo "Results:    $RESULTS_DIR"
echo ""

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

docker run --rm \
    -v "$RESULTS_DIR/prompt.txt:/workspace/prompt.txt:ro" \
    -v "$RESULTS_DIR/skill.md:/workspace/skill.md:ro" \
    -v "$RESULTS_DIR:/workspace/output" \
    -e "LLM_API_KEY=${LLM_API_KEY:?LLM_API_KEY is required}" \
    -e "LLM_MODEL=${LLM_MODEL:-openai/gpt-4o-mini}" \
    -e "LLM_BASE_URL=${LLM_BASE_URL:-https://api.openai.com/v1}" \
    -e "MAX_ITERATIONS=${MAX_ITERATIONS:-50}" \
    -e "GITHUB_TOKEN=${GH_AUTH_TOKEN}" \
    -e "GH_TOKEN=${GH_AUTH_TOKEN}" \
    openhands-eval-github:latest

echo ""
echo "=== Agent run complete. Grading... ==="
echo ""

_skill_root="${SKILL_DIR%/}"
PYTEST_REL="${PYTEST_GRADER#"${_skill_root}/"}"
GRADE_IMAGE="${GRADE_IMAGE:-openhands-eval:latest}"

if [ "${GRADE_ON_HOST:-}" = "1" ]; then
    echo "=== Grading (host pytest) ==="
    EVENTS_JSON="$RESULTS_DIR/events.json" \
    SUMMARY_TXT="$RESULTS_DIR/summary.txt" \
    STDOUT_TXT="$RESULTS_DIR/stdout.txt" \
        "$PYTHON_CMD" -m pytest "$PYTEST_GRADER" \
            -v --tb=short \
            -o "cache_dir=$RESULTS_DIR/.pytest_cache" \
            2>&1 | tee "$RESULTS_DIR/grading.txt"
else
    echo "=== Grading (Docker: $GRADE_IMAGE) ==="
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
        -c 'set -o pipefail && python -m pytest "'"$PYTEST_REL"'" -v --tb=short -o cache_dir=/out/.pytest_cache 2>&1 | tee /out/grading.txt'
fi

echo ""
echo "=== Grading complete ==="
echo "Results saved to: $RESULTS_DIR"

