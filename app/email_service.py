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
from email.mime.multipart import MIMEMultipart

# Deliberately NOT read/validated at module import time (that was the bug -
# see below). Read fresh inside send_password_reset_email() instead, the
# same lazy pattern already used correctly for GROQ_API_KEY/ANTHROPIC_API_KEY
# in groq_client.py
#
# WHY THIS MATTERS: main.py does `from app.email_service import
# send_password_reset_email` unconditionally at the top of the file, as
# part of loading the whole application. If this module raised at IMPORT
# time (as it used to) whenever Gmail credentials were missing, that
# single missing credential for a non-critical feature (password reset
# email) would prevent the ENTIRE app from starting - including live chat,
# admin login, everything - not just password reset. A production deploy
# that hasn't gotten around to setting up a Gmail App Password yet would
# refuse to boot at all. Making this lazy means the app starts fine
# regardless, and only an actual password-reset attempt fails - and even
# that fails safely, since /auth/forgot-password in main.py already wraps
# this call in a try/except and returns its normal generic success message
# either way (so this also doesn't create a new email-enumeration signal).


def send_password_reset_email(to_email: str, reset_link: str) -> None:
    gmail_address = os.environ.get("GMAIL_ADDRESS")
    gmail_app_password = os.environ.get("GMAIL_APP_PASSWORD")

    if not gmail_address or not gmail_app_password:
        raise RuntimeError(
            "GMAIL_ADDRESS / GMAIL_APP_PASSWORD are not set in .env - the "
            "password reset feature requires Gmail to be configured. Generate "
            "an App Password at https://myaccount.google.com/apppasswords "
            "(requires 2-Step Verification enabled on that Gmail account first)."
        )

    # Same navy/amber brand colors as admin-vue's tailwind.config.js, so the
    # email matches the actual product instead of looking like a generic
    # unbranded system notification.
    NAVY = "#0b1224"
    AMBER = "#e0a527"
    AMBER_DARK = "#c8901c"
    SLATE_TEXT = "#334155"
    SLATE_MUTED = "#64748b"
    BORDER = "#e2e8f0"

    text_body = (
        f"We received a request to reset your Chatbot Platform password.\n\n"
        f"Click the link below to choose a new password. This link expires "
        f"in 30 minutes:\n\n{reset_link}\n\n"
        f"If you didn't request this, you can safely ignore this email - "
        f"your password won't be changed."
    )

    # HTML email quirks: inline styles only (most clients strip <style>
    # blocks), table-based layout (most reliable across Outlook/Gmail/etc),
    # and a plain-text fallback link below the button in case the button
    # itself doesn't render or the recipient's client blocks images/CTAs.
    html_body = f"""\
<!DOCTYPE html>
<html>
  <head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
  </head>
  <body style="margin:0; padding:0; background-color:#f1f5f9; font-family:-apple-system,Segoe UI,Roboto,Helvetica,Arial,sans-serif;">
    <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background-color:#f1f5f9; padding:32px 16px;">
      <tr>
        <td align="center">
          <table role="presentation" width="480" cellpadding="0" cellspacing="0" style="max-width:480px; width:100%; background-color:#ffffff; border-radius:16px; overflow:hidden; box-shadow:0 1px 3px rgba(0,0,0,0.08);">

            <!-- Header -->
            <tr>
              <td style="background-color:{NAVY}; padding:28px 32px; text-align:center;">
                <table role="presentation" cellpadding="0" cellspacing="0" style="margin:0 auto;">
                  <tr>
                    <td style="width:44px; height:44px; background-color:{AMBER}; border-radius:10px; text-align:center; vertical-align:middle; font-weight:700; font-size:14px; color:{NAVY};">
                      CP
                    </td>
                  </tr>
                </table>
                <p style="margin:14px 0 0; color:#ffffff; font-size:15px; font-weight:600;">Chatbot Platform</p>
              </td>
            </tr>

            <!-- Body -->
            <tr>
              <td style="padding:32px;">
                <h1 style="margin:0 0 12px; color:{NAVY}; font-size:18px; font-weight:700;">Reset your password</h1>
                <p style="margin:0 0 24px; color:{SLATE_TEXT}; font-size:14px; line-height:22px;">
                  We received a request to reset your Chatbot Platform password.
                  Click the button below to choose a new one. This link expires
                  in <strong>30 minutes</strong>.
                </p>

                <table role="presentation" cellpadding="0" cellspacing="0" style="margin:0 0 24px;">
                  <tr>
                    <td style="border-radius:10px; background-color:{AMBER};">
                      <a href="{reset_link}"
                         style="display:inline-block; padding:12px 28px; color:{NAVY}; font-size:14px; font-weight:700; text-decoration:none; border-radius:10px;">
                        Reset Password
                      </a>
                    </td>
                  </tr>
                </table>

                <p style="margin:0 0 8px; color:{SLATE_MUTED}; font-size:12px; line-height:18px;">
                  Or copy and paste this link into your browser:
                </p>
                <p style="margin:0 0 24px; word-break:break-all;">
                  <a href="{reset_link}" style="color:{AMBER_DARK}; font-size:12px;">{reset_link}</a>
                </p>

                <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="border-top:1px solid {BORDER}; padding-top:16px;">
                  <tr>
                    <td>
                      <p style="margin:0; color:{SLATE_MUTED}; font-size:12px; line-height:18px;">
                        If you didn't request this, you can safely ignore this
                        email \u2014 your password won't be changed.
                      </p>
                    </td>
                  </tr>
                </table>
              </td>
            </tr>
          </table>
        </td>
      </tr>
    </table>
  </body>
</html>
"""

    msg = MIMEMultipart("alternative")
    msg["Subject"] = "Reset your Chatbot Platform password"
    msg["From"] = gmail_address
    msg["To"] = to_email
    # Plain text part attached FIRST, HTML second - per the MIME spec for
    # multipart/alternative, clients render the LAST part they understand,
    # so this ordering makes HTML-capable clients show the styled version
    # while plain-text-only clients fall back to the text version.
    msg.attach(MIMEText(text_body, "plain", "utf-8"))
    msg.attach(MIMEText(html_body, "html", "utf-8"))

    with smtplib.SMTP("smtp.gmail.com", 587) as server:
        server.starttls()
        server.login(gmail_address, gmail_app_password)
        server.send_message(msg)