"""
LADX - Email Utility
Sends confirmation and password reset emails via SMTP (Namecheap Private Email).
"""

import smtplib
import secrets
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from config import SMTP_HOST, SMTP_PORT, SMTP_USER, SMTP_PASSWORD, FROM_EMAIL, APP_URL


def generate_token() -> str:
    """Generate a secure random token for email confirmation or password reset."""
    return secrets.token_urlsafe(32)


def _send_email(to_email: str, subject: str, html_body: str) -> bool:
    """Send an email via SMTP. Returns True on success, False on failure."""
    try:
        msg = MIMEMultipart("alternative")
        msg["From"] = f"LADX <{FROM_EMAIL}>"
        msg["To"] = to_email
        msg["Subject"] = subject
        msg.attach(MIMEText(html_body, "html"))

        with smtplib.SMTP_SSL(SMTP_HOST, SMTP_PORT, timeout=10) as server:
            server.login(SMTP_USER, SMTP_PASSWORD)
            server.sendmail(FROM_EMAIL, to_email, msg.as_string())

        print(f"[LADX Email] Sent to {to_email}: {subject}")
        return True
    except Exception as e:
        print(f"[LADX Email] Failed to send to {to_email}: {e}")
        return False


def send_confirmation_email(to_email: str, username: str, token: str) -> bool:
    """Send email confirmation link after signup."""
    confirm_url = f"{APP_URL}/api/auth/confirm/{token}"

    html = f"""
    <div style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; max-width: 500px; margin: 0 auto; padding: 40px 20px;">
        <div style="text-align: center; margin-bottom: 30px;">
            <h1 style="color: #3fbfb7; margin: 0; font-size: 28px;">LADX</h1>
            <p style="color: #888; font-size: 13px; margin-top: 4px;">Your AI Partner for PLC Programming</p>
        </div>
        <div style="background: #1a1d27; border: 1px solid #2d3044; border-radius: 12px; padding: 30px; color: #e4e6ef;">
            <h2 style="margin-top: 0; color: #e4e6ef; font-size: 20px;">Welcome, {username}!</h2>
            <p style="color: #9ca0b0; line-height: 1.6;">
                Thanks for signing up for LADX. Please confirm your email address by clicking the button below.
            </p>
            <div style="text-align: center; margin: 28px 0;">
                <a href="{confirm_url}" style="background: #3fbfb7; color: white; padding: 12px 32px; border-radius: 8px; text-decoration: none; font-weight: 600; font-size: 14px; display: inline-block;">
                    Confirm Email
                </a>
            </div>
            <p style="color: #666; font-size: 12px; margin-bottom: 0;">
                If the button doesn't work, copy and paste this link:<br>
                <span style="color: #3fbfb7; word-break: break-all;">{confirm_url}</span>
            </p>
        </div>
        <p style="color: #666; font-size: 11px; text-align: center; margin-top: 20px;">
            If you didn't create an account on LADX, you can safely ignore this email.
        </p>
    </div>
    """
    return _send_email(to_email, "Confirm your LADX account", html)


def send_password_reset_email(to_email: str, username: str, token: str) -> bool:
    """Send password reset link."""
    reset_url = f"{APP_URL}?reset_token={token}"

    html = f"""
    <div style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; max-width: 500px; margin: 0 auto; padding: 40px 20px;">
        <div style="text-align: center; margin-bottom: 30px;">
            <h1 style="color: #3fbfb7; margin: 0; font-size: 28px;">LADX</h1>
            <p style="color: #888; font-size: 13px; margin-top: 4px;">Your AI Partner for PLC Programming</p>
        </div>
        <div style="background: #1a1d27; border: 1px solid #2d3044; border-radius: 12px; padding: 30px; color: #e4e6ef;">
            <h2 style="margin-top: 0; color: #e4e6ef; font-size: 20px;">Password Reset</h2>
            <p style="color: #9ca0b0; line-height: 1.6;">
                Hi {username}, we received a request to reset your password. Click the button below to set a new password.
            </p>
            <div style="text-align: center; margin: 28px 0;">
                <a href="{reset_url}" style="background: #3fbfb7; color: white; padding: 12px 32px; border-radius: 8px; text-decoration: none; font-weight: 600; font-size: 14px; display: inline-block;">
                    Reset Password
                </a>
            </div>
            <p style="color: #666; font-size: 12px;">
                This link expires in 1 hour. If the button doesn't work, copy and paste this link:<br>
                <span style="color: #3fbfb7; word-break: break-all;">{reset_url}</span>
            </p>
        </div>
        <p style="color: #666; font-size: 11px; text-align: center; margin-top: 20px;">
            If you didn't request a password reset, you can safely ignore this email.
        </p>
    </div>
    """
    return _send_email(to_email, "Reset your LADX password", html)
