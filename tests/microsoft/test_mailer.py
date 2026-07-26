"""Tests for app.microsoft.mailer.send_mail — sends app-only, as an explicit
mailbox (never a silent default), targeting /users/{from_mailbox}/sendMail.
"""
from unittest.mock import patch

import pytest

from app.microsoft import mailer


def test_send_mail_targets_from_mailbox_app_only():
    with patch.object(mailer, "graph_app_client") as mocked:
        mailer.send_mail(
            from_mailbox="daniel@mhmw.com",
            to_address="sam@acme.test",
            subject="Hello",
            html_content="<p>Hi</p>",
        )

    mocked.graph_post.assert_called_once()
    path = mocked.graph_post.call_args.args[0]
    assert path == "/users/daniel@mhmw.com/sendMail"


def test_send_mail_body_shape():
    with patch.object(mailer, "graph_app_client") as mocked:
        mailer.send_mail(
            from_mailbox="daniel@mhmw.com",
            to_address="sam@acme.test",
            subject="Hello",
            html_content="<p>Hi</p>",
        )

    body = mocked.graph_post.call_args.kwargs["json_body"]
    assert body["message"]["subject"] == "Hello"
    assert body["message"]["body"] == {"contentType": "HTML", "content": "<p>Hi</p>"}
    assert body["message"]["toRecipients"] == [{"emailAddress": {"address": "sam@acme.test"}}]
    assert "ccRecipients" not in body["message"]
    assert body["saveToSentItems"] == "true"


def test_send_mail_cc_address_included_when_given():
    with patch.object(mailer, "graph_app_client") as mocked:
        mailer.send_mail(
            from_mailbox="carmen_ai@mhmw.com",
            to_address="sam@acme.test",
            cc_address="daniel@mhmw.com",
            subject="Hello",
            html_content="<p>Hi</p>",
        )

    body = mocked.graph_post.call_args.kwargs["json_body"]
    assert body["message"]["ccRecipients"] == [{"emailAddress": {"address": "daniel@mhmw.com"}}]


def test_send_mail_requires_from_mailbox():
    """from_mailbox has no default — omitting it is a TypeError, not a silent
    fall-back to some shared identity."""
    with pytest.raises(TypeError):
        mailer.send_mail(to_address="sam@acme.test", subject="x", html_content="x")
