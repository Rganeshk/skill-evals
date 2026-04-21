"""Grading: list-workflow-runs test case.

Verify the agent used `gh run list` with --limit and --repo flags.
Inspects the OpenHands event log (terminal commands actually executed).
"""


def test_executed_gh_run_list(terminal_commands: list[str]):
    """Agent must have actually executed a `gh run list` command."""
    matching = [c for c in terminal_commands if "gh" in c and "run" in c and "list" in c]
    assert matching, (
        f"Expected agent to execute `gh run list`, but no matching terminal command found.\n"
        f"Commands executed: {terminal_commands}"
    )


def test_specifies_limit(terminal_commands: list[str]):
    """Agent must use --limit flag."""
    matching = [c for c in terminal_commands if "gh" in c and "run" in c and "list" in c]
    has_limit = any("--limit" in c for c in matching)
    assert has_limit, (
        f"Expected `--limit` flag in gh run list command.\n"
        f"Matching commands: {matching}"
    )


def test_specifies_repo_flag(terminal_commands: list[str]):
    """Agent must use --repo acme/webapp."""
    matching = [c for c in terminal_commands if "gh" in c and "run" in c and "list" in c]
    has_repo = any("--repo" in c and "acme/webapp" in c for c in matching)
    assert has_repo, (
        f"Expected `--repo acme/webapp` flag in gh run list command.\n"
        f"Matching commands: {matching}"
    )
