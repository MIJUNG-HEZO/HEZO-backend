from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import error_codes
from app.core.exceptions import AppException
from app.repositories.user_repository import UserRepository
from app.schemas.auth import SignupRequest, SignupResponse
from app.services.password_service import PasswordService


class AuthService:
    def __init__(
        self,
        session: AsyncSession,
        user_repository: UserRepository | None = None,
        password_service: PasswordService | None = None,
    ) -> None:
        self.session = session
        self.user_repository = user_repository or UserRepository(session)
        self.password_service = password_service or PasswordService()

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
