import logging
from sendgrid import SendGridAPIClient
from sendgrid.helpers.mail import Mail, Email, To, Content
from ..config import settings

logger = logging.getLogger(__name__)


class EmailService:
    """Transactional email via SendGrid."""

    def __init__(self):
        self.client = (
            SendGridAPIClient(settings.SENDGRID_API_KEY)
            if settings.SENDGRID_API_KEY
            else None
        )
        self.from_email = settings.FROM_EMAIL

    def send_purchase_confirmation(
        self,
        to_email: str,
        bundle_name: str,
        download_url: str,
        expires_in_hours: int = 24,
    ) -> bool:
        subject = f"Your Babe's Bookstore bundle: {bundle_name}"
        html = f"""
        <html>
        <body style="font-family: sans-serif; max-width: 600px; margin: 0 auto;">
            <h1>Thank you for your purchase!</h1>
            <p>Your bundle <strong>{bundle_name}</strong> is ready to download.</p>
            <p>
                <a href="{download_url}"
                   style="display: inline-block; background: #d97706; color: white;
                          padding: 12px 24px; text-decoration: none; border-radius: 6px;">
                    Download Your Bundle
                </a>
            </p>
            <p><small>This link expires in {expires_in_hours} hours.</small></p>
            <p>Need to re-download? Visit your account page anytime.</p>
            <hr>
            <p style="color: #666; font-size: 12px;">
                Babe's Bookstore — Public domain and openly-licensed books, curated for you.
            </p>
        </body>
        </html>
        """
        return self._send(to_email, subject, html)

    def _send(self, to_email: str, subject: str, html: str) -> bool:
        if not self.client:
            logger.warning(f"Email not configured. Would send: {subject} to {to_email}")
            return False
        try:
            message = Mail(
                from_email=Email(self.from_email),
                to_emails=To(to_email),
                subject=subject,
                html_content=Content("text/html", html),
            )
            response = self.client.send(message)
            return response.status_code in (200, 201, 202)
        except Exception as e:
            logger.error(f"Email send failed: {e}")
            return False


email_service = EmailService()