# rota-otimizada

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
- **i18n:** `app/i18n.py` — dicionário PT/EN; injetado via Jinja2 como `{{ i18n.* }}` e `window.I18N` no JS

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
├── main.py               # FastAPI app; monta static, templates Jinja2, GET /r/{code}, /s/{code}
├── config.py             # Settings via .env (pydantic-settings)
├── i18n.py               # Dicionários de strings PT/EN por locale
├── limiter.py            # Instância do slowapi Limiter (separado para evitar circular import)
├── storage.py            # Turso (libSQL) via HTTP + fallback em memória; short links, rotas salvas, users, sessions
├── models.py             # RouteRequest, RouteResponse, RouteStop, SaveRouteRequest, etc.
├── routers/
│   └── routes.py         # Todos os endpoints /api/v1/*
└── services/
    ├── geocoding.py      # Google Maps / Nominatim + cache + autocomplete + reverse geocoding
    ├── distance.py       # OSRM Table API (fallback: Haversine)
    ├── directions.py     # Polyline de rota real (OSRM/Directions)
    ├── static_maps.py    # Google Static Maps API — imagem do mini-mapa
    └── optimizer.py      # OR-Tools TSP solver (PATH_CHEAPEST_ARC + GLS)
static/
    ├── index.html        # Frontend Alpine.js completo (~940 linhas)
    ├── app.js            # Lógica Alpine.js (~700 linhas)
    ├── style.css         # Estilos (~840 linhas)
    ├── capa.png          # Imagem OG/WhatsApp (og:image, twitter:image)
    ├── logo-find-my-route.png
    ├── icon-find-my-route.png
    └── my-location.svg   # Ícone do botão de geolocalização
tests/
├── test_routes.py        # Testes dos endpoints (mock geocoding.geocode_all)
├── test_geocoding.py     # Testes do service de geocoding
├── test_distance.py      # Testes Haversine + OSRM mock
└── test_optimizer.py     # Testes OR-Tools
```

### Páginas SEO

Servidas por rotas FastAPI usando templates Jinja2 com strings i18n. Os slugs diferem por locale:

- PT (`rotaotimizada.com.br`): `/como-funciona`, `/importar-enderecos-csv`, `/otimizar-rota-entregas`, `/roteirizador-gratuito`, `/google-maps-multiplos-enderecos`, `/waze-multiplos-destinos`, `/perguntas-frequentes`
- EN (`findmyroute.com.br`): `/how-it-works`, `/import-addresses-csv`, `/optimize-delivery-route`, `/free-route-planner`, `/google-maps-multiple-addresses`, `/waze-multiple-destinations`, `/faq`

## Endpoints

```
GET  /health
GET  /r/{code}                      → redirect 302 para /?origin=...&a=... (short link compartilhamento)
GET  /s/{code}                      → redirect 302 para /?saved={code} (rota salva)

# Geocoding
GET  /api/v1/autocomplete?q=        → Google Places autocomplete (rate: 120/min)
GET  /api/v1/geocode?q=             → geocodifica endereço único; retorna {lat, lng} (rate: 30/min)
GET  /api/v1/reverse?lat=&lng=      → reverse geocoding para geolocalização (rate: 30/min)

# Rota
POST /api/v1/shorten                → gera short link, body=RouteRequest (rate: 20/min)
POST /api/v1/routes/optimize        → otimiza rota, body=RouteRequest (rate: 20/min)
POST /api/v1/routes/polyline        → retorna polyline de estrada real entre os pontos (rate: 30/min)
POST /api/v1/routes/map-image       → retorna PNG do Google Static Maps (rate: 20/min)

# Rotas salvas (requer autenticação Bearer)
POST /api/v1/routes/save            → salva rota com nome; retorna {code, path} (rate: 20/min)
GET  /api/v1/routes/my-routes       → lista rotas salvas do usuário autenticado (rate: 30/min)
GET  /api/v1/routes/saved/{code}    → retorna resultado de rota salva (público, sem auth)
DELETE /api/v1/routes/saved/{code}  → exclui rota salva (requer auth; valida user_id) (rate: 20/min)

# Auth (magic link / token simples)
POST /api/v1/auth/login             → find_or_create_user por e-mail; retorna {token, user} (rate: 10/min)
GET  /api/v1/auth/me                → retorna usuário autenticado
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

## Frontend (`app/static/index.html` + `app.js`)

Alpine.js v3, sem build step, single-page. Lógica em `app.js`, markup em `index.html`, estilos em `style.css`.

