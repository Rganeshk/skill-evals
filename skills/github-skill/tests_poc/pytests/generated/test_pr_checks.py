"""Generated (POC) grader for: pr-checks.

Asserts the agent executed a terminal command containing required tokens.
"""


def test_terminal_contains_required_tokens(terminal_commands: list[str]):
    matching = [c for c in terminal_commands if 'gh' in c and 'pr' in c and 'checks' in c and '42' in c and '--repo' in c and 'acme/webapp' in c]
    assert matching, (
        "Expected a terminal command containing all required tokens.\n"
        f"Required tokens: ['gh', 'pr', 'checks', '42', '--repo', 'acme/webapp']\n"
        f"Commands executed: {terminal_commands}"
    )


def test_no_forbidden_ops(terminal_commands: list[str]):
    forbidden = ('git push', 'gh pr create', 'gh pr merge')
    bad = [c for c in terminal_commands if any(f in c for f in forbidden)]
    assert not bad, f"Forbidden operations detected: {bad}"
