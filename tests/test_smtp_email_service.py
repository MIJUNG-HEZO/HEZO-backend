from types import SimpleNamespace
from typing import Any

from app.integrations.email.email_service import EmailMessage
from app.integrations.email.smtp_email_service import SmtpEmailService


class FakeSmtp:
    instances: list["FakeSmtp"] = []

    def __init__(self, host: str, port: int, timeout: int) -> None:
        self.host = host
        self.port = port
        self.timeout = timeout
        self.started_tls = False
        self.tls_context: Any = None
        self.login_username: str | None = None
        self.login_password: str | None = None
        self.sent_message: Any = None
        FakeSmtp.instances.append(self)

    def __enter__(self) -> "FakeSmtp":
        return self

    def __exit__(self, *_: object) -> None:
        return None

    def starttls(self, context: Any = None) -> None:
        self.started_tls = True
        self.tls_context = context

    def login(self, username: str, password: str) -> None:
        self.login_username = username
        self.login_password = password

    def send_message(self, message: Any) -> None:
        self.sent_message = message


def test_smtp_email_service_sends_email(monkeypatch: Any) -> None:
    async def run_send() -> None:
        FakeSmtp.instances.clear()
        monkeypatch.setattr(
            "app.integrations.email.smtp_email_service.smtplib.SMTP",
            FakeSmtp,
        )
        settings = SimpleNamespace(
            smtp_host="smtp.example.com",
            smtp_port=587,
            smtp_username="smtp-user",
            smtp_password="smtp-password",
            smtp_use_tls=True,
            smtp_from_email="no-reply@example.com",
        )
        service = SmtpEmailService(settings)

        await service.send_email(
            EmailMessage(
                to_email="user@example.com",
                subject="인증 메일",
                text_body="인증 링크",
                html_body="<p>인증 링크</p>",
            )
        )

        assert len(FakeSmtp.instances) == 1
        smtp = FakeSmtp.instances[0]
        assert smtp.host == "smtp.example.com"
        assert smtp.port == 587
        assert smtp.timeout == 10
        assert smtp.started_tls is True
        assert smtp.tls_context is not None
        assert smtp.login_username == "smtp-user"
        assert smtp.login_password == "smtp-password"
        assert smtp.sent_message is not None
        assert smtp.sent_message["From"] == "no-reply@example.com"
        assert smtp.sent_message["To"] == "user@example.com"
        assert smtp.sent_message["Subject"] == "인증 메일"

    import asyncio

    asyncio.run(run_send())
