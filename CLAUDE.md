# find-my-route

API REST de roteirização de endereços com frontend web completo. Recebe uma lista de endereços, geocodifica, calcula distâncias reais de estrada e retorna a ordem de visita otimizada (TSP).

## Stack

- **Python 3.9** (macOS system python — usar `from __future__ import annotations` em todo arquivo que use `X | Y` ou `list[...]` em annotations, pois o Pydantic avalia em runtime)
- **FastAPI** + **Uvicorn**
- **OR-Tools** (Google) — solver TSP com GLS metaheuristic
- **httpx** — HTTP client async
- **slowapi** — rate limiting por IP
- **Alpine.js v3** — frontend reativo (CDN, sem build step)
- **Geocoding:** Google Maps API quando `GOOGLE_MAPS_API_KEY` estiver no `.env`; fallback para Nominatim (OSM)
- **Distâncias:** OSRM Table API quando `OSRM_BASE_URL` configurado; fallback para Haversine

## Comandos

```bash
# Instalar dependências (primeira vez)
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt

# Rodar servidor
.venv/bin/uvicorn app.main:app --reload

# Rodar testes
.venv/bin/pytest -v   # 27 testes passando
```

## Estrutura

```
app/
├── main.py               # FastAPI app; GET /health + GET /r/{code} (short link redirect)
├── config.py             # Settings via .env (pydantic-settings)
├── limiter.py            # Instância do slowapi Limiter (separado para evitar circular import)
├── storage.py            # Dict em memória para short links (/r/{code})
├── models.py             # RouteRequest, RouteResponse, RouteStop (com leg_distance_km), etc.
├── routers/
│   └── routes.py         # Todos os endpoints /api/v1/*
└── services/
    ├── geocoding.py      # Google Maps / Nominatim + cache + autocomplete + reverse geocoding
    ├── distance.py       # OSRM Table API (fallback: Haversine)
    └── optimizer.py      # OR-Tools TSP solver (PATH_CHEAPEST_ARC + GLS)
static/
    ├── index.html        # Frontend Alpine.js completo
    ├── capa.png          # Imagem OG para preview no WhatsApp
    ├── icon-find-my-route.png
    └── my-location.svg   # Ícone do botão de geolocalização
tests/
├── test_routes.py        # Testes dos endpoints (mock geocoding.geocode_all)
├── test_geocoding.py     # Testes do service de geocoding
├── test_distance.py      # Testes Haversine + OSRM mock
└── test_optimizer.py     # Testes OR-Tools
```

## Endpoints

```
GET  /health
GET  /r/{code}                   → redirect 302 para /?origin=...&a=... (short link)

GET  /api/v1/autocomplete?q=     → Google Places autocomplete (rate: 120/min)
GET  /api/v1/reverse?lat=&lng=   → reverse geocoding para geolocalização (rate: 30/min)
POST /api/v1/shorten             → gera short link, body=RouteRequest (rate: 20/min)
POST /api/v1/routes/optimize     → otimiza rota, body=RouteRequest (rate: 20/min)
```

## Modelos principais

### `RouteRequest`
```python
addresses: list[Address]       # min 2, max 50; Address = Annotated[str, max_length=200]
origin:      Optional[Address] # ponto de partida fixo
destination: Optional[Address] # ponto de chegada fixo (pode == origin para ciclo)
```

### `RouteStop` (dentro de `RouteResponse.optimized_route`)
```python
order: int
original_address: str
coordinates: Coordinates        # {lat, lng}
leg_distance_km: Optional[float] # distância até a próxima parada (None na última)
```

## Frontend (`app/static/index.html`)

Alpine.js v3, sem build step, single-page:

- **Persistência:** localStorage salva origin, dest, addresses entre sessões
- **Autocomplete:** Google Places, debounce 400ms, em todos os inputs
- **Geolocalização:** botão ⊕ chama `/api/v1/reverse`, auto-confirma a origem; só ícone no mobile (≤480px)
- **Resultado:** badges 0 (origem), 1-N (paradas), F (destino); distância por trecho ↓ X km; link Google Maps
- **Copiar rota:** texto formatado com assinatura `findmyroute.com.br`
- **Compartilhar rota / Copiar link:** chama `/api/v1/shorten` → URL curta `/r/CODE`; `navigator.share()` no mobile, clipboard no desktop; inclui mensagem contextual
- **Limpar tudo:** reseta estado + localStorage
- **Destino:** botão "← Usar mesmo endereço da origem" (aparece quando origem está definida)
- **URL params:** `?origin=&dest=&a=` pré-preenche o formulário (usado pelo redirect de short links)

## Segurança

- **CORS:** restrito ao domínio de produção (`rotas.casapetcampinas.com.br` → migrar para `findmyroute.com.br`)
- **Rate limiting:** slowapi por IP no código + Cloudflare Rate Limiting no painel (proteção dupla)
- **Validação:** `Address` com `max_length=200`, addresses com `min_length=2, max_length=50`

## Deploy

- **Railway** (Python) — auto-deploy via GitHub push
- `Procfile`: `web: uvicorn app.main:app --host 0.0.0.0 --port $PORT`
- **Cloudflare** — DNS proxy + Rate Limiting configurado no painel
- **Domínio atual:** `rotas.casapetcampinas.com.br` → **futuro:** `findmyroute.com.br`

## Variáveis de ambiente (`.env`)

```
GOOGLE_MAPS_API_KEY=     # obrigatório para autocomplete, reverse geocoding e geocoding de qualidade
NOMINATIM_USER_AGENT=find-my-route/1.0
NOMINATIM_BASE_URL=https://nominatim.openstreetmap.org
TSP_TIMEOUT_SECONDS=5
MAX_ADDRESSES=50
OSRM_BASE_URL=           # opcional; sem isso usa Haversine
```

> **Nunca commitar o `.env`** — contém a API key do Google Maps.

## Decisões técnicas relevantes

- **`from __future__ import annotations` + Pydantic:** Não usar em arquivos que usem `Body(...)` como parâmetro — causa `ForwardRef` não resolvido em runtime. Em `routes.py` usar `Optional[X]` diretamente.
- **`app/limiter.py` separado:** Evita circular import entre `main.py` e `routes.py`.
- **Short links em memória (`storage.py`):** Links expiram no próximo deploy. Aceitável — usuário gera novo link se precisar.
- **Geocoding paralelo:** Google Maps usa `asyncio.gather`; Nominatim é sequencial com `sleep(1s)` (usage policy).
- **OR-Tools endpoint fixo:** Quando `origin == destination` (retorno ao depósito), o nó é duplicado nas coordenadas para que OR-Tools trate como índices distintos.
- **`leg_distance_km`:** Calculado direto da matriz em memória — sem custo extra de I/O.
- **Geolocalização mobile:** Botão ⊕ só com SVG em telas ≤480px (`.btn-geo-text { display: none }`).

## Próximos passos

- [x] Distâncias reais de estrada (OSRM)
- [x] Frontend Alpine.js completo
- [x] Rate limiting (slowapi + Cloudflare)
- [x] Autocomplete Google Places
- [x] Geolocalização com reverse geocoding
- [x] Short links para compartilhamento (`/r/{code}`)
- [x] Distância por trecho no resultado (`leg_distance_km`)
- [ ] **Migração de domínio** para `findmyroute.com.br` — atualizar CORS em `main.py`, URLs OG em `index.html`, textos de assinatura
- [ ] Cache persistente de geocoding (Redis ou SQLite)
- [ ] `GET /api/v1/routes/{id}` para consultar resultado de rota salva
