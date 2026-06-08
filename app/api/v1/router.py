from fastapi import APIRouter

from app.api.v1.auth import router as auth_router
from app.api.v1.billing import router as billing_router
from app.api.v1.health import router as health_router
from app.api.v1.plans import router as plans_router
from app.api.v1.sites import router as sites_router
from app.api.v1.subscriptions import router as subscriptions_router

api_router = APIRouter()
api_router.include_router(auth_router)
api_router.include_router(billing_router)
api_router.include_router(health_router)
api_router.include_router(plans_router)
api_router.include_router(sites_router)
api_router.include_router(subscriptions_router)
