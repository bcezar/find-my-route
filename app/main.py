from contextlib import asynccontextmanager
from hashlib import md5
from pathlib import Path
from urllib.parse import urlencode

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from slowapi.errors import RateLimitExceeded
from slowapi import _rate_limit_exceeded_handler

from app import storage
from app.config import settings
from app.i18n import get_strings
from app.limiter import limiter
from app.routers import billing, routes


_STATIC = Path(__file__).parent / "static"
_css_hash = md5(_STATIC.joinpath("style.css").read_bytes()).hexdigest()[:8]
_js_hash  = md5(_STATIC.joinpath("app.js").read_bytes()).hexdigest()[:8]

templates = Jinja2Templates(directory=str(_STATIC))

_i18n = get_strings(settings.locale)
_BASE_URL = settings.app_base_url


@asynccontextmanager
async def lifespan(_: FastAPI):
    await storage.init_db()
    yield


app = FastAPI(title=settings.app_name, lifespan=lifespan)

app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["https://rotaotimizada.com.br", "https://findmyroute.com.br"],
    allow_methods=["GET", "POST", "DELETE"],
    allow_headers=["Content-Type", "Authorization"],
)

app.include_router(routes.router, prefix="/api/v1")
app.include_router(billing.router, prefix="/api/v1")


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


@app.get("/")
async def index(request: Request):
    return templates.TemplateResponse("index.html", {
        "request": request,
        "css_version": _css_hash,
        "js_version": _js_hash,
        "google_maps_key": settings.google_maps_api_key or "",
        "ga_measurement_id": settings.ga_measurement_id or "",
        "base_url": _BASE_URL,
        "i18n": _i18n,
    })


@app.get("/conta")
async def conta(request: Request):
    return templates.TemplateResponse("conta.html", {
        "request": request,
        "css_version": _css_hash,
        "ga_measurement_id": settings.ga_measurement_id or "",
        "i18n": _i18n,
    })


_SEO_PAGES: dict[str, dict[str, str]] = {
    "como-funciona": {
        "title": "Como Funciona o Rota Otimizada — Otimização de Rota com TSP",
        "description": "Entenda como o Rota Otimizada calcula a ordem ideal de visitas usando o algoritmo TSP. Economize tempo e combustível nas suas entregas.",
        "template": "como-funciona.html",
    },
    "importar-enderecos-csv": {
        "title": "Importar Endereços via CSV — Rota Otimizada",
        "description": "Aprenda a importar uma lista de endereços por arquivo CSV ou Excel no Rota Otimizada. Roteirize dezenas de paradas em segundos.",
        "template": "importar-enderecos-csv.html",
    },
    "otimizar-rota-entregas": {
        "title": "Otimizar Rota de Entregas Gratuitamente — Rota Otimizada",
        "description": "Calcule a melhor ordem de entregas com múltiplos endereços. Reduza km rodados, economize combustível e faça mais entregas por dia.",
        "template": "otimizar-rota-entregas.html",
    },
    "roteirizador-gratuito": {
        "title": "Roteirizador Gratuito com Múltiplos Endereços — Rota Otimizada",
        "description": "O melhor roteirizador do Brasil. Grátis até 5 paradas, até 50 no plano Pro. Sem cadastro, sem complicação. Abra direto no Maps.",
        "template": "roteirizador-gratuito.html",
    },
    "google-maps-multiplos-enderecos": {
        "title": "Google Maps com Múltiplos Endereços Otimizados — Rota Otimizada",
        "description": "Supere o limite do Google Maps e otimize a ordem de visitas. O Rota Otimizada calcula a rota ideal e abre automaticamente no Google Maps.",
        "template": "google-maps-multiplos-enderecos.html",
    },
    "waze-multiplos-destinos": {
        "title": "Waze com Múltiplos Destinos Otimizados — Rota Otimizada",
        "description": "Use o Waze com vários destinos em ordem otimizada. O Rota Otimizada organiza suas paradas e abre cada uma diretamente no Waze.",
        "template": "waze-multiplos-destinos.html",
    },
    "perguntas-frequentes": {
        "title": "Perguntas Frequentes — Rota Otimizada",
        "description": "Tire suas dúvidas sobre o Rota Otimizada: como otimizar rotas, importar endereços, usar com Google Maps e Waze, e muito mais.",
        "template": "perguntas-frequentes.html",
    },
}

@app.get("/{slug}")
async def seo_page(request: Request, slug: str):
    # Serve known static files that need to bypass the SEO handler
    if "." in slug:
        static_file = _STATIC / slug
        if static_file.exists() and static_file.is_file():
            return FileResponse(str(static_file))
        raise HTTPException(status_code=404)
    page = _SEO_PAGES.get(slug)
    if not page:
        raise HTTPException(status_code=404)
    return templates.TemplateResponse(page["template"], {
        "request": request,
        "css_version": _css_hash,
        "title": page["title"],
        "description": page["description"],
        "canonical": f"{_BASE_URL}/{slug}",
        "base_url": _BASE_URL,
        "ga_measurement_id": settings.ga_measurement_id or "",
        "i18n": _i18n,
    })


# Serve static assets (CSS, images, etc.) — must come after all routes
app.mount("/", StaticFiles(directory="app/static", html=True), name="static")
