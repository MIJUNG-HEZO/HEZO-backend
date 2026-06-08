import asyncio
import smtplib
import ssl
from email.message import EmailMessage as SmtpMessage

from app.core.config import Settings
from app.integrations.email.email_service import EmailMessage


class SmtpEmailService:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    async def send_email(self, message: EmailMessage) -> None:
        await asyncio.to_thread(self._send_email, message)

    def _send_email(self, message: EmailMessage) -> None:
        smtp_message = SmtpMessage()
        smtp_message["From"] = self.settings.smtp_from_email
        smtp_message["To"] = message.to_email
        smtp_message["Subject"] = message.subject

        if message.html_body is None:
            smtp_message.set_content(message.text_body)
        else:
            smtp_message.set_content(message.text_body)
            smtp_message.add_alternative(message.html_body, subtype="html")

        with smtplib.SMTP(self.settings.smtp_host, self.settings.smtp_port, timeout=10) as smtp:
            if self.settings.smtp_use_tls:
                smtp.starttls(context=ssl.create_default_context())
            if self.settings.smtp_username or self.settings.smtp_password:
                smtp.login(self.settings.smtp_username, self.settings.smtp_password)
            smtp.send_message(smtp_message)
