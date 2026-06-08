from datetime import UTC, datetime

from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import error_codes
from app.core.exceptions import AppException
from app.repositories.plan_repository import PlanRepository
from app.repositories.refresh_token_repository import RefreshTokenRepository
from app.repositories.subscription_repository import SubscriptionRepository
from app.repositories.user_repository import UserRepository
from app.schemas.auth import LoginRequest, LoginResponse, SignupRequest, SignupResponse
from app.services.password_service import PasswordService
from app.services.token_service import TokenService


class AuthService:
    def __init__(
        self,
        session: AsyncSession,
        user_repository: UserRepository | None = None,
        plan_repository: PlanRepository | None = None,
        subscription_repository: SubscriptionRepository | None = None,
        refresh_token_repository: RefreshTokenRepository | None = None,
        password_service: PasswordService | None = None,
        token_service: TokenService | None = None,
    ) -> None:
        self.session = session
        self.user_repository = user_repository or UserRepository(session)
        self.plan_repository = plan_repository or PlanRepository(session)
        self.subscription_repository = subscription_repository or SubscriptionRepository(session)
        self.refresh_token_repository = refresh_token_repository or RefreshTokenRepository(session)
        self.password_service = password_service or PasswordService()
        self.token_service = token_service or TokenService()

    async def signup(self, payload: SignupRequest) -> SignupResponse:
        existing_user = await self.user_repository.get_by_email(payload.email)
        if existing_user is not None:
            raise AppException(
                code=error_codes.EMAIL_ALREADY_EXISTS,
                message="Email already exists.",
                status_code=409,
                details={"email": payload.email},
            )

        password_hash = self.password_service.hash_password(payload.password)

        try:
            user = await self.user_repository.create(
                email=payload.email,
                password_hash=password_hash,
                name=payload.name,
                phone=payload.phone,
            )
        except IntegrityError as exc:
            await self.session.rollback()
            raise AppException(
                code=error_codes.EMAIL_ALREADY_EXISTS,
                message="Email already exists.",
                status_code=409,
                details={"email": payload.email},
            ) from exc

        try:
            free_plan = await self.plan_repository.get_free_plan()
            if free_plan is None:
                await self.session.rollback()
                raise AppException(
                    code=error_codes.PLAN_NOT_FOUND,
                    message="Free plan is not configured.",
                    status_code=500,
                )

            await self.subscription_repository.create_free_subscription(
                user_id=user.id,
                plan_id=free_plan.id,
            )
            await self.session.commit()
            await self.session.refresh(user)
        except SQLAlchemyError:
            await self.session.rollback()
            raise

        return SignupResponse.model_validate(user)

    async def login(self, payload: LoginRequest) -> tuple[LoginResponse, str]:
        user = await self.user_repository.get_by_email(payload.email)
        if (
            user is None
            or user.password_hash is None
            or not self.password_service.verify_password(payload.password, user.password_hash)
        ):
            raise AppException(
                code=error_codes.INVALID_CREDENTIALS,
                message="Invalid email or password.",
                status_code=401,
            )

        access_token = self.token_service.create_access_token(user_id=user.id)
        refresh_token = self.token_service.create_refresh_token()
        refresh_token_hash = self.token_service.hash_refresh_token(refresh_token)
        refresh_token_expires_at = self.token_service.get_refresh_token_expires_at()

        try:
            await self.refresh_token_repository.create(
                user_id=user.id,
                token_hash=refresh_token_hash,
                expires_at=refresh_token_expires_at,
            )
            await self.session.commit()
        except SQLAlchemyError:
            await self.session.rollback()
            raise

        return LoginResponse(access_token=access_token), refresh_token

    async def refresh(self, refresh_token: str) -> tuple[LoginResponse, str]:
        now = datetime.now(UTC)
        refresh_token_hash = self.token_service.hash_refresh_token(refresh_token)
        stored_refresh_token = await self.refresh_token_repository.get_by_token_hash_for_update(
            refresh_token_hash
        )
        if (
            stored_refresh_token is None
            or stored_refresh_token.revoked_at is not None
            or stored_refresh_token.expires_at <= now
        ):
            self.raise_invalid_refresh_token()

        user = await self.user_repository.get_by_id_for_update(stored_refresh_token.user_id)
        if user is None or user.deleted_at is not None:
            self.raise_invalid_refresh_token()

        new_access_token = self.token_service.create_access_token(user_id=user.id)
        new_refresh_token = self.token_service.create_refresh_token()
        new_refresh_token_hash = self.token_service.hash_refresh_token(new_refresh_token)
        new_refresh_token_expires_at = self.token_service.get_refresh_token_expires_at()

        try:
            await self.refresh_token_repository.revoke(stored_refresh_token, revoked_at=now)
            await self.refresh_token_repository.create(
                user_id=user.id,
                token_hash=new_refresh_token_hash,
                expires_at=new_refresh_token_expires_at,
            )
            await self.session.commit()
        except SQLAlchemyError:
            await self.session.rollback()
            raise

        return LoginResponse(access_token=new_access_token), new_refresh_token

    def raise_invalid_refresh_token(self) -> None:
        raise AppException(
            code=error_codes.INVALID_REFRESH_TOKEN,
            message="Invalid refresh token.",
            status_code=401,
        )
