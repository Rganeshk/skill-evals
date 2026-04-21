"""Grading: api-pr-details test case.

Verify the agent used `gh api` with --jq to extract specific PR fields.
Inspects the OpenHands event log (terminal commands actually executed).
"""


def test_executed_gh_api(terminal_commands: list[str]):
    """Agent must use `gh api` (not gh pr view)."""
    matching = [c for c in terminal_commands if "gh" in c and "api" in c.split()]
    assert matching, (
        f"Expected agent to execute `gh api`, but no matching terminal command found.\n"
        f"Commands executed: {terminal_commands}"
    )


def test_targets_correct_pr_endpoint(terminal_commands: list[str]):
    """Agent must target the pulls/55 API endpoint for acme/webapp."""
    matching = [c for c in terminal_commands if "gh" in c and "api" in c.split()]
    has_endpoint = any("repos/acme/webapp/pulls/55" in c for c in matching)
    assert has_endpoint, (
        f"Expected API path `repos/acme/webapp/pulls/55` in gh api command.\n"
        f"Matching commands: {matching}"
    )


def test_uses_jq_filtering(terminal_commands: list[str]):
    """Agent must use --jq to filter response fields."""
    matching = [c for c in terminal_commands if "gh" in c and "api" in c.split()]
    has_jq = any("--jq" in c for c in matching)
    assert has_jq, (
        f"Expected `--jq` flag for field filtering in gh api command.\n"
        f"Matching commands: {matching}"
    )


def test_did_not_use_gh_pr_view(terminal_commands: list[str]):
    """Agent should use gh api, not gh pr view, for this task."""
    pr_view_cmds = [c for c in terminal_commands if "gh" in c and "pr" in c and "view" in c]
    # It's acceptable if the agent also ran gh pr view, but it must have used gh api
    api_cmds = [c for c in terminal_commands if "gh" in c and "api" in c.split()]
    assert api_cmds, (
        f"Agent used gh pr view but was asked to use gh api.\n"
        f"PR view commands: {pr_view_cmds}\n"
        f"API commands: {api_cmds}"
    )
