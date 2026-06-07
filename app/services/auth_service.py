from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import error_codes
from app.core.exceptions import AppException
from app.repositories.refresh_token_repository import RefreshTokenRepository
from app.repositories.user_repository import UserRepository
from app.schemas.auth import LoginRequest, LoginResponse, SignupRequest, SignupResponse
from app.services.password_service import PasswordService
from app.services.token_service import TokenService


class AuthService:
    def __init__(
        self,
        session: AsyncSession,
        user_repository: UserRepository | None = None,
        refresh_token_repository: RefreshTokenRepository | None = None,
        password_service: PasswordService | None = None,
        token_service: TokenService | None = None,
    ) -> None:
        self.session = session
        self.user_repository = user_repository or UserRepository(session)
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
            await self.session.commit()
            await self.session.refresh(user)
        except IntegrityError as exc:
            await self.session.rollback()
            raise AppException(
                code=error_codes.EMAIL_ALREADY_EXISTS,
                message="Email already exists.",
                status_code=409,
                details={"email": payload.email},
            ) from exc
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
