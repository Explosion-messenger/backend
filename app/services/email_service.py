import aiosmtplib
from email.message import EmailMessage
from ..config import settings
import logging

logger = logging.getLogger(__name__)

async def send_verification_email(email: str, code: str):
    message = EmailMessage()
    message["From"] = settings.SMTP_FROM
    message["To"] = email
    message["Subject"] = "Verify your Messenger account"
    message.set_content(f"Your verification code is: {code}\nIt will expire in {settings.EMAIL_VERIFICATION_EXPIRE_MINUTES} minutes.")

    if not settings.SMTP_USER or not settings.SMTP_PASSWORD:
        logger.warning(f"SMTP credentials not set. Code for {email} is: {code}")
        return

    try:
        await aiosmtplib.send(
            message,
            hostname=settings.SMTP_HOST,
            port=settings.SMTP_PORT,
            username=settings.SMTP_USER,
            password=settings.SMTP_PASSWORD,
            use_tls=settings.SMTP_PORT == 465,
            start_tls=settings.SMTP_PORT == 587 or settings.SMTP_PORT == 2525,
        )
    except Exception as e:
        logger.error(f"Failed to send email to {email}: {e}")
        # In dev, we might still want to see the code even if sending fails
        logger.warning(f"Verification code for {email}: {code}")
