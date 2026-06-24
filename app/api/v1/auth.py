from typing import Annotated

from fastapi import APIRouter, Cookie, Depends, Response, status

from app.api.deps import (
    CurrentUser,
    get_auth_service,
    get_email_verification_service,
    get_oauth_service,
    require_authenticated,
)
from app.core.config import settings
from app.schemas.auth import (
    ChangePasswordRequest,
    EmailVerificationConfirmRequest,
    EmailVerificationConfirmResponse,
    EmailVerificationRequestResponse,
    KakaoOAuthLoginRequest,
    LoginRequest,
    LoginResponse,
    NaverOAuthLoginRequest,
    OAuthCompleteSignupRequest,
    OAuthLoginResponse,
    SignupRequest,
    SignupResponse,
)
from app.services.auth_service import AuthService
from app.services.email_verification_service import EmailVerificationService
from app.services.oauth_service import OAuthService

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


@router.post("/oauth/kakao", response_model=OAuthLoginResponse)
async def kakao_oauth_login(
    payload: KakaoOAuthLoginRequest,
    response: Response,
    oauth_service: Annotated[OAuthService, Depends(get_oauth_service)],
) -> OAuthLoginResponse:
    oauth_response, refresh_token = await oauth_service.login_with_kakao(payload)
    if refresh_token is not None:
        response.set_cookie(
            key=settings.refresh_token_cookie_name,
            value=refresh_token,
            httponly=True,
            secure=settings.refresh_token_cookie_secure,
            samesite="lax",
            max_age=settings.refresh_token_expires_days * 24 * 60 * 60,
            path=get_refresh_token_cookie_path(),
        )
    return oauth_response


@router.post("/oauth/naver", response_model=OAuthLoginResponse)
async def naver_oauth_login(
    payload: NaverOAuthLoginRequest,
    response: Response,
    oauth_service: Annotated[OAuthService, Depends(get_oauth_service)],
) -> OAuthLoginResponse:
    oauth_response, refresh_token = await oauth_service.login_with_naver(payload)
    if refresh_token is not None:
        response.set_cookie(
            key=settings.refresh_token_cookie_name,
            value=refresh_token,
            httponly=True,
            secure=settings.refresh_token_cookie_secure,
            samesite="lax",
            max_age=settings.refresh_token_expires_days * 24 * 60 * 60,
            path=get_refresh_token_cookie_path(),
        )
    return oauth_response


@router.post("/refresh", response_model=LoginResponse)
async def refresh(
    response: Response,
    auth_service: Annotated[AuthService, Depends(get_auth_service)],
    refresh_token: Annotated[str | None, Cookie(alias=settings.refresh_token_cookie_name)] = None,
) -> LoginResponse:
    if refresh_token is None:
        auth_service.raise_invalid_refresh_token()

    refresh_response, new_refresh_token = await auth_service.refresh(refresh_token)
    response.set_cookie(
        key=settings.refresh_token_cookie_name,
        value=new_refresh_token,
        httponly=True,
        secure=settings.refresh_token_cookie_secure,
        samesite="lax",
        max_age=settings.refresh_token_expires_days * 24 * 60 * 60,
        path=get_refresh_token_cookie_path(),
    )
    return refresh_response


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(
    response: Response,
    auth_service: Annotated[AuthService, Depends(get_auth_service)],
    refresh_token: Annotated[str | None, Cookie(alias=settings.refresh_token_cookie_name)] = None,
) -> None:
    if refresh_token is not None:
        await auth_service.logout(refresh_token)

    response.delete_cookie(
        key=settings.refresh_token_cookie_name,
        path=get_refresh_token_cookie_path(),
        secure=settings.refresh_token_cookie_secure,
        httponly=True,
        samesite="lax",
    )


@router.delete("/me", status_code=status.HTTP_204_NO_CONTENT)
async def delete_my_account(
    current_user: Annotated[CurrentUser, Depends(require_authenticated)],
    response: Response,
    auth_service: Annotated[AuthService, Depends(get_auth_service)],
) -> None:
    await auth_service.delete_account(current_user.id)
    response.delete_cookie(
        key=settings.refresh_token_cookie_name,
        path=get_refresh_token_cookie_path(),
        secure=settings.refresh_token_cookie_secure,
        httponly=True,
        samesite="lax",
    )


@router.post("/oauth/complete-signup", response_model=OAuthLoginResponse)
async def complete_oauth_signup(
    payload: OAuthCompleteSignupRequest,
    response: Response,
    oauth_service: Annotated[OAuthService, Depends(get_oauth_service)],
) -> OAuthLoginResponse:
    oauth_response, refresh_token = await oauth_service.complete_signup(payload)
    response.set_cookie(
        key=settings.refresh_token_cookie_name,
        value=refresh_token,
        httponly=True,
        secure=settings.refresh_token_cookie_secure,
        samesite="lax",
        max_age=settings.refresh_token_expires_days * 24 * 60 * 60,
        path=get_refresh_token_cookie_path(),
    )
    return oauth_response


@router.patch("/me/password", status_code=status.HTTP_204_NO_CONTENT)
async def change_password(
    payload: ChangePasswordRequest,
    current_user: Annotated[CurrentUser, Depends(require_authenticated)],
    auth_service: Annotated[AuthService, Depends(get_auth_service)],
) -> None:
    await auth_service.change_password(
        current_user.id,
        current_password=payload.current_password,
        new_password=payload.new_password,
    )


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


@router.post(
    "/email-verification/confirm",
    response_model=EmailVerificationConfirmResponse,
)
async def confirm_email_verification(
    payload: EmailVerificationConfirmRequest,
    email_verification_service: Annotated[
        EmailVerificationService,
        Depends(get_email_verification_service),
    ],
) -> EmailVerificationConfirmResponse:
    result = await email_verification_service.confirm_email_verification(token=payload.token)
    return EmailVerificationConfirmResponse(email_verified_at=result.email_verified_at)
