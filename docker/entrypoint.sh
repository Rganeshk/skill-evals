#!/usr/bin/env bash
# entrypoint.sh — Launch OpenHands agent inside Docker, capture events + output.
#
# Volume layout (managed by the test runner):
#   /workspace/prompt.txt           — task prompt
#   /workspace/skill.md             — skill definition (injected into agent context)
#   /workspace/input/               — seed files the agent operates on
#   /workspace/output/              — results written here
#   /workspace/output/events.json   — full event log for pytest grading
#   /workspace/output/stdout.txt    — agent stdout capture
#   /workspace/output/summary.txt   — conversation summary
set -eu -o pipefail

mkdir -p /workspace/output/artifacts

PROMPT_FILE="/workspace/prompt.txt"
if [ ! -f "$PROMPT_FILE" ]; then
    echo "ERROR: $PROMPT_FILE not found" >&2
    exit 1
fi

# ── Run the OpenHands agent via Python ──────────────────────────────
python3 /usr/local/bin/run_agent.py 2>&1 | tee /workspace/output/stdout.txt

echo ""
echo "=== Agent run finished ==="
echo "Event log:  /workspace/output/events.json"
echo "Summary:    /workspace/output/summary.txt"
echo "Stdout:     /workspace/output/stdout.txt"
