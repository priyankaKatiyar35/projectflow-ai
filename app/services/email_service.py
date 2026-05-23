"""
app/services/email_service.py

Sends emails via SMTP. Configurable via environment variables.

If SMTP isn't configured, falls back to logging the email to console
(perfect for local development - no SMTP needed to test).

Configuration (set in .env or Render dashboard):
  SMTP_HOST     -- e.g. smtp.gmail.com
  SMTP_PORT     -- 587 (TLS) or 465 (SSL)
  SMTP_USER     -- your full email
  SMTP_PASSWORD -- app password (NOT your real Gmail password)
  SMTP_FROM     -- "Your App <noreply@yourdomain.com>"
  SMTP_TLS      -- "true" (default) or "false"
  APP_BASE_URL  -- used for building absolute links, e.g. https://your-app.onrender.com

For Gmail:
  1. Enable 2FA on your Google account
  2. Go to https://myaccount.google.com/apppasswords
  3. Generate an app password
  4. Use that 16-char password as SMTP_PASSWORD (not your real password)
"""
import os
import smtplib
import ssl
from email.message import EmailMessage
from email.utils import formataddr
from typing import Optional


# ---- Configuration ----
SMTP_HOST     = os.getenv("SMTP_HOST", "").strip()
SMTP_PORT     = int(os.getenv("SMTP_PORT", "587") or "587")
SMTP_USER     = os.getenv("SMTP_USER", "").strip()
SMTP_PASSWORD = os.getenv("SMTP_PASSWORD", "")
SMTP_FROM     = os.getenv("SMTP_FROM", "").strip() or SMTP_USER
SMTP_TLS      = (os.getenv("SMTP_TLS", "true").lower() != "false")
APP_BASE_URL  = os.getenv("APP_BASE_URL", "http://localhost:8000").rstrip("/")


def is_configured() -> bool:
    """Are SMTP credentials set?"""
    return bool(SMTP_HOST and SMTP_USER and SMTP_PASSWORD)


# ---- HTML email template ----
EMAIL_HTML_TEMPLATE = """\
<!DOCTYPE html>
<html>
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{title}</title>
</head>
<body style="margin:0;padding:0;background:#f1f5f9;font-family:-apple-system,Segoe UI,Roboto,sans-serif;">
  <div style="max-width:560px;margin:32px auto;background:#ffffff;border-radius:16px;overflow:hidden;box-shadow:0 8px 24px rgba(0,0,0,0.06);">

    <!-- Header bar with gradient -->
    <div style="background:linear-gradient(135deg,#667eea,#764ba2);padding:24px 32px;color:white;">
      <p style="margin:0;font-size:11px;text-transform:uppercase;letter-spacing:0.06em;font-weight:600;opacity:0.85;">Timesheet AI</p>
      <h1 style="margin:6px 0 0;font-size:22px;line-height:1.3;font-weight:700;">{title}</h1>
    </div>

    <!-- Body -->
    <div style="padding:28px 32px;">
      <p style="margin:0 0 16px;color:#1e293b;font-size:15px;line-height:1.55;">Hi {recipient_name},</p>
      <div style="color:#334155;font-size:15px;line-height:1.6;">{body_html}</div>

      {action_button_html}

      <div style="margin-top:32px;padding-top:20px;border-top:1px solid #e2e8f0;color:#64748b;font-size:12px;line-height:1.6;">
        <p style="margin:0 0 4px;">This message was sent automatically. Do not reply.</p>
        <p style="margin:0;">If you don't want to receive these emails, update your preferences in
          <a href="{settings_url}" style="color:#667eea;">settings</a>.</p>
      </div>
    </div>

    <div style="padding:18px 32px;background:#f8fafc;color:#94a3b8;font-size:11px;text-align:center;">
      Timesheet AI &middot; CMMI-compliant project management
    </div>
  </div>
</body>
</html>
"""


def send_email(
    to_email: str,
    to_name: str,
    subject: str,
    body_html: str,
    link_url: Optional[str] = None,
    link_label: str = "View in app",
) -> bool:
    """
    Send a single email. Returns True if sent (or logged to console in dev mode).

    Never raises — if SMTP fails, logs the error and returns False.
    """
    if not is_configured():
        # ----- Development mode: log to console instead of sending -----
        print("\n" + "=" * 70)
        print("📧 [EMAIL - SMTP not configured, would have sent]")
        print(f"   To:      {to_name} <{to_email}>")
        print(f"   Subject: {subject}")
        if link_url:
            print(f"   Link:    {link_url}")
        print(f"   Body:    {body_html[:200]}{'...' if len(body_html) > 200 else ''}")
        print("=" * 70 + "\n")
        return True  # treat as success in dev mode

    action_button = ""
    if link_url:
        action_button = f'''
        <div style="margin:24px 0;text-align:center;">
          <a href="{link_url}" style="display:inline-block;padding:12px 28px;background:linear-gradient(135deg,#667eea,#764ba2);color:white;text-decoration:none;border-radius:10px;font-weight:600;font-size:14px;">
            {link_label} →
          </a>
        </div>
        '''

    settings_url = f"{APP_BASE_URL}/email-settings"
    html_body = EMAIL_HTML_TEMPLATE.format(
        title=subject,
        recipient_name=to_name.split()[0] if to_name else "there",
        body_html=body_html,
        action_button_html=action_button,
        settings_url=settings_url,
    )

    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = SMTP_FROM if "<" in SMTP_FROM else formataddr(("Timesheet AI", SMTP_FROM))
    msg["To"] = formataddr((to_name or to_email, to_email))
    # Plain text fallback (strip HTML)
    import re
    plain_text = re.sub(r"<[^>]+>", "", body_html).strip()
    msg.set_content(plain_text)
    msg.add_alternative(html_body, subtype="html")

    try:
        ctx = ssl.create_default_context()
        if SMTP_PORT == 465:
            with smtplib.SMTP_SSL(SMTP_HOST, SMTP_PORT, context=ctx, timeout=10) as smtp:
                smtp.login(SMTP_USER, SMTP_PASSWORD)
                smtp.send_message(msg)
        else:
            with smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=10) as smtp:
                if SMTP_TLS:
                    smtp.starttls(context=ctx)
                smtp.login(SMTP_USER, SMTP_PASSWORD)
                smtp.send_message(msg)
        return True
    except Exception as e:
        print(f"[email_service] Failed to send to {to_email}: {e}")
        return False


def send_notification_email(
    to_email: str,
    to_name: str,
    title: str,
    body: str,
    link_path: Optional[str] = None,
    notification_type: str = "system",
) -> bool:
    """Convenience wrapper for sending notification-style emails."""
    link_url = None
    if link_path:
        link_url = APP_BASE_URL + (link_path if link_path.startswith("/") else "/" + link_path)

    return send_email(
        to_email=to_email,
        to_name=to_name,
        subject=title,
        body_html=f"<p>{body}</p>" if body else "",
        link_url=link_url,
        link_label="Open in app",
    )