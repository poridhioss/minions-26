"""Email notification via Gmail SMTP. Credentials are read from env vars."""
import os
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

SMTP_HOST = os.getenv("GMAIL_SMTP_HOST", "smtp.gmail.com")
SMTP_PORT = int(os.getenv("GMAIL_SMTP_PORT", "587"))


def _creds():
    sender = os.getenv("GMAIL_SENDER")
    password = os.getenv("GMAIL_APP_PASSWORD")
    receiver = os.getenv("GMAIL_RECEIVER", sender)
    if not sender or not password:
        raise RuntimeError("GMAIL_SENDER / GMAIL_APP_PASSWORD not set in environment")
    return sender, password, receiver


def send_notification(job_id: str, status: str, message: str) -> None:
    """Send a build-completion email. Failures are logged, never raised."""
    try:
        sender, password, receiver = _creds()
    except RuntimeError as e:
        print(f"[notifier] skipped: {e}", flush=True)
        return

    subject = f"Build {status.upper()} — {job_id[:8]}"
    body = (
        f"Build Runner Notification\n\n"
        f"Job ID: {job_id}\n"
        f"Status: {status}\n"
        f"Message: {message}\n\n"
        f"---\nBuild Runner System\n"
    )

    msg = MIMEMultipart()
    msg["From"] = sender
    msg["To"] = receiver
    msg["Subject"] = subject
    msg.attach(MIMEText(body, "plain"))

    try:
        with smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=15) as server:
            server.starttls()
            server.login(sender, password)
            server.sendmail(sender, receiver, msg.as_string())
        print(f"[notifier] sent email for job {job_id}", flush=True)
    except Exception as e:
        # Notifications must never crash a build
        print(f"[notifier] email failed for {job_id}: {e}", flush=True)