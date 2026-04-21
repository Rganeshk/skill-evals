#!/usr/bin/env bash
# run_all_evals.sh — Build images and run all test cases for a skill.
#
# Usage:
#   ./run_all_evals.sh <skill-dir>
#
# Example:
#   ./run_all_evals.sh skills/github-skill
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
    echo "Try:  python -m pip install pyyaml   or   python3 -m pip install pyyaml" >&2
    exit 1
fi

SKILL_DIR="${1:?Usage: $0 <skill-dir>}"
REPO_ROOT="$(cd "$(dirname "$0")" && pwd)"

# ── Build Docker images ─────────────────────────────────────────────
echo "=== Building base image ==="
docker build -t openhands-eval:latest -f "$REPO_ROOT/docker/Dockerfile.claude" "$REPO_ROOT/docker/"

echo ""
echo "=== Building skill image ==="
docker build -t openhands-eval-github:latest -f "$REPO_ROOT/$SKILL_DIR/Dockerfile" "$REPO_ROOT/"

# ── Parse test names from tests.yaml ────────────────────────────────
TESTS_YAML="$REPO_ROOT/$SKILL_DIR/tests/tests.yaml"
TEST_NAMES=$("$PYTHON_CMD" -c "
import yaml
with open('$TESTS_YAML') as f:
    tests = yaml.safe_load(f)
for t in tests:
    print(t['name'])
")

# ── Run each test ───────────────────────────────────────────────────
PASS=0
FAIL=0
TOTAL=0

for TEST_NAME in $TEST_NAMES; do
    TOTAL=$((TOTAL + 1))
    echo ""
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo "  Test $TOTAL: $TEST_NAME"
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

    if "$REPO_ROOT/run_eval.sh" "$SKILL_DIR" "$TEST_NAME"; then
        PASS=$((PASS + 1))
        echo "  ✓ PASSED"
    else
        FAIL=$((FAIL + 1))
        echo "  ✗ FAILED"
    fi
done

# ── Summary ─────────────────────────────────────────────────────────
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "  Results: $PASS/$TOTAL passed, $FAIL failed"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

[ "$FAIL" -eq 0 ] || exit 1
