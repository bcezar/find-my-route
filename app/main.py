from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from app.config import settings
from app.routers import routes

app = FastAPI(title=settings.app_name)

app.include_router(routes.router, prefix="/api/v1")


@app.get("/health")
async def health():
    return {"status": "ok"}


# Serve the frontend — must come after API routes so /api/v1 takes precedence
app.mount("/", StaticFiles(directory="app/static", html=True), name="static")
