"""
Sends transactional emails (currently just password resets) via Gmail SMTP.

Uses only Python's standard library (smtplib + email) - no new pip package,
no new venv risk. Gmail requires an "App Password" for this, not your
regular Gmail password - regular passwords are blocked by Google for SMTP
login. Generate one at: https://myaccount.google.com/apppasswords
(requires 2-Step Verification to be turned on for the Gmail account first).

Add to .env:
    GMAIL_ADDRESS=your-platform-account@gmail.com
    GMAIL_APP_PASSWORD=xxxx xxxx xxxx xxxx   (the 16-char app password, spaces are fine)
"""

import os
import smtplib
from email.mime.text import MIMEText

GMAIL_ADDRESS = os.environ.get("GMAIL_ADDRESS")
GMAIL_APP_PASSWORD = os.environ.get("GMAIL_APP_PASSWORD")

if not GMAIL_ADDRESS or not GMAIL_APP_PASSWORD:
    raise RuntimeError(
        "GMAIL_ADDRESS / GMAIL_APP_PASSWORD are not set in .env - the "
        "password reset feature requires Gmail to be configured. Generate "
        "an App Password at https://myaccount.google.com/apppasswords "
        "(requires 2-Step Verification enabled on that Gmail account first)."
    )


def send_password_reset_email(to_email: str, reset_link: str) -> None:

    body = (
        f"We received a request to reset your Chatbot Platform password.\n\n"
        f"Click the link below to choose a new password. This link expires "
        f"in 30 minutes:\n\n{reset_link}\n\n"
        f"If you didn't request this, you can safely ignore this email - "
        f"your password won't be changed."
    )
    msg = MIMEText(body)
    msg["Subject"] = "Reset your Chatbot Platform password"
    msg["From"] = GMAIL_ADDRESS
    msg["To"] = to_email

    with smtplib.SMTP("smtp.gmail.com", 587) as server:
        server.starttls()
        server.login(GMAIL_ADDRESS, GMAIL_APP_PASSWORD)
        server.send_message(msg)