from typing import Annotated

from fastapi import APIRouter, Depends

from app.api.deps import CurrentUser, get_user_service, require_authenticated
from app.schemas.user import UserResponse, UserUpdateRequest
from app.services.user_service import UserService

router = APIRouter(prefix="/users", tags=["Users"])


@router.get("/me", response_model=UserResponse)
async def get_me(
    current_user: Annotated[CurrentUser, Depends(require_authenticated)],
    user_service: Annotated[UserService, Depends(get_user_service)],
) -> UserResponse:
    return await user_service.get_me(user_id=current_user.id)


@router.patch("/me", response_model=UserResponse)
async def update_me(
    payload: UserUpdateRequest,
    current_user: Annotated[CurrentUser, Depends(require_authenticated)],
    user_service: Annotated[UserService, Depends(get_user_service)],
) -> UserResponse:
    return await user_service.update_me(user_id=current_user.id, payload=payload)
