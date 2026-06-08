from dataclasses import dataclass
from typing import Any

import httpx

from app.core import error_codes
from app.core.config import settings
from app.core.exceptions import AppException


@dataclass(frozen=True)
class KakaoUserInfo:
    provider_user_id: str
    email: str | None
    name: str | None


class KakaoOAuthClient:
    token_url = "https://kauth.kakao.com/oauth/token"
    user_info_url = "https://kapi.kakao.com/v2/user/me"

    async def get_user_info_by_code(self, *, code: str, redirect_uri: str) -> KakaoUserInfo:
        access_token = await self.exchange_code_for_access_token(
            code=code,
            redirect_uri=redirect_uri,
        )
        return await self.get_user_info(access_token=access_token)

    async def exchange_code_for_access_token(self, *, code: str, redirect_uri: str) -> str:
        if not settings.kakao_client_id:
            raise AppException(
                code=error_codes.OAUTH_PROVIDER_ERROR,
                message="Kakao OAuth client id is not configured.",
                status_code=500,
            )

        data = {
            "grant_type": "authorization_code",
            "client_id": settings.kakao_client_id,
            "redirect_uri": redirect_uri,
            "code": code,
        }
        if settings.kakao_client_secret:
            data["client_secret"] = settings.kakao_client_secret

        async with httpx.AsyncClient(timeout=5.0) as client:
            response = await client.post(self.token_url, data=data)

        if response.status_code >= 400:
            raise AppException(
                code=error_codes.OAUTH_PROVIDER_ERROR,
                message="Failed to exchange Kakao authorization code.",
                status_code=400 if response.status_code < 500 else 502,
            )

        payload = response.json()
        access_token = payload.get("access_token")
        if not isinstance(access_token, str) or not access_token:
            raise AppException(
                code=error_codes.OAUTH_PROVIDER_ERROR,
                message="Kakao token response is invalid.",
                status_code=502,
            )
        return access_token

    async def get_user_info(self, *, access_token: str) -> KakaoUserInfo:
        headers = {"Authorization": f"Bearer {access_token}"}
        async with httpx.AsyncClient(timeout=5.0) as client:
            response = await client.get(self.user_info_url, headers=headers)

        if response.status_code >= 400:
            raise AppException(
                code=error_codes.OAUTH_PROVIDER_ERROR,
                message="Failed to fetch Kakao user info.",
                status_code=502,
            )

        return self._parse_user_info(response.json())

    def _parse_user_info(self, payload: dict[str, Any]) -> KakaoUserInfo:
        provider_user_id = payload.get("id")
        if not isinstance(provider_user_id, int | str):
            raise AppException(
                code=error_codes.OAUTH_PROVIDER_ERROR,
                message="Kakao user info response is invalid.",
                status_code=502,
            )

        kakao_account = payload.get("kakao_account")
        if not isinstance(kakao_account, dict):
            kakao_account = {}

        profile = kakao_account.get("profile")
        if not isinstance(profile, dict):
            profile = {}

        email = kakao_account.get("email")
        nickname = profile.get("nickname")
        name = kakao_account.get("name") or nickname

        return KakaoUserInfo(
            provider_user_id=str(provider_user_id),
            email=email if isinstance(email, str) else None,
            name=name if isinstance(name, str) else None,
        )
