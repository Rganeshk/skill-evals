#!/usr/bin/env bash
# run_all_evals_generated.sh — Run all generated (POC) test cases for a skill.
#
# Usage:
#   ./run_all_evals_generated.sh <skill-dir>
#
# Defaults:
#   - Reads tests from: <skill-dir>/tests_poc/tests.yaml
#   - Requires Docker images (run ./run_all_evals.sh once to build, or set SKIP_BUILD=1
#     after images exist)
set -eu -o pipefail

REPO_ROOT="$(cd "$(dirname "$0")" && pwd)"
# shellcheck source=scripts/lib/common.sh
source "$REPO_ROOT/scripts/lib/common.sh"

require_python_with_yaml
require_docker

SKILL_DIR="${1:?Usage: $0 <skill-dir>}"
SKILL_DIR_ABS="$REPO_ROOT/$SKILL_DIR"
BASE_IMAGE="openhands-eval:latest"
SKILL_IMAGE="openhands-eval-github:latest"

if [ "${SKIP_BUILD:-}" != "1" ]; then
    if ! docker image inspect "$BASE_IMAGE" >/dev/null 2>&1 \
        || ! docker image inspect "$SKILL_IMAGE" >/dev/null 2>&1; then
        log_stage "Docker images missing — building base + skill images"
        docker build -t "$BASE_IMAGE" -f "$REPO_ROOT/docker/Dockerfile.openhands" "$REPO_ROOT/docker/"
        docker build -t "$SKILL_IMAGE" -f "$REPO_ROOT/$SKILL_DIR/Dockerfile" "$REPO_ROOT/"
    fi
else
    require_docker_image "$BASE_IMAGE"
    require_docker_image "$SKILL_IMAGE"
fi

TESTS_ROOT="${TESTS_ROOT:-$SKILL_DIR_ABS/tests_poc}"
TESTS_YAML="$TESTS_ROOT/tests.yaml"
if [ ! -f "$TESTS_YAML" ]; then
    echo "ERROR: $TESTS_YAML not found" >&2
    echo "Generate tests first, e.g.:" >&2
    echo "  python tools/gen_skill_tests.py --skill-dir $SKILL_DIR --cases-yaml skills/github-skill/eval-cases.poc.yaml" >&2
    exit 1
fi

log_stage "Loading generated test cases from $TESTS_YAML"
TEST_NAMES=$("$PYTHON_CMD" -c "
import yaml
with open('$TESTS_YAML') as f:
    tests = yaml.safe_load(f)
if not tests:
    raise SystemExit('ERROR: tests.yaml is empty')
for t in tests:
    print(t['name'])
")

PASS=0
FAIL=0
TOTAL=0

for TEST_NAME in $TEST_NAMES; do
    TOTAL=$((TOTAL + 1))
    log_banner "Generated test $TOTAL: $TEST_NAME"

    if "$REPO_ROOT/run_eval_generated.sh" "$SKILL_DIR" "$TEST_NAME"; then
        PASS=$((PASS + 1))
        echo "  ✓ PASSED"
    else
        FAIL=$((FAIL + 1))
        echo "  ✗ FAILED"
    fi
done

log_banner "Results: $PASS/$TOTAL passed, $FAIL failed"

[ "$FAIL" -eq 0 ] || exit 1
