from urllib.parse import urlencode

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
from slowapi.errors import RateLimitExceeded
from slowapi import _rate_limit_exceeded_handler

from app import storage
from app.config import settings
from app.limiter import limiter
from app.routers import routes

app = FastAPI(title=settings.app_name)

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


@app.get("/r/{code}")
async def expand_route(code: str):
    state = storage.get_route(code)
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
