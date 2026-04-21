"""Run the OpenHands agent inside Docker and capture events.

This script:
1. Reads the prompt from /workspace/prompt.txt
2. Optionally prepends skill context from /workspace/skill.md
3. Launches an OpenHands agent with the LocalConversation API
4. Collects all events via callback
5. Serializes events to /workspace/output/events.json
6. Writes a human-readable summary to /workspace/output/summary.txt
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

from pydantic import SecretStr

from openhands.sdk import LLM, Agent, LocalConversation, Message, TextContent
from openhands.sdk.conversation.visualizer import DefaultConversationVisualizer
from openhands.sdk.event import ActionEvent, ObservationEvent, Event
from openhands.tools.preset.default import get_default_tools
from openhands.tools.terminal.definition import TerminalAction, TerminalTool

# ── Configuration from environment ──────────────────────────────────
LLM_MODEL = os.environ.get("LLM_MODEL", "openai/gpt-5.1-mini")
LLM_API_KEY = os.environ.get("LLM_API_KEY", "")
# OpenAI Chat Completions base (LiteLLM / OpenAI-compatible clients).
LLM_BASE_URL = os.environ.get("LLM_BASE_URL", "https://api.openai.com/v1")
MAX_ITERATIONS = int(os.environ.get("MAX_ITERATIONS", "50"))
WORKSPACE_DIR = os.environ.get("AGENT_WORKSPACE", "/workspace/input")

# ── Read prompt and skill ───────────────────────────────────────────
prompt_text = Path("/workspace/prompt.txt").read_text().strip()

skill_path = Path("/workspace/skill.md")
if skill_path.exists():
    skill_text = skill_path.read_text().strip()
    # Prepend skill context to the instruction so the agent has it
    full_prompt = (
        f"You have the following skill loaded. Use it to complete the task.\n\n"
        f"--- SKILL START ---\n{skill_text}\n--- SKILL END ---\n\n"
        f"Task:\n{prompt_text}"
    )
else:
    full_prompt = prompt_text

# ── Set up the agent ────────────────────────────────────────────────
if not LLM_API_KEY:
    print("ERROR: LLM_API_KEY environment variable is required.", file=sys.stderr)
    sys.exit(1)

llm = LLM(
    model=LLM_MODEL,
    api_key=SecretStr(LLM_API_KEY),
    base_url=LLM_BASE_URL,
    usage_id="skill-eval",
)

tools = get_default_tools(enable_browser=False)
agent = Agent(llm=llm, tools=tools)

# ── Collect events ──────────────────────────────────────────────────
collected_events: list[Event] = []


def event_callback(event: Event) -> None:
    collected_events.append(event)


conversation = LocalConversation(
    agent=agent,
    workspace=WORKSPACE_DIR,
    callbacks=[event_callback],
    visualizer=DefaultConversationVisualizer(),
    max_iteration_per_run=MAX_ITERATIONS,
)

# ── Run ─────────────────────────────────────────────────────────────
print(f"Starting OpenHands agent (model={LLM_MODEL}, max_iter={MAX_ITERATIONS})")
print(f"Workspace: {WORKSPACE_DIR}")
print(f"Prompt: {prompt_text[:200]}...")
print("=" * 60)

message = Message(role="user", content=[TextContent(text=full_prompt)])
conversation.send_message(message=message)
conversation.run()

# ── Serialize events to JSON ────────────────────────────────────────
output_dir = Path("/workspace/output")

events_data = []
for event in collected_events:
    try:
        event_dict = {
            "type": type(event).__name__,
            "id": getattr(event, "id", None),
            "timestamp": str(getattr(event, "timestamp", "")),
            "source": getattr(event, "source", None),
        }

        # Extract terminal commands
        if isinstance(event, ActionEvent):
            event_dict["tool_name"] = event.tool_name
            event_dict["summary"] = event.summary
            if event.action is not None and isinstance(event.action, TerminalAction):
                event_dict["command"] = event.action.command
                event_dict["action_type"] = "terminal"
            elif event.action is not None:
                event_dict["action_type"] = type(event.action).__name__
                # Capture file editor actions
                if hasattr(event.action, "command"):
                    event_dict["file_command"] = event.action.command
                if hasattr(event.action, "path"):
                    event_dict["file_path"] = event.action.path

        # Extract observations
        if isinstance(event, ObservationEvent):
            event_dict["tool_name"] = event.tool_name
            obs = event.observation
            if hasattr(obs, "exit_code"):
                event_dict["exit_code"] = obs.exit_code
            if hasattr(obs, "command"):
                event_dict["obs_command"] = obs.command
            # Truncate large observation content
            content = str(obs)
            event_dict["content"] = content[:2000] if len(content) > 2000 else content

        events_data.append(event_dict)
    except Exception as e:
        events_data.append({
            "type": type(event).__name__,
            "error": f"Failed to serialize: {e}",
        })

with open(output_dir / "events.json", "w") as f:
    json.dump(events_data, f, indent=2, default=str)

# ── Write human-readable summary ────────────────────────────────────
summary_parts = []
for event in collected_events:
    try:
        viz = event.visualize
        plain = viz.plain.strip() if viz else ""
        if plain:
            summary_parts.append(f"[{type(event).__name__}]\n{plain}\n")
    except Exception:
        summary_parts.append(f"[{type(event).__name__}] (could not visualize)\n")

summary_text = "\n".join(summary_parts)
with open(output_dir / "summary.txt", "w") as f:
    f.write(summary_text)

# ── Print stats ─────────────────────────────────────────────────────
terminal_cmds = [
    e for e in events_data
    if e.get("action_type") == "terminal" and e.get("command")
]
print("=" * 60)
print(f"Total events collected: {len(collected_events)}")
print(f"Terminal commands executed: {len(terminal_cmds)}")
for cmd in terminal_cmds:
    print(f"  $ {cmd['command']}")
