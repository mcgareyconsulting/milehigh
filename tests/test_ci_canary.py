"""
Canary test for CI/CD pipeline verification.

This test intentionally fails so that:
1. The GitHub Actions workflow can be verified end-to-end
2. A subagent reviewing PR failures can detect and report bugs

Remove or update this test once the pipeline is confirmed working.
"""


def test_canary_fails():
    """Intentionally failing test to verify CI catches failures."""
    assert False, "CI canary: this test is supposed to fail — remove once pipeline is verified"
