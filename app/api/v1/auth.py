from typing import Annotated

from fastapi import APIRouter, Depends, Response, status

from app.api.deps import get_auth_service
from app.core.config import settings
from app.schemas.auth import LoginRequest, LoginResponse, SignupRequest, SignupResponse
from app.services.auth_service import AuthService

router = APIRouter(prefix="/auth", tags=["Auth"])


@router.post("/signup", response_model=SignupResponse, status_code=status.HTTP_201_CREATED)
async def signup(
    payload: SignupRequest,
    auth_service: Annotated[AuthService, Depends(get_auth_service)],
) -> SignupResponse:
    return await auth_service.signup(payload)


@router.post("/login", response_model=LoginResponse)
async def login(
    payload: LoginRequest,
    response: Response,
    auth_service: Annotated[AuthService, Depends(get_auth_service)],
) -> LoginResponse:
    login_response, refresh_token = await auth_service.login(payload)
    response.set_cookie(
        key=settings.refresh_token_cookie_name,
        value=refresh_token,
        httponly=True,
        secure=settings.refresh_token_cookie_secure,
        samesite="lax",
        max_age=settings.refresh_token_expires_days * 24 * 60 * 60,
        path="/api/v1/auth",
    )
    return login_response
