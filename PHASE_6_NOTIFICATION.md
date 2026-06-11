# Phase 6: Email Notifications ✅

## Overview
This phase implements automated email notifications sent to users when a build completes (success or failure). The system integrates Gmail SMTP to send formatted emails with build details after the Docker build process finishes.

---

## Objectives
- ✅ Set up Gmail SMTP configuration
- ✅ Create email notification module
- ✅ Send success notifications
- ✅ Send failure notifications
- ✅ Integrate with worker process
- ✅ Handle SMTP errors

---

## Step 1: Set Up Gmail App Password

Gmail requires app-specific passwords for programmatic access. Follow these steps:

### Step 1a: Enable 2-Factor Authentication

1. Go to [myaccount.google.com](https://myaccount.google.com)
2. Click **Security** in the left menu
3. Enable **2-Step Verification** (if not already enabled)

### Step 1b: Generate App Password

1. Go to [myaccount.google.com/apppasswords](https://myaccount.google.com/apppasswords)
2. Select **App: Mail** and **Device: Windows/Linux/Mac**
3. Click **Generate**
4. Copy the 16-character password
5. Save it securely (we'll use it in Step 3)

**Security Note:** This password is device-specific and can be revoked at any time.

---

## Step 2: Install Required Packages

The `email` and `smtplib` modules are included in Python by default, so no new installation is needed.

Verify:
```bash
python -c "import smtplib, email.mime; print('Email modules available')"
```

---

## Step 3: Create notifier.py

Create a new file `notifier.py`:

```python
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

# Gmail credentials
SENDER_EMAIL = "your-email@gmail.com"          # Change this
APP_PASSWORD = "xxxx xxxx xxxx xxxx"           # 16-char password from Step 1b
RECEIVER_EMAIL = "your-email@gmail.com"        # Change this (can be same or different)

def send_notification(job_id, status, message):
    """
    Send email notification for build completion.
    
    Args:
        job_id (str): Unique job identifier
        status (str): Build status ('success' or 'failed')
        message (str): Build result message
    """
    
    # Step 1: Create email subject and body
    subject = f"Build {status.upper()} — {job_id[:8]}"
    
    body = f"""
Build Runner Notification

Job ID: {job_id}
Status: {status}
Message: {message}

---
Build Runner System
    """

    # Step 2: Create MIME multipart message
    msg = MIMEMultipart()
    msg["From"] = SENDER_EMAIL
    msg["To"] = RECEIVER_EMAIL
    msg["Subject"] = subject
    msg.attach(MIMEText(body, "plain"))

    try:
        # Step 3: Connect to Gmail SMTP server
        server = smtplib.SMTP("smtp.gmail.com", 587)
        
        # Step 4: Start TLS encryption
        server.starttls()
        
        # Step 5: Login with email and app password
        server.login(SENDER_EMAIL, APP_PASSWORD)
        
        # Step 6: Send email
        server.sendmail(SENDER_EMAIL, RECEIVER_EMAIL, msg.as_string())
        
        # Step 7: Close connection
        server.quit()
        
        print(f"✓ Notification sent for job {job_id}")
        
    except smtplib.SMTPAuthenticationError:
        print(f"✗ Email authentication failed. Check credentials.")
    except smtplib.SMTPException as e:
        print(f"✗ SMTP error: {e}")
    except Exception as e:
        print(f"✗ Failed to send notification: {e}")
```

---

## Step 4: Understanding SMTP and Email Basics

### SMTP (Simple Mail Transfer Protocol):

```
┌──────────────┐
│ Your Program │
└──────┬───────┘
       │ Connects to SMTP server
       │ (smtp.gmail.com:587)
       ▼
┌──────────────────────┐
│ Gmail SMTP Server    │
│ (TLS encrypted)      │
└──────┬───────────────┘
       │ Authenticates
       │ (email + password)
       ▼
┌──────────────────────┐
│ Email Sent           │
│ (to recipient)       │
└──────────────────────┘
```

### Email Components:

```
From:    iftakharalamshihad@gmail.com    (sender)
To:      iftakharalamshihad@gmail.com    (recipient)
Subject: Build SUCCESS — 550e8400        (subject line)

Body:
Build Runner Notification

Job ID: 550e8400-e29b-41d4-a716-446655440000
Status: success
Message: Image built: build-runner/550e8400...:latest

---
Build Runner System
```

### MIME (Multipurpose Internet Mail Extension):

```python
# Plain text email
MIMEText(body, "plain")

# HTML email (for future enhancement)
MIMEText(html_body, "html")

# With attachments
msg.attach(MIMEBase("application", "octet-stream"))
```

---

## Step 5: Update worker.py to Send Notifications

Update the imports and `process_job()` function in `worker.py`:

**Add this import at the top:**
```python
from notifier import send_notification
```

**Update the `process_job()` function:**
```python
def process_job(job_id, github_url):
    """
    Main job processing function.
    Orchestrates the entire build workflow.
    """
    update_status(job_id, "running", "Job started")

    # Clone the repository
    clone_dir = clone_repo(job_id, github_url)
    if not clone_dir:
        return

    # Build Docker image from cloned repo
    update_status(job_id, "building", "Docker build started")
    success, result = build_image(job_id, clone_dir)

    # Send notification based on build result
    if success:
        update_status(job_id, "success", f"Image built: {result}")
        # Send success email
        send_notification(job_id, "success", f"Image built: {result}")
    else:
        update_status(job_id, "failed", f"Build failed: {result}")
        # Send failure email
        send_notification(job_id, "failed", f"Build failed: {result}")
```

---

## Step 6: Testing Phase 6

### Prerequisites:
Ensure you have:
- ✅ Gmail account with 2FA enabled
- ✅ App password generated (16-character)
- ✅ Updated SENDER_EMAIL and APP_PASSWORD in notifier.py

### Terminal 1: Start Redis
```bash
redis-server
```

### Terminal 2: Start FastAPI
```bash
uvicorn main:app --reload
```

### Terminal 3: Start Worker
```bash
python worker.py
```

### Terminal 4: Submit Build Job
```bash
curl -X POST "http://localhost:8000/build?github_url=https://github.com/docker/welcome-to-docker"
```

### Expected Output:

**Terminal 3 (Worker):**
```
[550e8400...] Status → running | Job started
[550e8400...] Status → cloning | Cloning https://github.com/docker/welcome-to-docker
[550e8400...] Status → cloned | Repository cloned successfully
[550e8400...] Status → building | Docker build started
[550e8400...] Status → success | Image built: build-runner/550e8400...:latest
✓ Notification sent for job 550e8400...
```

**Gmail Inbox:**
```
From: iftakharalamshihad@gmail.com
To: iftakharalamshihad@gmail.com
Subject: Build SUCCESS — 550e8400

Build Runner Notification

Job ID: 550e8400-e29b-41d4-a716-446655440000
Status: success
Message: Image built: build-runner/550e8400...:latest

---
Build Runner System
```

---

## Step 7: HTML Email Template (Enhancement)

For better email formatting, create an HTML version:

```python
def send_notification_html(job_id, status, message):
    """
    Send HTML formatted email notification.
    """
    subject = f"Build {status.upper()} — {job_id[:8]}"
    
    # HTML template
    html_body = f"""
    <html>
        <body style="font-family: Arial, sans-serif;">
            <h2>Build Runner Notification</h2>
            
            <table style="border-collapse: collapse; width: 100%;">
                <tr>
                    <td style="padding: 10px; background: #f5f5f5;"><strong>Job ID:</strong></td>
                    <td style="padding: 10px;">{job_id}</td>
                </tr>
                <tr>
                    <td style="padding: 10px; background: #f5f5f5;"><strong>Status:</strong></td>
                    <td style="padding: 10px;"><strong>{status.upper()}</strong></td>
                </tr>
                <tr>
                    <td style="padding: 10px; background: #f5f5f5;"><strong>Message:</strong></td>
                    <td style="padding: 10px;">{message}</td>
                </tr>
            </table>
            
            <hr>
            <p style="color: #666; font-size: 12px;">Build Runner System</p>
        </body>
    </html>
    """
    
    msg = MIMEMultipart("alternative")
    msg["From"] = SENDER_EMAIL
    msg["To"] = RECEIVER_EMAIL
    msg["Subject"] = subject
    
    # Attach both plain text and HTML
    msg.attach(MIMEText(f"Job {job_id}: {status}", "plain"))
    msg.attach(MIMEText(html_body, "html"))
    
    # Send via SMTP...
```

---

## Step 8: Gmail Security & Best Practices

### Security Considerations:

1. **Don't commit credentials to Git:**
   ```bash
   # Create .gitignore
   echo "notifier.py" >> .gitignore
   ```

2. **Use environment variables (better practice):**
   ```python
   import os
   
   SENDER_EMAIL = os.getenv("GMAIL_EMAIL")
   APP_PASSWORD = os.getenv("GMAIL_PASSWORD")
   ```

3. **Store credentials in .env file:**
   ```bash
   # Create .env file (add to .gitignore)
   GMAIL_EMAIL=your-email@gmail.com
   GMAIL_PASSWORD=xxxx xxxx xxxx xxxx
   ```

4. **Load from .env:**
   ```bash
   pip install python-dotenv
   ```

   ```python
   from dotenv import load_dotenv
   import os
   
   load_dotenv()
   SENDER_EMAIL = os.getenv("GMAIL_EMAIL")
   APP_PASSWORD = os.getenv("GMAIL_PASSWORD")
   ```

---

## Step 9: SMTP Port and Protocol

### TLS vs SSL:

```python
# TLS (Recommended - Port 587)
server = smtplib.SMTP("smtp.gmail.com", 587)
server.starttls()  # Upgrade to encrypted connection
server.login(email, password)

# SSL (Legacy - Port 465)
server = smtplib.SMTP_SSL("smtp.gmail.com", 465)
server.login(email, password)

# Choose TLS for modern systems
```

### Common SMTP Servers:

| Provider | Server | Port | Auth |
|----------|--------|------|------|
| Gmail | smtp.gmail.com | 587 | App Password |
| Outlook | smtp-mail.outlook.com | 587 | Password |
| Yahoo | smtp.mail.yahoo.com | 587 | App Password |
| AWS SES | email-smtp.region.amazonaws.com | 587 | Access Key |

---

## Step 10: Error Handling Examples

### Scenario 1: Wrong Credentials
```python
# Error: SMTPAuthenticationError
# Solution: Verify app password in notifier.py
```

### Scenario 2: Less Secure Apps Blocked
```python
# Error: SMTP 535 authentication failed
# Solution: Use app password (not regular password)
# Go to: myaccount.google.com/apppasswords
```

### Scenario 3: Network Error
```python
# Error: SMTPServerDisconnected
# Solution: Check internet connection, firewall
```

### Scenario 4: TLS Error
```python
# Error: SSL: CERTIFICATE_VERIFY_FAILED
# Solution: Disable verification (not recommended):
# import ssl
# server.starttls(context=ssl.create_default_context(cafile=None))
```

---

## Step 11: Testing Email Manually

Test notifier independently:

```python
# test_notifier.py
from notifier import send_notification

# Simulate a successful build
send_notification(
    "test-job-12345",
    "success",
    "Image built: build-runner/test-job-12345:latest"
)

# Simulate a failed build
send_notification(
    "test-job-67890",
    "failed",
    "Build failed: Dockerfile not found"
)
```

Run it:
```bash
python test_notifier.py
```

Check your Gmail inbox for emails.

---

## Architecture Overview: Complete Build Pipeline

```
┌─────────────────────────────────────────────────────┐
│ Client                                              │
│ curl -X POST /build?github_url=...                 │
└────────────┬────────────────────────────────────────┘
             │
             ▼
┌─────────────────────────────────────────────────────┐
│ FastAPI Server (main.py)                            │
│ - /build endpoint (creates job, queues)             │
│ - /status endpoint (check status)                   │
│ - /logs endpoint (WebSocket streaming)              │
└────────────┬────────────────────────────────────────┘
             │ (job pushed to queue)
             ▼
┌─────────────────────────────────────────────────────┐
│ Redis Store                                         │
│ - job:{job_id} (stores job data)                    │
│ - build_queue (queue of pending jobs)               │
└────────────┬────────────────────────────────────────┘
             │ (worker pops job)
             ▼
┌─────────────────────────────────────────────────────┐
│ Background Worker (worker.py)                       │
│ - Polls Redis for jobs                              │
│ - Clones GitHub repo                               │
│ - Updates status continuously                       │
└────────────┬────────────────────────────────────────┘
             │
             ├──────────────────────┬──────────────────┐
             │                      │                  │
             ▼                      ▼                  ▼
      ┌──────────┐      ┌──────────────┐    ┌────────────────┐
      │ Git      │      │ Docker       │    │ Email          │
      │ Clone    │      │ Build        │    │ Notification   │
      │ (worker) │      │ (docker_     │    │ (notifier.py)  │
      │          │      │ builder.py)  │    │                │
      │          │      │              │    │ Sends Gmail    │
      └──────────┘      └──────────────┘    │ when done      │
                                            └────────────────┘
```

---

## Summary of Changes

| File | Changes |
|------|---------|
| `notifier.py` | **NEW** - Email notification system |
| `worker.py` | Added `send_notification()` calls on build completion |
| `main.py` | No changes |
| `requirements.txt` | No new packages (uses stdlib) |

---

## Summary

✅ Gmail SMTP configured  
✅ App password generated  
✅ Email sending implemented  
✅ Success notifications working  
✅ Failure notifications working  
✅ Integrated with worker  

---

## Complete Project Structure

```
build-runner-project/
├── venv/                      # Virtual environment
├── main.py                    # FastAPI server
├── worker.py                  # Background worker
├── docker_builder.py          # Docker build logic
├── notifier.py                # Email notifications
├── test_websocket.py          # WebSocket client
├── redis_helper.py            # Redis testing helper
├── requirements.txt           # Dependencies
├── PHASE_1_SETUP.md          # Phase 1 documentation
├── PHASE_2_REDIS_API.md      # Phase 2 documentation
├── PHASE_3_WORKER.md         # Phase 3 documentation
├── PHASE_4_DOCKER_BUILD.md   # Phase 4 documentation
├── PHASE_5_WEBSOCKET.md      # Phase 5 documentation
└── PHASE_6_NOTIFICATION.md   # Phase 6 documentation
```

---

## Complete Workflow Example

### Scenario: Build a Docker Project

```bash
# 1. Start all services
redis-server &
python worker.py &
uvicorn main:app &

# 2. Submit build request
curl -X POST "http://localhost:8000/build?github_url=https://github.com/your-org/your-repo"
# Returns: {"job_id": "abc123...", "status": "queued"}

# 3. Watch progress (WebSocket)
python test_websocket.py
# Enter job_id: abc123...
# Output:
# Status: queued | 
# Status: running | Job started
# Status: cloning | Cloning https://github.com/your-org/your-repo
# Status: cloned | Repository cloned successfully
# Status: building | Docker build started
# Status: success | Image built: build-runner/abc123...:latest
# Job finished!

# 4. Check email inbox
# Receives: "Build SUCCESS — abc123"
# With: Job ID, status, image name

# 5. Verify image created
docker images | grep build-runner
# build-runner/abc123... latest abc123def 5 seconds ago 500MB
```

---

## Troubleshooting

**Issue:** `SMTPAuthenticationError: 535-5.7.8 Username and password not accepted`
- **Solution 1:** Verify app password is correct (16 characters, spaces included)
- **Solution 2:** Generate new app password at myaccount.google.com/apppasswords
- **Solution 3:** Use app password, not regular Gmail password

**Issue:** `SMTPServerDisconnected: Connection unexpectedly closed`
- **Solution:** Check firewall/network, try with `server.starttls()` enabled

**Issue:** `No module named 'smtplib'`
- **Solution:** This is part of Python stdlib, reinstall Python

**Issue:** Email not received
- **Solution:** Check spam/promotions folder, verify recipient email is correct

**Issue:** Connection timeout
- **Solution:** Disable firewall temporarily, check if port 587 is open

---

## Future Enhancements

1. **Email Templates**: Use Jinja2 for HTML templates
2. **Attachments**: Send build logs as PDF attachment
3. **Webhook**: Send build status to Slack/Discord
4. **Multiple Recipients**: Add CC/BCC recipients
5. **Scheduled Emails**: Digest email with daily builds
6. **Database**: Store email delivery history
7. **Retry Logic**: Retry failed emails with exponential backoff

---

## Final Checklist

- ✅ Phase 1: Setup - FastAPI + Uvicorn
- ✅ Phase 2: Redis + API - Job storage + endpoints
- ✅ Phase 3: Worker - Background job processing
- ✅ Phase 4: Docker Build - Image building
- ✅ Phase 5: WebSocket - Real-time streaming
- ✅ Phase 6: Notifications - Email alerts

**Congratulations! Your Build Runner project is complete! 🎉**
