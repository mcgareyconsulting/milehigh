"""
One-time device-code link for the Banana Boy mailbox (bb@mhmw.com).

Run interactively once. Signs the mailbox in via Microsoft's device-code flow
(no admin consent, no redirect URI, no client secret) and stores the refresh
token in MicrosoftDelegatedToken so the poller and on-demand pulls can mint
access tokens going forward.

You will be shown a code and a URL; open the URL in any browser, enter the code,
and sign in AS bb@mhmw.com (this is also where bb self-consents to the
Mail.ReadWrite / Mail.Send scopes). Re-run this to re-link if the refresh token
ever dies (password rotation, MFA policy change, long inactivity).

Usage:
    ENVIRONMENT=sandbox .venv/bin/python -m scripts.link_bb_mailbox

Requires AZURE_TENANT_ID and AZURE_CLIENT_ID in the environment (the fresh
app registration). The token is written to whatever DB ENVIRONMENT selects —
run it against the same environment the poller runs in.
"""
import sys

from app import create_app
from app.config import Config as cfg
from app.microsoft.graph_delegated import link_mailbox


def main():
    if not cfg.AZURE_TENANT_ID or not cfg.AZURE_CLIENT_ID:
        print("✗ AZURE_TENANT_ID and AZURE_CLIENT_ID must be set in the environment.")
        return 2

    app = create_app()
    with app.app_context():
        print(f"Linking mailbox: {cfg.BB_MAILBOX}")
        try:
            link_mailbox()
        except Exception as exc:  # noqa: BLE001 - surface any failure to the operator
            print(f"\n✗ Linking failed: {exc}")
            return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
