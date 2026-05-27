from fastapi import FastAPI

from app.config import settings
from app.routers import routes

app = FastAPI(title=settings.app_name)

app.include_router(routes.router, prefix="/api/v1")


@app.get("/health")
async def health():
    return {"status": "ok"}
