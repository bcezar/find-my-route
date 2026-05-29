from contextlib import asynccontextmanager
from urllib.parse import urlencode

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
from slowapi.errors import RateLimitExceeded
from slowapi import _rate_limit_exceeded_handler

from app import storage
from app.config import settings
from app.limiter import limiter
from app.routers import routes


@asynccontextmanager
async def lifespan(_: FastAPI):
    await storage.init_db()
    yield


app = FastAPI(title=settings.app_name, lifespan=lifespan)

app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["https://rotas.casapetcampinas.com.br"],
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type"],
)

app.include_router(routes.router, prefix="/api/v1")


@app.get("/health")
async def health():
    return {"status": "ok"}


@app.get("/s/{code}")
async def expand_saved_route(code: str):
    return RedirectResponse(url=f"/?saved={code}", status_code=302)


@app.get("/r/{code}")
async def expand_route(code: str):
    state = await storage.get_route(code)
    if not state:
        return RedirectResponse(url="/?expired=1", status_code=302)
    parts = []
    if state.get("origin"):      parts.append(("origin", state["origin"]))
    if state.get("destination"): parts.append(("dest",   state["destination"]))
    for a in state.get("addresses", []):
        parts.append(("a", a))
    return RedirectResponse(url=f"/?{urlencode(parts)}", status_code=302)


# Serve the frontend — must come after API routes so /api/v1 takes precedence
app.mount("/", StaticFiles(directory="app/static", html=True), name="static")
