from fastapi import APIRouter, Depends

from app.api import admin, applications, auth, billing, files, health, jobs, matches, me, misc, profile, resumes
from app.core.config import get_settings
from app.core.ratelimit import rate_limit

api_router = APIRouter(prefix="/api", dependencies=[Depends(rate_limit("api", get_settings().rate_limit_default_per_minute))])
api_router.include_router(health.router)
api_router.include_router(auth.router)
api_router.include_router(me.router)
api_router.include_router(profile.router)
api_router.include_router(resumes.router)
api_router.include_router(jobs.router)
api_router.include_router(matches.router)
api_router.include_router(applications.router)
api_router.include_router(billing.router)
api_router.include_router(misc.router)
api_router.include_router(admin.router)
api_router.include_router(files.router)
