from typing import Annotated

from fastapi import APIRouter, Depends, Response, status

from app.api.deps import (
    CurrentUser,
    get_auth_service,
    get_email_verification_service,
    require_authenticated,
)
from app.core.config import settings
from app.schemas.auth import (
    EmailVerificationRequestResponse,
    LoginRequest,
    LoginResponse,
    SignupRequest,
    SignupResponse,
)
from app.services.auth_service import AuthService
from app.services.email_verification_service import EmailVerificationService

router = APIRouter(prefix="/auth", tags=["Auth"])


def get_refresh_token_cookie_path() -> str:
    return f"{settings.api_v1_prefix.rstrip('/')}/auth"


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
        path=get_refresh_token_cookie_path(),
    )
    return login_response


@router.post(
    "/email-verification/request",
    response_model=EmailVerificationRequestResponse,
)
async def request_email_verification(
    current_user: Annotated[CurrentUser, Depends(require_authenticated)],
    email_verification_service: Annotated[
        EmailVerificationService,
        Depends(get_email_verification_service),
    ],
) -> EmailVerificationRequestResponse:
    result = await email_verification_service.request_verification_email(user_id=current_user.id)
    return EmailVerificationRequestResponse(
        expires_at=result.expires_at,
        verification_url=result.verification_url,
    )
