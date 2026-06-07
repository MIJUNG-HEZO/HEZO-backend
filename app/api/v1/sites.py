from typing import Annotated

from fastapi import APIRouter, Depends, status

from app.api.deps import CurrentUser, get_site_service, require_email_verified
from app.schemas.site import SiteCreateRequest, SiteResponse
from app.services.site_service import SiteService

router = APIRouter(prefix="/sites", tags=["Sites"])


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
