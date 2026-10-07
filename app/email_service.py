"""
Sends transactional emails (password resets and lead notifications).

Supported Transports:
1. Resend HTTPS REST API (Recommended for Deployed / Cloud Environments):
   Bypasses outbound SMTP port blocks (Render, Railway, DigitalOcean, etc.)
   using standard HTTPS REST API calls (Port 443).
   Add to .env:
       RESEND_API_KEY=re_xxxxxxxxx
       EMAIL_FROM="Chatbot Platform <onboarding@resend.dev>"

2. Gmail SMTP (Fallback for Local Development):
   Add to .env:
       GMAIL_ADDRESS=your-platform-account@gmail.com
       GMAIL_APP_PASSWORD=xxxx xxxx xxxx xxxx
"""

import os
import smtplib
import logging
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import httpx

logger = logging.getLogger("chatbot_platform.email")


def _send_email_transport(
    to_email: str,
    subject: str,
    text_body: str,
    html_body: str,
) -> None:
    """
    Dispatches transactional email using either Resend API or Gmail SMTP.
    Prefers Resend if RESEND_API_KEY is present (ideal for deployed servers).
    """
    resend_api_key = os.environ.get("RESEND_API_KEY")
    if resend_api_key and resend_api_key.strip():
        from_email = os.environ.get("EMAIL_FROM") or "Chatbot Platform <onboarding@resend.dev>"
        headers = {
            "Authorization": f"Bearer {resend_api_key.strip()}",
            "Content-Type": "application/json",
        }
        payload = {
            "from": from_email.strip(),
            "to": [to_email.strip()],
            "subject": subject,
            "text": text_body,
            "html": html_body,
        }
        try:
            with httpx.Client(timeout=10.0) as client:
                resp = client.post("https://api.resend.com/emails", headers=headers, json=payload)
                if resp.status_code >= 400:
                    raise RuntimeError(f"Resend API error ({resp.status_code}): {resp.text}")
            logger.info(f"Transactional email sent via Resend to {to_email}")
            return
        except Exception as e:
            logger.error(f"Failed to send email via Resend to {to_email}: {e}")
            raise e

    # Fallback: Gmail SMTP
    gmail_address = os.environ.get("GMAIL_ADDRESS")
    gmail_app_password = os.environ.get("GMAIL_APP_PASSWORD")

    if not gmail_address or not gmail_app_password:
        raise RuntimeError(
            "Neither RESEND_API_KEY nor GMAIL_ADDRESS / GMAIL_APP_PASSWORD are set in .env. "
            "Configure RESEND_API_KEY (recommended for cloud hosting) or Gmail credentials."
        )

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = gmail_address
    msg["To"] = to_email
    msg.attach(MIMEText(text_body, "plain", "utf-8"))
    msg.attach(MIMEText(html_body, "html", "utf-8"))

    with smtplib.SMTP("smtp.gmail.com", 587, timeout=5) as server:
        server.starttls()
        server.login(gmail_address, gmail_app_password)
        server.send_message(msg)
    logger.info(f"Transactional email sent via Gmail SMTP to {to_email}")


def send_password_reset_email(to_email: str, reset_link: str) -> None:
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

    _send_email_transport(
        to_email=to_email,
        subject="Reset your Chatbot Platform password",
        text_body=text_body,
        html_body=html_body,
    )


def send_lead_notification_email(
    to_email: str,
    tenant_id: str,
    lead_name: str,
    lead_email: str = None,
    lead_phone: str = None,
    lead_message: str = None,
) -> None:
    """Best-effort notification to business owner when a new lead is captured (T9)."""
    contact_parts = []
    if lead_email:
        contact_parts.append(f"Email: {lead_email}")
    if lead_phone:
        contact_parts.append(f"Phone: {lead_phone}")
    contact_str = " | ".join(contact_parts) or "No direct contact method"

    text_body = (
        f"New Contact Lead from Chatbot ({tenant_id})\n\n"
        f"Name: {lead_name}\n"
        f"{contact_str}\n"
        f"Note: {lead_message or 'No additional note'}\n\n"
        "Check your business owner dashboard to view recent chat context and respond to this lead."
    )

    html_body = f"""<!doctype html>
<html>
  <body style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif; background-color: #f8fafc; padding: 24px; margin: 0;">
    <div style="max-width: 520px; margin: 0 auto; background: #ffffff; border-radius: 12px; padding: 28px; border: 1px solid #e2e8f0;">
      <h2 style="color: #0b1224; font-size: 18px; margin: 0 0 8px;">New Customer Contact Lead</h2>
      <p style="color: #64748b; font-size: 13px; line-height: 1.5; margin: 0 0 20px;">
        A customer requested contact via your chatbot for <strong>{tenant_id}</strong>:
      </p>
      <div style="background: #f8fafc; border: 1px solid #edf2f7; border-radius: 8px; padding: 16px; margin: 0 0 20px; font-size: 13px; line-height: 1.6; color: #1e293b;">
        <p style="margin: 0 0 6px;"><strong>Name:</strong> {lead_name}</p>
        {f'<p style="margin: 0 0 6px;"><strong>Email:</strong> {lead_email}</p>' if lead_email else ''}
        {f'<p style="margin: 0 0 6px;"><strong>Phone:</strong> {lead_phone}</p>' if lead_phone else ''}
        {f'<p style="margin: 0;"><strong>Message:</strong> {lead_message}</p>' if lead_message else ''}
      </div>
      <p style="color: #94a3b8; font-size: 11px; margin: 0;">
        Sign in to your admin dashboard to view the conversation history and update this lead.
      </p>
    </div>
  </body>
</html>"""

    _send_email_transport(
        to_email=to_email,
        subject=f"New Lead: {lead_name} ({tenant_id})",
        text_body=text_body,
        html_body=html_body,
    )