#!/usr/bin/env bash
# run_all_evals_generated.sh — Run all generated (POC) test cases for a skill.
#
# Usage:
#   ./run_all_evals_generated.sh <skill-dir>
#
# Defaults:
#   - Reads tests from: <skill-dir>/tests_poc/tests.yaml
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
SKILL_DIR_ABS="$REPO_ROOT/$SKILL_DIR"

TESTS_ROOT="${TESTS_ROOT:-$SKILL_DIR_ABS/tests_poc}"
TESTS_YAML="$TESTS_ROOT/tests.yaml"
if [ ! -f "$TESTS_YAML" ]; then
    echo "ERROR: $TESTS_YAML not found" >&2
    exit 1
fi

TEST_NAMES=$("$PYTHON_CMD" -c "
import yaml
with open('$TESTS_YAML') as f:
    tests = yaml.safe_load(f)
for t in tests:
    print(t['name'])
")

PASS=0
FAIL=0
TOTAL=0

for TEST_NAME in $TEST_NAMES; do
    TOTAL=$((TOTAL + 1))
    echo ""
    echo \"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\"
    echo \"  Generated test $TOTAL: $TEST_NAME\"
    echo \"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\"

    if "$REPO_ROOT/run_eval_generated.sh" "$SKILL_DIR" "$TEST_NAME"; then
        PASS=$((PASS + 1))
        echo "  ✓ PASSED"
    else
        FAIL=$((FAIL + 1))
        echo "  ✗ FAILED"
    fi
done

echo ""
echo \"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\"
echo \"  Results: $PASS/$TOTAL passed, $FAIL failed\"
echo \"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\"

[ "$FAIL" -eq 0 ] || exit 1

