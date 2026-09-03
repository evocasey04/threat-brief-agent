"""Tests for agent/deliver.py.

All tests use mocked SMTP so nothing touches the network.
"""

from __future__ import annotations

from unittest.mock import MagicMock, call, patch

import pytest

from agent.deliver import send_email

COMMON = dict(
    subject="[CRITICAL] Threat Brief — Wed 03 Sep 2026",
    text_body="Plain text body.",
    html_body="<p>HTML body.</p>",
    host="smtp.gmail.com",
    username="sender@gmail.com",
    password="secret",
    sender="sender@gmail.com",
    recipients=["recipient@example.com"],
)


def test_raises_when_no_recipients():
    with pytest.raises(ValueError, match="no recipients"):
        send_email(**{**COMMON, "recipients": []}, port=587)


def test_starttls_path_login_and_send(monkeypatch):
    mock_server = MagicMock()
    mock_cls = MagicMock(return_value=mock_server)
    mock_server.__enter__ = MagicMock(return_value=mock_server)
    mock_server.__exit__ = MagicMock(return_value=False)

    with patch("agent.deliver.smtplib.SMTP", mock_cls):
        send_email(**COMMON, port=587)

    mock_cls.assert_called_once_with("smtp.gmail.com", 587, timeout=30)
    mock_server.starttls.assert_called_once()
    mock_server.login.assert_called_once_with("sender@gmail.com", "secret")
    mock_server.send_message.assert_called_once()


def test_ssl_path_used_for_port_465(monkeypatch):
    mock_server = MagicMock()
    mock_cls = MagicMock(return_value=mock_server)
    mock_server.__enter__ = MagicMock(return_value=mock_server)
    mock_server.__exit__ = MagicMock(return_value=False)

    with patch("agent.deliver.smtplib.SMTP_SSL", mock_cls):
        send_email(**COMMON, port=465)

    mock_cls.assert_called_once()
    mock_server.login.assert_called_once_with("sender@gmail.com", "secret")
    mock_server.send_message.assert_called_once()


def test_ssl_path_does_not_call_starttls():
    mock_server = MagicMock()
    mock_cls = MagicMock(return_value=mock_server)
    mock_server.__enter__ = MagicMock(return_value=mock_server)
    mock_server.__exit__ = MagicMock(return_value=False)

    with patch("agent.deliver.smtplib.SMTP_SSL", mock_cls):
        send_email(**COMMON, port=465)

    mock_server.starttls.assert_not_called()


def test_message_headers_are_set_correctly():
    captured = {}

    def capture_send(msg):
        captured["msg"] = msg

    mock_server = MagicMock()
    mock_server.__enter__ = MagicMock(return_value=mock_server)
    mock_server.__exit__ = MagicMock(return_value=False)
    mock_server.send_message.side_effect = capture_send

    with patch("agent.deliver.smtplib.SMTP", MagicMock(return_value=mock_server)):
        send_email(**COMMON, port=587)

    msg = captured["msg"]
    assert msg["Subject"] == COMMON["subject"]
    assert msg["From"] == COMMON["sender"]
    assert "recipient@example.com" in msg["To"]


def test_multiple_recipients_joined_in_to_header():
    captured = {}

    def capture_send(msg):
        captured["msg"] = msg

    mock_server = MagicMock()
    mock_server.__enter__ = MagicMock(return_value=mock_server)
    mock_server.__exit__ = MagicMock(return_value=False)
    mock_server.send_message.side_effect = capture_send

    params = {**COMMON, "recipients": ["a@example.com", "b@example.com"]}
    with patch("agent.deliver.smtplib.SMTP", MagicMock(return_value=mock_server)):
        send_email(**params, port=587)

    assert "a@example.com" in captured["msg"]["To"]
    assert "b@example.com" in captured["msg"]["To"]


def test_sender_falls_back_to_username_when_empty():
    captured = {}

    def capture_send(msg):
        captured["msg"] = msg

    mock_server = MagicMock()
    mock_server.__enter__ = MagicMock(return_value=mock_server)
    mock_server.__exit__ = MagicMock(return_value=False)
    mock_server.send_message.side_effect = capture_send

    params = {**COMMON, "sender": ""}
    with patch("agent.deliver.smtplib.SMTP", MagicMock(return_value=mock_server)):
        send_email(**params, port=587)

    assert captured["msg"]["From"] == COMMON["username"]


def test_custom_timeout_is_forwarded():
    mock_cls = MagicMock()
    mock_server = MagicMock()
    mock_cls.return_value = mock_server
    mock_server.__enter__ = MagicMock(return_value=mock_server)
    mock_server.__exit__ = MagicMock(return_value=False)

    with patch("agent.deliver.smtplib.SMTP", mock_cls):
        send_email(**COMMON, port=587, timeout=60)

    mock_cls.assert_called_once_with("smtp.gmail.com", 587, timeout=60)
