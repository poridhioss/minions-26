import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

# your gmail credentials
SENDER_EMAIL = "iftakharalamshihad@gmail.com"
APP_PASSWORD = "eelh bqxl wpcq dpvs"
RECEIVER_EMAIL = "iftakharalamshihad@gmail.com"

def send_notification(job_id, status, message):
    subject = f"Build {status.upper()} — {job_id[:8]}"
    body = f"""
    Build Runner Notification
    
    Job ID: {job_id}
    Status: {status}
    Message: {message}
    """

    msg = MIMEMultipart()
    msg["From"] = SENDER_EMAIL
    msg["To"] = RECEIVER_EMAIL
    msg["Subject"] = subject
    msg.attach(MIMEText(body, "plain"))

    try:
        # connect to gmail smtp server
        server = smtplib.SMTP("smtp.gmail.com", 587)
        server.starttls()
        server.login(SENDER_EMAIL, APP_PASSWORD)
        server.sendmail(SENDER_EMAIL, RECEIVER_EMAIL, msg.as_string())
        server.quit()
        print(f"Notification sent for job {job_id}")
    except Exception as e:
        print(f"Failed to send notification: {e}")