- **Persistência:** localStorage salva origin, dest, addresses, fixedFirst, fixedLast entre sessões
- **Autocomplete:** Google Places, debounce 400ms, em todos os inputs; `locationHint` (lat/lng) para boas sugestões
- **Geolocalização:** botão chama `/api/v1/reverse`, auto-confirma a origem; texto oculto no mobile (≤480px)
- **Paradas:** lista com accordion (5 visíveis, expand/collapse com animação `max-height`); busca inline; por parada: editar, excluir, definir como primeiro/último destino
- **Importar endereços:** modal 2 passos — (1) dropzone CSV/XLSX, (2) preview com contagem + botões "Adicionar" / "Substituir"; parser CSV vanilla (auto-detect `,`/`;`); XLSX via SheetJS lazy-loaded do CDN
- **Exportar paradas:** baixa `enderecos.csv` com colunas `endereco,descricao`; template também disponível
- **Resultado:** mini-mapa SVG (fallback) + imagem Google Static Maps; timeline com badges 0/1-N/F; distância e tempo por trecho; link Google Maps
- **Ações do resultado:** Abrir no Google Maps, Copiar rota (texto formatado), Compartilhar/Copiar link, Salvar rota, Exportar CSV/PDF (desabilitados)
- **Copiar rota:** texto formatado com assinatura `rotaotimizada.com.br`
- **Compartilhar:** chama `/api/v1/shorten` → URL curta `/r/CODE`; `navigator.share()` no mobile, clipboard no desktop
- **Auth:** login por e-mail (magic token); sessão em localStorage (`routeSession`); avatar/iniciais no header; menu de usuário
- **Rotas salvas:** modal "Minhas Rotas" — lista, carrega, exclui; modal com input de nome para salvar
- **Drawer:** Nova rota (confirma se há conteúdo), Minhas rotas, Templates, Importar, Exportar, Template CSV, Ajuda, Entrar/Sair
- **Limpar tudo:** modal de confirmação com opção de salvar antes; reseta estado + localStorage
- **URL params:** `?origin=&dest=&a=` pré-preenche o formulário; `?saved=CODE` carrega rota salva; `?expired=1` exibe toast

## Segurança

- **CORS:** restrito a `rotaotimizada.com.br` em `main.py`
- **Rate limiting:** slowapi por IP no código + Cloudflare Rate Limiting no painel (proteção dupla)
- **Validação:** `Address` com `max_length=200`, addresses com `min_length=2, max_length=50`
- **Auth:** token Bearer gerado por `secrets.token_urlsafe(32)`, armazenado no Turso; sem expiração por enquanto

## Deploy

- **Railway** (Python) — dois serviços apontando para o mesmo repo `bcezar/rota-otimizada`
  - `rotaotimizada.com.br` — `LOCALE=pt-BR`, `BRAND_NAME=Rota Otimizada`
  - `findmyroute.com.br` — `LOCALE=en-US`, `BRAND_NAME=Find My Route`, `GEOCODING_COUNTRY=` (vazio)
- `Procfile`: `web: uvicorn app.main:app --host 0.0.0.0 --port $PORT`
- **Cloudflare** — DNS proxy + Rate Limiting para ambos os domínios
- **Domínios:** `rotaotimizada.com.br` (PT) e `findmyroute.com.br` (EN)

## Variáveis de ambiente (`.env`)

```
GOOGLE_MAPS_API_KEY=     # obrigatório para autocomplete, reverse geocoding e geocoding de qualidade
NOMINATIM_USER_AGENT=rota-otimizada/1.0
NOMINATIM_BASE_URL=https://nominatim.openstreetmap.org
TSP_TIMEOUT_SECONDS=5
MAX_ADDRESSES=50
OSRM_BASE_URL=           # opcional; sem isso usa Haversine
TURSO_DATABASE_URL=      # libsql://... — persistência de rotas salvas, users, sessions
TURSO_AUTH_TOKEN=        # token de autenticação do Turso
LOCALE=pt-BR              # pt-BR ou en-US — controla idioma, marca e geocoding
BRAND_NAME=Rota Otimizada # nome da marca exibido
GEOCODING_COUNTRY=br      # código ISO do país para restringir geocoding (vazio = global)
GEOCODING_LANGUAGE=pt-BR  # idioma das respostas do Google Maps / Nominatim
```

> **Nunca commitar o `.env`** — contém a API key do Google Maps e credenciais do Turso.

As variáveis `LOCALE`, `BRAND_NAME`, `GEOCODING_COUNTRY`, `GEOCODING_LANGUAGE`, `GA_MEASUREMENT_ID`, `APP_BASE_URL`, `RESEND_FROM_EMAIL` e `APP_NAME` diferem entre os dois deploys. As demais são compartilhadas.

## Decisões técnicas relevantes

