from dataclasses import dataclass
from typing import Any

import httpx

from app.core import error_codes
from app.core.config import settings
from app.core.exceptions import AppException


@dataclass(frozen=True)
class NaverUserInfo:
    provider_user_id: str
    email: str | None
    name: str | None


class NaverOAuthClient:
    token_url = "https://nid.naver.com/oauth2.0/token"
    user_info_url = "https://openapi.naver.com/v1/nid/me"

    async def get_user_info_by_code(self, *, code: str, redirect_uri: str) -> NaverUserInfo:
        access_token = await self.exchange_code_for_access_token(
            code=code,
            redirect_uri=redirect_uri,
        )
        return await self.get_user_info(access_token=access_token)

    async def exchange_code_for_access_token(self, *, code: str, redirect_uri: str) -> str:
        if not settings.naver_client_id or not settings.naver_client_secret:
            raise AppException(
                code=error_codes.OAUTH_PROVIDER_ERROR,
                message="Naver OAuth client credentials are not configured.",
                status_code=500,
            )

        params = {
            "grant_type": "authorization_code",
            "client_id": settings.naver_client_id,
            "client_secret": settings.naver_client_secret,
            "code": code,
            "redirect_uri": redirect_uri,
        }

        async with httpx.AsyncClient(timeout=5.0) as client:
            response = await client.post(self.token_url, data=params)

        if response.status_code >= 400:
            raise AppException(
                code=error_codes.OAUTH_PROVIDER_ERROR,
                message="Failed to exchange Naver authorization code.",
                status_code=400 if response.status_code < 500 else 502,
            )

        payload = response.json()
        access_token = payload.get("access_token")
        if not isinstance(access_token, str) or not access_token:
            raise AppException(
                code=error_codes.OAUTH_PROVIDER_ERROR,
                message="Naver token response is invalid.",
                status_code=502,
            )
        return access_token

    async def get_user_info(self, *, access_token: str) -> NaverUserInfo:
        headers = {"Authorization": f"Bearer {access_token}"}
        async with httpx.AsyncClient(timeout=5.0) as client:
            response = await client.get(self.user_info_url, headers=headers)

        if response.status_code >= 400:
            raise AppException(
                code=error_codes.OAUTH_PROVIDER_ERROR,
                message="Failed to fetch Naver user info.",
                status_code=502,
            )

        return self._parse_user_info(response.json())

    def _parse_user_info(self, payload: dict[str, Any]) -> NaverUserInfo:
        response = payload.get("response")
        if not isinstance(response, dict):
            raise AppException(
                code=error_codes.OAUTH_PROVIDER_ERROR,
                message="Naver user info response is invalid.",
                status_code=502,
            )

        provider_user_id = response.get("id")
        if not isinstance(provider_user_id, str) or not provider_user_id:
            raise AppException(
                code=error_codes.OAUTH_PROVIDER_ERROR,
                message="Naver user info response is invalid.",
                status_code=502,
            )

        email = response.get("email")
        name = response.get("name") or response.get("nickname")

        return NaverUserInfo(
            provider_user_id=provider_user_id,
            email=email if isinstance(email, str) else None,
            name=name if isinstance(name, str) else None,
        )
