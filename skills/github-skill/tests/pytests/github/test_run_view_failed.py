"""Grading: view-failed-run-logs test case.

Verify the agent used `gh run view` with --log-failed and correct run ID.
Inspects the OpenHands event log (terminal commands actually executed).
"""


def test_executed_gh_run_view(terminal_commands: list[str]):
    """Agent must have actually executed a `gh run view` command."""
    matching = [c for c in terminal_commands if "gh" in c and "run" in c and "view" in c]
    assert matching, (
        f"Expected agent to execute `gh run view`, but no matching terminal command found.\n"
        f"Commands executed: {terminal_commands}"
    )


def test_correct_run_id(terminal_commands: list[str]):
    """Agent must reference run ID 12345678."""
    matching = [c for c in terminal_commands if "gh" in c and "run" in c and "view" in c]
    has_id = any("12345678" in c for c in matching)
    assert has_id, (
        f"Expected run ID 12345678 in gh run view command.\n"
        f"Matching commands: {matching}"
    )


def test_uses_log_failed_flag(terminal_commands: list[str]):
    """Agent must use --log-failed to show only failed step logs."""
    matching = [c for c in terminal_commands if "gh" in c and "run" in c and "view" in c]
    has_flag = any("--log-failed" in c for c in matching)
    assert has_flag, (
        f"Expected `--log-failed` flag in gh run view command.\n"
        f"Matching commands: {matching}"
    )


def test_specifies_repo_flag(terminal_commands: list[str]):
    """Agent must use --repo acme/webapp."""
    matching = [c for c in terminal_commands if "gh" in c and "run" in c and "view" in c]
    has_repo = any("--repo" in c and "acme/webapp" in c for c in matching)
    assert has_repo, (
        f"Expected `--repo acme/webapp` flag in gh run view command.\n"
        f"Matching commands: {matching}"
    )
