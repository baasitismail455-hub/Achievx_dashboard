
import json
import os
import urllib.error
import urllib.request
from urllib.parse import urlencode


BREVO_API_URL = "https://api.brevo.com/v3/smtp/email"


def send_auth_email(to_email, subject, html_content, text_content):
    api_key = os.getenv("BREVO_API_KEY")
    sender_email = os.getenv("MAIL_FROM", "achievxlabs@gmail.com")
    sender_name = os.getenv("MAIL_FROM_NAME", "AchievX Labs")

    if not api_key:
        raise RuntimeError("BREVO_API_KEY is not configured.")

    payload = {
        "sender": {
            "name": sender_name,
            "email": sender_email,
        },
        "to": [{"email": to_email}],
        "subject": subject,
        "htmlContent": html_content,
        "textContent": text_content,
    }

    request = urllib.request.Request(
        BREVO_API_URL,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "accept": "application/json",
            "api-key": api_key,
            "content-type": "application/json",
        },
        method="POST",
    )

    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            if response.status not in (200, 201, 202):
                raise RuntimeError(
                    f"Brevo email request failed with status {response.status}."
                )
    except urllib.error.HTTPError as exc:
        # Do not log the API key or other secrets.
        try:
            detail = exc.read().decode("utf-8", errors="replace")
        except Exception:
            detail = "No response details."
        raise RuntimeError(
            f"Brevo API returned HTTP {exc.code}: {detail[:500]}"
        ) from None
    except (urllib.error.URLError, TimeoutError) as exc:
        raise RuntimeError(
            f"Could not connect to the Brevo API: {exc}"
        ) from None


def send_verification_email(to_email, token):
    frontend_url = os.getenv(
        "FRONTEND_URL",
        "https://achievxdashboard.pythonanywhere.com",
    ).rstrip("/")

    query = urlencode({"verify_token": token})
    verification_url = f"{frontend_url}/?{query}"

    subject = "Verify your AchievX email address"

    text_content = (
        "Welcome to AchievX!\n\n"
        "Please verify your email address using this link:\n"
        f"{verification_url}\n\n"
        "If you did not create an AchievX account, you can ignore this email."
    )

    html_content = f"""
    <div style="font-family:Arial,sans-serif;line-height:1.6;color:#222">
      <h2>Welcome to AchievX</h2>
      <p>Please verify your email address to complete your registration.</p>
      <p>
        <a href="{verification_url}"
           style="display:inline-block;padding:12px 20px;background:#111;
                  color:#fff;text-decoration:none;border-radius:6px">
          Verify email address
        </a>
      </p>
      <p>If the button doesn't work, copy this link into your browser:</p>
      <p>{verification_url}</p>
      <p>If you did not create an AchievX account, you can ignore this email.</p>
    </div>
    """

    send_auth_email(to_email, subject, html_content, text_content)


def send_password_reset_email(to_email, token):
    frontend_url = os.getenv(
        "FRONTEND_URL",
        "https://achievxdashboard.pythonanywhere.com",
    ).rstrip("/")

    query = urlencode({"reset_token": token})
    reset_url = f"{frontend_url}/?{query}"

    subject = "Reset your AchievX password"

    text_content = (
        "We received a request to reset your AchievX password.\n\n"
        "Use this link to choose a new password:\n"
        f"{reset_url}\n\n"
        "If you did not request a password reset, you can ignore this email."
    )

    html_content = f"""
    <div style="font-family:Arial,sans-serif;line-height:1.6;color:#222">
      <h2>Reset your AchievX password</h2>
      <p>We received a request to reset your password.</p>
      <p>
        <a href="{reset_url}"
           style="display:inline-block;padding:12px 20px;background:#111;
                  color:#fff;text-decoration:none;border-radius:6px">
          Reset password
        </a>
      </p>
      <p>If the button doesn't work, copy this link into your browser:</p>
      <p>{reset_url}</p>
      <p>If you did not request this, you can ignore this email.</p>
    </div>
    """

    send_auth_email(to_email, subject, html_content, text_content)
