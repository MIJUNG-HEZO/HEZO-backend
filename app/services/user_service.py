from uuid import UUID

from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import error_codes
from app.core.exceptions import AppException
from app.models.user import User
from app.repositories.user_repository import UserRepository
from app.schemas.user import UserModelResponse, UserResponse, UserUpdateRequest


class UserService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.user_repository = UserRepository(session)

    async def get_me(self, *, user_id: UUID) -> UserResponse:
        user = await self.user_repository.get_by_id(user_id)
        if user is None or user.deleted_at is not None:
            raise AppException(
                code=error_codes.USER_NOT_FOUND,
                message="User was not found.",
                status_code=404,
            )

        return self._to_response(user)

    async def update_me(self, *, user_id: UUID, payload: UserUpdateRequest) -> UserResponse:
        user = await self.user_repository.get_by_id_for_update(user_id)
        if user is None or user.deleted_at is not None:
            raise AppException(
                code=error_codes.USER_NOT_FOUND,
                message="User was not found.",
                status_code=404,
            )

        try:
            updated_user = await self.user_repository.update_profile(
                user=user,
                name=payload.name if payload.name is not None else user.name,
                phone=payload.phone if "phone" in payload.model_fields_set else user.phone,
            )
            await self.session.commit()
            await self.session.refresh(updated_user)
        except SQLAlchemyError:
            await self.session.rollback()
            raise

        return self._to_response(updated_user)

    def _to_response(self, user: User) -> UserResponse:
        model = UserModelResponse.model_validate(user)
        return UserResponse(
            id=model.id,
            email=model.email,
            name=model.name,
            phone=model.phone,
            email_verified_at=model.email_verified_at,
            email_verified=model.email_verified_at is not None,
            created_at=model.created_at,
            updated_at=model.updated_at,
        )
