from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, status

from app.api.deps import (
    CurrentUser,
    get_site_service,
    require_authenticated,
    require_email_verified,
)
from app.schemas.site import SiteCreateRequest, SiteListResponse, SiteResponse, SiteUpdateRequest
from app.services.site_service import SiteService

router = APIRouter(prefix="/sites", tags=["Sites"])


@router.get("", response_model=SiteListResponse)
async def list_sites(
    current_user: Annotated[CurrentUser, Depends(require_authenticated)],
    site_service: Annotated[SiteService, Depends(get_site_service)],
) -> SiteListResponse:
    return await site_service.list_sites(user_id=current_user.id)


@router.get("/{site_id}", response_model=SiteResponse)
async def get_site(
    site_id: UUID,
    current_user: Annotated[CurrentUser, Depends(require_authenticated)],
    site_service: Annotated[SiteService, Depends(get_site_service)],
) -> SiteResponse:
    return await site_service.get_site(user_id=current_user.id, site_id=site_id)


@router.patch("/{site_id}", response_model=SiteResponse)
async def update_site(
    site_id: UUID,
    payload: SiteUpdateRequest,
    current_user: Annotated[CurrentUser, Depends(require_authenticated)],
    site_service: Annotated[SiteService, Depends(get_site_service)],
) -> SiteResponse:
    return await site_service.update_site(
        user_id=current_user.id,
        site_id=site_id,
        payload=payload,
    )


@router.delete("/{site_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_site(
    site_id: UUID,
    current_user: Annotated[CurrentUser, Depends(require_authenticated)],
    site_service: Annotated[SiteService, Depends(get_site_service)],
) -> None:
    await site_service.delete_site(user_id=current_user.id, site_id=site_id)


@router.post("", response_model=SiteResponse, status_code=status.HTTP_201_CREATED)
async def create_site(
    payload: SiteCreateRequest,
    current_user: Annotated[CurrentUser, Depends(require_email_verified)],
    site_service: Annotated[SiteService, Depends(get_site_service)],
) -> SiteResponse:
    return await site_service.create_site(
        user_id=current_user.id,
        email_verified=current_user.email_verified,
        payload=payload,
    )
