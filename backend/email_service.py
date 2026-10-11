
import os
import smtplib
from email.message import EmailMessage
from urllib.parse import urlencode


def send_auth_email(to_email, subject, message):
    smtp_host = os.getenv("SMTP_HOST", "smtp-relay.brevo.com")
    smtp_port = int(os.getenv("SMTP_PORT", "587"))
    smtp_user = os.getenv("SMTP_USER")
    smtp_password = os.getenv("SMTP_APP_PASSWORD")

    from_email = os.getenv("MAIL_FROM", "achievxlabs@gmail.com")
    from_name = os.getenv("MAIL_FROM_NAME", "AchievX Labs")

    if not smtp_user or not smtp_password:
        raise RuntimeError("Email service is not configured.")

    email = EmailMessage()
    email["Subject"] = subject
    email["From"] = f"{from_name} <{from_email}>"
    email["To"] = to_email
    email.set_content(message)

    with smtplib.SMTP(smtp_host, smtp_port, timeout=30) as server:
        server.ehlo()
        server.starttls()
        server.ehlo()
        server.login(smtp_user, smtp_password)
        server.send_message(email)


def send_verification_email(to_email, token):
    frontend = os.getenv(
        "FRONTEND_URL",
        "https://achievxdashboard.pythonanywhere.com"
    ).rstrip("/")

    link = f"{frontend}/?{urlencode({'verify_token': token})}"

    send_auth_email(
        to_email,
        "Verify your AchievX email",
        f"""Welcome to AchievX!

Please verify your email address using this link:

{link}

This link expires in 24 hours. If you did not create this account,
you can ignore this email.
"""
    )


def send_password_reset_email(to_email, token):
    frontend = os.getenv(
        "FRONTEND_URL",
        "https://achievxdashboard.pythonanywhere.com"
    ).rstrip("/")

    link = f"{frontend}/?{urlencode({'reset_token': token})}"

    send_auth_email(
        to_email,
        "Reset your AchievX password",
        f"""We received a request to reset your AchievX password.

Use this link to continue:

{link}

This link expires in one hour. If you did not request a reset,
you can ignore this email.
"""
    )
