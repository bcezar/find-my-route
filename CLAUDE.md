# find-my-route

API REST de roteirização de endereços. Recebe uma lista de endereços, geocodifica, calcula distâncias e retorna a ordem de visita otimizada (TSP).

## Stack

- **Python 3.9** (macOS system python — usar `from __future__ import annotations` em todo arquivo que use `X | Y` ou `list[...]` em annotations, pois o Pydantic avalia em runtime)
- **FastAPI** + **Uvicorn**
- **OR-Tools** (Google) — solver TSP com GLS metaheuristic
- **httpx** — HTTP client async
- **Geocoding:** Google Maps API quando `GOOGLE_MAPS_API_KEY` estiver no `.env`; fallback para Nominatim (OSM) caso contrário

## Comandos

```bash
# Instalar dependências (primeira vez)
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt

# Rodar servidor
.venv/bin/uvicorn app.main:app --reload

# Rodar testes
.venv/bin/pytest -v
```

## Estrutura

```
app/
├── main.py               # FastAPI app; GET /health
├── config.py             # Settings lidos do .env via pydantic-settings
├── models.py             # Pydantic models: RouteRequest, RouteResponse, etc.
├── routers/
│   └── routes.py         # POST /api/v1/routes/optimize
└── services/
    ├── geocoding.py      # Geocodificação: Google Maps ou Nominatim + cache em memória
    ├── distance.py       # Haversine — matriz n×n de distâncias em km
    └── optimizer.py      # OR-Tools TSP solver
tests/
├── test_routes.py        # Testes do endpoint (mock geocoding.geocode_all)
├── test_geocoding.py     # Testes do service de geocoding
├── test_distance.py      # Testes Haversine
└── test_optimizer.py     # Testes OR-Tools
```

## Endpoint

### `POST /api/v1/routes/optimize`

**Request:**
```json
{
  "origin": "Rua X, 123, Cidade/SP",      // opcional — ponto de partida fixo
  "destination": "Rua X, 123, Cidade/SP", // opcional — ponto de chegada fixo (pode ser igual ao origin para retornar ao depósito)
  "addresses": [                           // mínimo 2, máximo 50
    "Rua A, 456, Cidade/SP",
    "Av. B, 789, Outra Cidade/SP"
  ]
}
```

**Response:**
```json
{
  "optimized_route": [
    { "order": 1, "original_address": "...", "coordinates": { "lat": -23.5, "lng": -46.6 } }
  ],
  "total_distance_km": 41.4,
  "geocoding_failures": [],
  "origin": { "address": "...", "coordinates": { "lat": -22.9, "lng": -47.0 } },
  "destination": { "address": "...", "coordinates": { "lat": -22.9, "lng": -47.0 } }
}
```

**Erros:**
| Status | Motivo |
|--------|--------|
| 422 | Menos de 2 endereços, ou `origin`/`destination` não geocodificado |
| 400 | Menos de 2 endereços resolvidos após geocoding |

## Variáveis de ambiente (.env)

```
GOOGLE_MAPS_API_KEY=     # se presente, usa Google Maps; senão usa Nominatim
NOMINATIM_USER_AGENT=find-my-route/1.0
NOMINATIM_BASE_URL=https://nominatim.openstreetmap.org
TSP_TIMEOUT_SECONDS=5
MAX_ADDRESSES=50
```

> **Nunca commitar o `.env`** — ele contém a API key do Google Maps.

## Decisões técnicas relevantes

- **Cache de geocoding** é um dict em memória (`_cache` em `geocoding.py`). Persiste durante o processo, não entre reinicializações. Para limpar, reiniciar o servidor.
- **Rate limit Nominatim**: `asyncio.sleep(1.0)` entre cada chamada. Com Google Maps o sleep existe mas pode ser reduzido.
- **Formato de endereço brasileiro**: `Cidade/SP` é normalizado para `Cidade, SP, Brasil` antes da query ao Nominatim. O Google Maps aceita o formato original diretamente.
- **Nome de estabelecimento**: o serviço detecta e remove prefixos como `"Medkal Pet, 446 Rua Bolívia"` → `"Rua Bolívia, 446"` (apenas para Nominatim).
- **OR-Tools**: usa `PATH_CHEAPEST_ARC` como solução inicial + `GUIDED_LOCAL_SEARCH` para melhoria. Timeout configurável via `TSP_TIMEOUT_SECONDS`.
- **OR-Tools endpoint fixo**: `RoutingIndexManager(n, 1, [start], [end])` fixa início e fim. Quando `origin == destination` (retorno ao depósito), o nó é duplicado na lista de coordenadas para que OR-Tools trate como índices distintos. O loop de extração do resultado faz `while not routing.IsEnd` e adiciona o nó final somente quando `end_index is not None` (o fim virtual do OR-Tools sem endpoint fixo retornaria o depot duplicado).
- **OSRM**: `build_distance_matrix` é `async`; usa OSRM Table API (`/table/v1/driving/{coords}?annotations=distance`) quando `OSRM_BASE_URL` está configurado; fallback para Haversine.

## Próximos passos sugeridos

- [x] Distâncias reais de estrada (OSRM substituiu Haversine em `distance.py`)
- [ ] Cache persistente de geocoding (Redis ou SQLite)
- [ ] Suporte a janelas de tempo por endereço (CVRPTW)
- [ ] `GET /api/v1/routes/{id}` para consultar resultado de uma rota salva
