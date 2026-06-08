from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from hashlib import sha256
from secrets import token_urlsafe
from urllib.parse import urlencode
from uuid import UUID

from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import error_codes
from app.core.config import settings
from app.core.exceptions import AppException
from app.integrations.email.email_service import EmailMessage, EmailService
from app.integrations.email.smtp_email_service import SmtpEmailService
from app.models.email_verification_token import EmailVerificationToken
from app.repositories.email_verification_token_repository import EmailVerificationTokenRepository
from app.repositories.user_repository import UserRepository


@dataclass(frozen=True)
class EmailVerificationRequestResult:
    expires_at: datetime
    verification_url: str | None


@dataclass(frozen=True)
class EmailVerificationConfirmResult:
    email_verified_at: datetime


class EmailVerificationService:
    def __init__(
        self,
        session: AsyncSession,
        user_repository: UserRepository | None = None,
        email_verification_token_repository: EmailVerificationTokenRepository | None = None,
        email_service: EmailService | None = None,
    ) -> None:
        self.session = session
        self.user_repository = user_repository or UserRepository(session)
        self.email_verification_token_repository = (
            email_verification_token_repository or EmailVerificationTokenRepository(session)
        )
        self.email_service = email_service or SmtpEmailService(settings)

    async def request_verification_email(self, *, user_id: UUID) -> EmailVerificationRequestResult:
        user = await self.user_repository.get_by_id_for_update(user_id)
        if user is None or user.deleted_at is not None:
            raise AppException(
                code=error_codes.UNAUTHORIZED,
                message="Authentication is required.",
                status_code=401,
            )
        if user.email_verified_at is not None:
            raise AppException(
                code=error_codes.EMAIL_ALREADY_VERIFIED,
                message="Email is already verified.",
                status_code=409,
            )

        now = datetime.now(UTC)
        token = token_urlsafe(48)
        token_hash = self.hash_token(token)
        expires_at = now + timedelta(minutes=settings.email_verification_token_expires_minutes)

        try:
            await self.email_verification_token_repository.revoke_active_tokens(
                user_id=user.id,
                revoked_at=now,
            )
            email_verification_token = await self.email_verification_token_repository.create(
                user_id=user.id,
                token_hash=token_hash,
                expires_at=expires_at,
            )
            await self.session.commit()
        except SQLAlchemyError:
            await self.session.rollback()
            raise

        verification_url = self.build_verification_url(token)
        try:
            await self.email_service.send_email(
                self.build_verification_email(
                    to_email=user.email,
                    verification_url=verification_url,
                )
            )
        except Exception as exc:
            await self.revoke_failed_delivery_token(email_verification_token)
            raise AppException(
                code=error_codes.EXTERNAL_SERVICE_ERROR,
                message="Email delivery failed.",
                status_code=502,
            ) from exc

        return EmailVerificationRequestResult(
            expires_at=expires_at,
            verification_url=self.build_dev_verification_url(verification_url),
        )

    async def confirm_email_verification(
        self,
        *,
        token: str,
    ) -> EmailVerificationConfirmResult:
        now = datetime.now(UTC)
        token_hash = self.hash_token(token)
        token_snapshot = await self.email_verification_token_repository.get_by_token_hash(
            token_hash
        )
        if token_snapshot is None:
            self.raise_invalid_verification_token()

        user = await self.user_repository.get_by_id_for_update(token_snapshot.user_id)
        if user is None or user.deleted_at is not None:
            self.raise_invalid_verification_token()

        email_verification_token = (
            await self.email_verification_token_repository.get_by_token_hash_for_update(token_hash)
        )
        if (
            email_verification_token is None
            or email_verification_token.user_id != user.id
            or email_verification_token.used_at is not None
            or email_verification_token.revoked_at is not None
            or email_verification_token.expires_at <= now
        ):
            self.raise_invalid_verification_token()

        email_verified_at = user.email_verified_at or now

        try:
            if user.email_verified_at is None:
                await self.user_repository.mark_email_verified(user, verified_at=email_verified_at)
            await self.email_verification_token_repository.mark_used(
                email_verification_token,
                used_at=now,
            )
            await self.session.commit()
        except SQLAlchemyError:
            await self.session.rollback()
            raise

        return EmailVerificationConfirmResult(email_verified_at=email_verified_at)

    def build_verification_email(
        self,
        *,
        to_email: str,
        verification_url: str,
    ) -> EmailMessage:
        return EmailMessage(
            to_email=to_email,
            subject="[HEZO] 이메일 인증을 완료해주세요",
            text_body=(
                "HEZO 이메일 인증을 완료하려면 아래 링크를 열어주세요.\n\n"
                f"{verification_url}\n\n"
                "본인이 요청하지 않았다면 이 메일을 무시해주세요."
            ),
            html_body=(
                "<p>HEZO 이메일 인증을 완료하려면 아래 링크를 열어주세요.</p>"
                f'<p><a href="{verification_url}">이메일 인증하기</a></p>'
                "<p>본인이 요청하지 않았다면 이 메일을 무시해주세요.</p>"
            ),
        )

    def build_verification_url(self, token: str) -> str:
        base_url = settings.frontend_base_url.rstrip("/")
        query = urlencode({"token": token})
        return f"{base_url}/email-verification?{query}"

    def build_dev_verification_url(self, verification_url: str) -> str | None:
        if settings.app_env not in {"local", "dev", "test"}:
            return None
        return verification_url

    async def revoke_failed_delivery_token(
        self,
        email_verification_token: EmailVerificationToken,
    ) -> None:
        try:
            await self.email_verification_token_repository.mark_revoked(
                email_verification_token,
                revoked_at=datetime.now(UTC),
            )
            await self.session.commit()
        except SQLAlchemyError:
            await self.session.rollback()
            raise

    def hash_token(self, token: str) -> str:
        return sha256(token.encode("utf-8")).hexdigest()

    def raise_invalid_verification_token(self) -> None:
        raise AppException(
            code=error_codes.INVALID_EMAIL_VERIFICATION_TOKEN,
            message="Invalid email verification token.",
            status_code=400,
        )
