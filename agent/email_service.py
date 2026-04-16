import os
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

# ENV CONFIG
EMAIL_PROVIDER = os.environ.get("EMAIL_PROVIDER", "gmail")

GMAIL_USER     = os.environ.get("GMAIL_USER", "")
GMAIL_APP_PASS = os.environ.get("GMAIL_APP_PASS", "")
SMTP_HOST      = os.environ.get("SMTP_HOST", "smtp.gmail.com")
SMTP_PORT      = int(os.environ.get("SMTP_PORT", 587))


def send_via_gmail(to_email: str, to_name: str, subject: str, body: str, cc_list: list = None) -> str:
    msg = MIMEMultipart()
    msg["From"] = GMAIL_USER
    msg["To"] = to_email
    msg["Subject"] = subject

    if cc_list:
        cc_emails = [p["email"] for p in cc_list if p.get("email")]
        if cc_emails:
            msg["Cc"] = ", ".join(cc_emails)

    msg.attach(MIMEText(body, "plain"))

    # Build full recipient list (To + CC)
    all_recipients = [to_email]
    if cc_list:
        all_recipients += [p["email"] for p in cc_list if p.get("email")]

    try:
        with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as server:
            server.ehlo()
            server.starttls()
            server.login(GMAIL_USER, GMAIL_APP_PASS)
            server.sendmail(GMAIL_USER, all_recipients, msg.as_string())
        return "sent"
    except Exception as e:
        return f"error:{e}"


def dispatch_email(to_email: str, to_name: str, subject: str, body: str, cc_list: list = None):
    if not to_email:
        return False, "No recipient email address found."

    if not GMAIL_USER or not GMAIL_APP_PASS:
        return False, "GMAIL_USER or GMAIL_APP_PASS is not set."

    result = send_via_gmail(to_email, to_name, subject, body, cc_list)

    if result == "sent":
        return True, f"Email successfully sent to {to_name} ({to_email})"
    else:
        return False, f"Failed to send email: {result}"