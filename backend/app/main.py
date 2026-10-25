from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import JSONResponse

from backend.app.api.jobs import router as jobs_router
from backend.app.api.profile import router as profile_router
from backend.app.api.matching import router as matching_router
from backend.app.api.dashboard import router as dashboard_router
from backend.app.api.profile_sessions import router as profile_sessions_router
from backend.app.api.cv import router as cv_router
from backend.app.db.database import DatabaseUnavailable
from backend.app.core.config import PROJECT_ROOT


app = FastAPI(title="KLTN Job Search API", version="0.1.0")
app.include_router(profile_router)
app.include_router(jobs_router)
app.include_router(matching_router)
app.include_router(dashboard_router)
app.include_router(profile_sessions_router)
app.include_router(cv_router)


@app.exception_handler(DatabaseUnavailable)
def database_unavailable(request, error):
    return JSONResponse(status_code=503, content={"detail": str(error)})


@app.get("/health")
def health_check() -> dict[str, str]:
    return {"status": "ok"}


# API routes are registered first. The day-1 UI uses only the root URL.
frontend_dist = PROJECT_ROOT / "frontend/dist"
if frontend_dist.is_dir():
    app.mount("/", StaticFiles(directory=frontend_dist, html=True), name="frontend")
