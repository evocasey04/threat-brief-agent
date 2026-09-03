"""Email delivery over SMTP with STARTTLS.

Written against Gmail (free, app-password auth) but any SMTP host works — it's
just host/port/user/password.
"""

from __future__ import annotations

import logging
import smtplib
import ssl
from email.message import EmailMessage
from email.utils import formatdate, make_msgid

log = logging.getLogger(__name__)


def send_email(
    *,
    subject: str,
    text_body: str,
    html_body: str,
    host: str,
    port: int,
    username: str,
    password: str,
    sender: str,
    recipients: list[str],
    timeout: int = 30,
) -> None:
    """Send a multipart/alternative message. Raises on failure."""
    if not recipients:
        raise ValueError("no recipients configured (set MAIL_TO or SMTP_USER)")

    message = EmailMessage()
    message["Subject"] = subject
    message["From"] = sender or username
    message["To"] = ", ".join(recipients)
    message["Date"] = formatdate(localtime=True)
    message["Message-ID"] = make_msgid(domain="threat-brief-agent.local")
    message.set_content(text_body)
    message.add_alternative(html_body, subtype="html")

    context = ssl.create_default_context()

    if port == 465:
        with smtplib.SMTP_SSL(host, port, timeout=timeout, context=context) as server:
            server.login(username, password)
            server.send_message(message)
    else:
        with smtplib.SMTP(host, port, timeout=timeout) as server:
            server.ehlo()
            server.starttls(context=context)
            server.ehlo()
            server.login(username, password)
            server.send_message(message)

    log.info("email sent to %s", ", ".join(recipients))
