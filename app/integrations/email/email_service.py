from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class EmailMessage:
    to_email: str
    subject: str
    text_body: str
    html_body: str | None = None


class EmailService(Protocol):
    async def send_email(self, message: EmailMessage) -> None:
        pass