- **`from __future__ import annotations` + Pydantic:** Não usar em arquivos que usem `Body(...)` como parâmetro — causa `ForwardRef` não resolvido em runtime. Em `routes.py` usar `Optional[X]` diretamente.
- **`app/limiter.py` separado:** Evita circular import entre `main.py` e `routes.py`.
- **Short links em memória (`storage.py`):** Links `/r/{code}` expiram no próximo deploy. Rotas salvas (`/s/{code}`) são persistidas no Turso.
- **Turso via HTTP:** `storage.py` usa a HTTP API do Turso (`/v2/pipeline`) com `httpx` — sem libsql-client. Tabelas: `routes`, `saved_routes`, `users`, `sessions`.
- **Geocoding paralelo:** Google Maps usa `asyncio.gather`; Nominatim é sequencial com `sleep(1s)` (usage policy).
- **OR-Tools endpoint fixo:** Quando `origin == destination` (retorno ao depósito), o nó é duplicado nas coordenadas para que OR-Tools trate como índices distintos.
- **`leg_distance_km`:** Calculado direto da matriz em memória — sem custo extra de I/O.
- **Geolocalização mobile:** Texto do botão oculto em telas ≤480px (`.btn-geo-text { display: none }`).
- **Import CSV/XLSX no frontend:** Parser CSV vanilla com detecção de delimitador (`,` vs `;`) e suporte RFC 4180. XLSX via SheetJS injetado lazily do CDN (`cdn.sheetjs.com`) apenas quando necessário.
- **Accordion de paradas:** `x-show` com `x-transition` hooks de classe (`addr-enter/leave`) usando `max-height` para animação natural.
- **i18n via env var:** `LOCALE` em `config.py` seleciona o dicionário em `app/i18n.py`. Templates recebem `i18n` dict via contexto Jinja2; JS recebe `window.I18N`. Slugs das páginas SEO diferem por locale (`_SEO_PAGES_PT` vs `_SEO_PAGES_EN` em `main.py`).
- **Geocoding locale-aware:** `GEOCODING_COUNTRY` (padrão `br`) e `GEOCODING_LANGUAGE` (padrão `pt-BR`) controlam restrições nas APIs Google Maps e Nominatim. Deploy EN usa `GEOCODING_COUNTRY=` (vazio) para busca global.
- **Sitemap e robots.txt dinâmicos:** servidos por rotas FastAPI (`/sitemap.xml`, `/robots.txt`) usando `_BASE_URL` e `_SEO_PAGES` — sem arquivo estático.

## Próximos passos

- [x] Distâncias reais de estrada (OSRM)
- [x] Frontend Alpine.js completo
- [x] Rate limiting (slowapi + Cloudflare)
- [x] Autocomplete Google Places
- [x] Geolocalização com reverse geocoding
- [x] Short links para compartilhamento (`/r/{code}`)
- [x] Distância por trecho no resultado (`leg_distance_km`)
- [x] Auth + rotas salvas (Turso) — login por e-mail, salvar/carregar/excluir rotas
- [x] Mini-mapa + imagem Google Static Maps
- [x] Importar/exportar paradas (CSV/XLSX)
- [x] SEO — canonical, robots.txt, sitemap.xml, Open Graph, Twitter Cards, JSON-LD, novo título
- [x] Google Search Console — verificado via Cloudflare DNS; sitemap enviado
- [x] **Migração de domínio (CORS)** — `allow_origins` em `main.py` atualizado para `rotaotimizada.com.br`
- [x] **i18n dual-deploy** — PT (rotaotimizada.com.br) e EN (findmyroute.com.br)
- [x] **Geocoding locale-aware** — restrição BR apenas no deploy PT
- [x] **Search Console verificado para ambos os domínios; sitemaps enviados**
- [ ] Cache persistente de geocoding (Redis ou SQLite)
- [ ] Exportar rota otimizada como CSV/PDF
- [ ] **Gateway de pagamento EN (Stripe)** — Asaas é BR-only
- [ ] **Upgrade de plano (freemium)** — modelo: 5 paradas grátis, 50 no plano Pro:
  - Backend: validar `len(addresses) <= 5` para usuários sem plano Pro em `routes.py` (retornar 402 com mensagem de upgrade)
  - Frontend: bloquear botão "Otimizar" com CTA de upgrade quando `addresses.length > 5 && !user?.isPro` — ver `app/static/app.js` linha ~937 (TODO marcado)
  - Auth: adicionar campo `is_pro: bool` no modelo de usuário (`storage.py`, tabela `users`)
  - Billing: integrar Stripe (cartão) ou Pix recorrente para ativação do plano Pro
