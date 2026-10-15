from fastapi import FastAPI

from backend.app.api.jobs import router as jobs_router
from backend.app.api.profile import router as profile_router


app = FastAPI(title="KLTN Job Search API", version="0.1.0")
app.include_router(profile_router)
app.include_router(jobs_router)


@app.get("/health")
def health_check() -> dict[str, str]:
    return {"status": "ok"}
