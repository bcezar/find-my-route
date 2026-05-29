from __future__ import annotations

import json
import secrets

import httpx

from app.config import settings

_routes: dict[str, dict] = {}


def _turso_configured() -> bool:
    return bool(settings.turso_database_url and settings.turso_auth_token)


def _turso_http_url() -> str:
    return (settings.turso_database_url or "").replace("libsql://", "https://")


async def _execute(sql: str, args: list | None = None) -> dict:
    stmt: dict = {"sql": sql}
    if args:
        stmt["args"] = [{"type": "text", "value": str(a)} for a in args]
    async with httpx.AsyncClient() as client:
        r = await client.post(
            f"{_turso_http_url()}/v2/pipeline",
            headers={"Authorization": f"Bearer {settings.turso_auth_token}"},
            json={"requests": [{"type": "execute", "stmt": stmt}, {"type": "close"}]},
            timeout=10,
        )
        r.raise_for_status()
        return r.json()["results"][0]["response"]["result"]


async def init_db() -> None:
    if not _turso_configured():
        return
    await _execute(
        "CREATE TABLE IF NOT EXISTS routes "
        "(code TEXT PRIMARY KEY, state TEXT NOT NULL, created_at TEXT DEFAULT (datetime('now')))"
    )


async def save_route(state: dict) -> str:
    code = secrets.token_urlsafe(6)
    if _turso_configured():
        await _execute(
            "INSERT INTO routes (code, state) VALUES (?, ?)",
            [code, json.dumps(state)],
        )
    else:
        while code in _routes:
            code = secrets.token_urlsafe(6)
        _routes[code] = state
    return code


async def get_route(code: str) -> dict | None:
    if _turso_configured():
        result = await _execute("SELECT state FROM routes WHERE code = ?", [code])
        rows = result.get("rows", [])
        if rows:
            cell = rows[0][0]
            raw = cell["value"] if isinstance(cell, dict) else cell
            return json.loads(raw)
        return None
    return _routes.get(code)
