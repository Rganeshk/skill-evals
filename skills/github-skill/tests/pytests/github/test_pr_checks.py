"""Grading: pr-ci-status test case.

Verify the agent used `gh pr checks` with the correct PR number and --repo flag.
Inspects the OpenHands event log (terminal commands actually executed).
"""


def test_executed_gh_pr_checks(terminal_commands: list[str]):
    """Agent must have actually executed a `gh pr checks` command."""
    matching = [c for c in terminal_commands if "gh" in c and "pr" in c and "checks" in c]
    assert matching, (
        f"Expected agent to execute `gh pr checks`, but no matching terminal command found.\n"
        f"Commands executed: {terminal_commands}"
    )


def test_correct_pr_number(terminal_commands: list[str]):
    """Agent must reference PR #42 in the command."""
    matching = [c for c in terminal_commands if "gh" in c and "checks" in c]
    has_42 = any("42" in c for c in matching)
    assert has_42, (
        f"Expected PR number 42 in gh pr checks command.\n"
        f"Matching commands: {matching}"
    )


def test_specifies_repo_flag(terminal_commands: list[str]):
    """Agent must use --repo acme/webapp."""
    matching = [c for c in terminal_commands if "gh" in c and "checks" in c]
    has_repo = any("--repo" in c and "acme/webapp" in c for c in matching)
    assert has_repo, (
        f"Expected `--repo acme/webapp` flag in gh pr checks command.\n"
        f"Matching commands: {matching}"
    )


def test_no_forbidden_remote_ops(terminal_commands: list[str]):
    """Agent must not push or create PRs — this is a read-only task."""
    forbidden = ("git push", "gh pr create", "gh pr merge")
    bad = [c for c in terminal_commands if any(f in c for f in forbidden)]
    assert not bad, f"Forbidden remote operations detected: {bad}"
