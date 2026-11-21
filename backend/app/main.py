import os
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException as StarletteHTTPException
from fastapi.responses import JSONResponse

from backend.app.api.data_review import router as data_review_router
from backend.app.api.jobs import router as jobs_router
from backend.app.api.profile import router as profile_router
from backend.app.api.matching import router as matching_router
from backend.app.api.dashboard import router as dashboard_router
from backend.app.api.profile_sessions import router as profile_sessions_router
from backend.app.api.cv import router as cv_router
from backend.app.api.profile_drafts import router as profile_drafts_router
from backend.app.api.resumes import router as resumes_router
from backend.app.api.tasks import router as tasks_router
from backend.app.api.assets import router as assets_router
from backend.app.api.applications import router as applications_router
from backend.app.api.interviews import router as interviews_router
from backend.app.api.assistant import router as assistant_router
from backend.app.db.database import DatabaseUnavailable
from backend.app.core.config import PROJECT_ROOT
from backend.app.api.auth import router as auth_router
from backend.app.api.admin import router as admin_router
from backend.app.core.auth_middleware import AuthMiddleware


@asynccontextmanager
async def lifespan(app):
    from backend.app.db import database
    from backend.app.services.tasks import LocalWorker
    if database.enabled():
        database.migrate()
    from backend.app.services.administration import bootstrap_admin
    from backend.app.services.knowledge import initialize_sources
    bootstrap_admin()
    initialize_sources()
    worker=LocalWorker() if database.enabled() and os.getenv('KLTN_WORKER_ENABLED','1')=='1' else None
    if worker:worker.start()
    try:yield
    finally:
        if worker:worker.stop()


app = FastAPI(title="KLTN Job Search API", version="0.1.0",lifespan=lifespan)
app.add_middleware(AuthMiddleware)
app.include_router(auth_router)
app.include_router(admin_router)
app.include_router(data_review_router)
app.include_router(profile_router)
app.include_router(jobs_router)
app.include_router(matching_router)
app.include_router(dashboard_router)
app.include_router(profile_sessions_router)
app.include_router(cv_router)
app.include_router(profile_drafts_router)
app.include_router(resumes_router)
app.include_router(tasks_router)
app.include_router(assets_router)
app.include_router(applications_router)
app.include_router(interviews_router)
app.include_router(assistant_router)


@app.exception_handler(DatabaseUnavailable)
def database_unavailable(request, error):
    return JSONResponse(status_code=503, content={"detail": str(error)})


@app.get("/health")
def health_check() -> dict[str, str]:
    return {"status": "ok"}


class SPAStaticFiles(StaticFiles):
    async def get_response(self, path, scope):
        try:
            return await super().get_response(path, scope)
        except StarletteHTTPException as error:
            if error.status_code != 404 or path.startswith(("api/", "assets/")) or path in {"api", "health"} or "." in path.rsplit("/", 1)[-1]:
                raise
            return await super().get_response("index.html", scope)


# API routes are registered first; only frontend routes receive the SPA fallback.
frontend_dist = PROJECT_ROOT / "frontend/dist"
if frontend_dist.is_dir():
    app.mount("/", SPAStaticFiles(directory=frontend_dist, html=True), name="frontend")
