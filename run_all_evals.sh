#!/usr/bin/env bash
# run_all_evals.sh — Build images and run all test cases for a skill.
#
# Usage:
#   ./run_all_evals.sh <skill-dir>
#
# Example:
#   ./run_all_evals.sh skills/github-skill
set -eu -o pipefail

REPO_ROOT="$(cd "$(dirname "$0")" && pwd)"
# shellcheck source=scripts/lib/common.sh
source "$REPO_ROOT/scripts/lib/common.sh"

require_python_with_yaml
require_docker

SKILL_DIR="${1:?Usage: $0 <skill-dir>}"
BASE_IMAGE="openhands-eval:latest"
SKILL_IMAGE="openhands-eval-github:latest"

# ── Build Docker images ─────────────────────────────────────────────
log_stage "Building base image ($BASE_IMAGE)"
docker build -t "$BASE_IMAGE" -f "$REPO_ROOT/docker/Dockerfile.openhands" "$REPO_ROOT/docker/"

log_stage "Building skill image ($SKILL_IMAGE)"
docker build -t "$SKILL_IMAGE" -f "$REPO_ROOT/$SKILL_DIR/Dockerfile" "$REPO_ROOT/"

# ── Parse test names from tests.yaml ────────────────────────────────
TESTS_YAML="$REPO_ROOT/$SKILL_DIR/tests/tests.yaml"
if [ ! -f "$TESTS_YAML" ]; then
    echo "ERROR: $TESTS_YAML not found" >&2
    exit 1
fi

log_stage "Loading test cases from tests.yaml"
TEST_NAMES=$("$PYTHON_CMD" -c "
import yaml
with open('$TESTS_YAML') as f:
    tests = yaml.safe_load(f)
if not tests:
    raise SystemExit('ERROR: tests.yaml is empty')
for t in tests:
    print(t['name'])
")

# ── Run each test ───────────────────────────────────────────────────
PASS=0
FAIL=0
TOTAL=0

for TEST_NAME in $TEST_NAMES; do
    TOTAL=$((TOTAL + 1))
    log_banner "Test $TOTAL: $TEST_NAME"

    if "$REPO_ROOT/run_eval.sh" "$SKILL_DIR" "$TEST_NAME"; then
        PASS=$((PASS + 1))
        echo "  ✓ PASSED"
    else
        FAIL=$((FAIL + 1))
        echo "  ✗ FAILED"
    fi
done

# ── Summary ─────────────────────────────────────────────────────────
log_banner "Results: $PASS/$TOTAL passed, $FAIL failed"

[ "$FAIL" -eq 0 ] || exit 1
