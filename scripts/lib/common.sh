#!/usr/bin/env bash
# Shared helpers for skill-evals orchestration scripts.
# Source from repo root: source "$(dirname "$0")/scripts/lib/common.sh"

# ── Strict mode (callers should also set -eu -o pipefail) ────────────

# Return the first python3/python on PATH that can import PyYAML.
pick_python_with_yaml() {
    local cmd
    for cmd in python3 python; do
        if command -v "$cmd" >/dev/null 2>&1 && "$cmd" -c "import yaml" 2>/dev/null; then
            echo "$cmd"
            return 0
        fi
    done
    return 1
}

require_python_with_yaml() {
    if ! PYTHON_CMD=$(pick_python_with_yaml); then
        echo "ERROR: No python3/python on PATH can import yaml (PyYAML)." >&2
        echo "Install with: python3 -m pip install pyyaml   OR   python -m pip install pyyaml" >&2
        exit 1
    fi
    export PYTHON_CMD
}

require_docker() {
    if ! command -v docker >/dev/null 2>&1; then
        echo "ERROR: docker is not installed or not on PATH." >&2
        exit 1
    fi
    if ! docker info >/dev/null 2>&1; then
        echo "ERROR: Docker daemon is not running. Start Docker and retry." >&2
        exit 1
    fi
}

require_docker_image() {
    local image="${1:?image name required}"
    if ! docker image inspect "$image" >/dev/null 2>&1; then
        echo "ERROR: Docker image '$image' not found." >&2
        echo "Build it first, e.g.:" >&2
        echo "  ./run_all_evals.sh <skill-dir>   # builds base + skill images" >&2
        exit 1
    fi
}

log_stage() {
    echo ""
    echo "=== $* ==="
}

log_banner() {
    echo ""
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo "  $*"
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
}
