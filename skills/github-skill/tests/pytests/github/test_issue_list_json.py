"""Grading: json-issue-list test case.

Verify the agent used `gh issue list` with --json and --jq flags.
Inspects the OpenHands event log (terminal commands actually executed).
"""


def test_executed_gh_issue_list(terminal_commands: list[str]):
    """Agent must have actually executed a `gh issue list` command."""
    matching = [c for c in terminal_commands if "gh" in c and "issue" in c and "list" in c]
    assert matching, (
        f"Expected agent to execute `gh issue list`, but no matching terminal command found.\n"
        f"Commands executed: {terminal_commands}"
    )


def test_uses_json_flag(terminal_commands: list[str]):
    """Agent must use --json flag for structured output."""
    matching = [c for c in terminal_commands if "gh" in c and "issue" in c and "list" in c]
    has_json = any("--json" in c for c in matching)
    assert has_json, (
        f"Expected `--json` flag in gh issue list command.\n"
        f"Matching commands: {matching}"
    )


def test_uses_jq_flag(terminal_commands: list[str]):
    """Agent must use --jq flag for filtering/formatting."""
    matching = [c for c in terminal_commands if "gh" in c and "issue" in c and "list" in c]
    has_jq = any("--jq" in c for c in matching)
    assert has_jq, (
        f"Expected `--jq` flag in gh issue list command.\n"
        f"Matching commands: {matching}"
    )


def test_specifies_repo_flag(terminal_commands: list[str]):
    """Agent must use --repo acme/webapp."""
    matching = [c for c in terminal_commands if "gh" in c and "issue" in c and "list" in c]
    has_repo = any("--repo" in c and "acme/webapp" in c for c in matching)
    assert has_repo, (
        f"Expected `--repo acme/webapp` flag in gh issue list command.\n"
        f"Matching commands: {matching}"
    )


def test_requests_number_and_title(terminal_commands: list[str]):
    """Agent should request number and title fields in --json."""
    matching = [c for c in terminal_commands if "gh" in c and "issue" in c and "--json" in c]
    has_fields = any("number" in c and "title" in c for c in matching)
    assert has_fields, (
        f"Expected 'number' and 'title' in --json field list.\n"
        f"Matching commands: {matching}"
    )
