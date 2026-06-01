from __future__ import annotations

import json
import secrets
import uuid
from datetime import datetime, timezone

import httpx

from app.config import settings

_routes: dict[str, dict] = {}
_saved:  dict[str, dict] = {}
_users:  dict[str, dict] = {}   # email → user dict
_sessions: dict[str, str] = {}  # token → user_id


def _turso_configured() -> bool:
    return bool(settings.turso_database_url and settings.turso_auth_token)


def _turso_http_url() -> str:
    return (settings.turso_database_url or "").replace("libsql://", "https://")


async def _execute(sql: str, args: list | None = None, *, ignore_error: bool = False) -> dict:
    stmt: dict = {"sql": sql}
    if args:
        stmt["args"] = [{"type": "text", "value": str(a)} for a in args]
    try:
        async with httpx.AsyncClient() as client:
            r = await client.post(
                f"{_turso_http_url()}/v2/pipeline",
                headers={"Authorization": f"Bearer {settings.turso_auth_token}"},
                json={"requests": [{"type": "execute", "stmt": stmt}, {"type": "close"}]},
                timeout=10,
            )
            r.raise_for_status()
            return r.json()["results"][0]["response"]["result"]
    except Exception:
        if ignore_error:
            return {}
        raise


def _cell(cell) -> str:
    return cell["value"] if isinstance(cell, dict) else cell


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


async def init_db() -> None:
    if not _turso_configured():
        return
    await _execute(
        "CREATE TABLE IF NOT EXISTS routes "
        "(code TEXT PRIMARY KEY, state TEXT NOT NULL, created_at TEXT DEFAULT (datetime('now')))"
    )
    await _execute(
        "CREATE TABLE IF NOT EXISTS saved_routes "
        "(code TEXT PRIMARY KEY, name TEXT, result TEXT NOT NULL, inputs TEXT NOT NULL, "
        "user_id TEXT, created_at TEXT DEFAULT (datetime('now')))"
    )
    await _execute(
        "CREATE TABLE IF NOT EXISTS users "
        "(id TEXT PRIMARY KEY, email TEXT UNIQUE NOT NULL, created_at TEXT DEFAULT (datetime('now')))"
    )
    await _execute(
        "CREATE TABLE IF NOT EXISTS sessions "
        "(token TEXT PRIMARY KEY, user_id TEXT NOT NULL, created_at TEXT DEFAULT (datetime('now')))"
    )
    # migrate: add user_id column to saved_routes if it doesn't exist yet
    await _execute("ALTER TABLE saved_routes ADD COLUMN user_id TEXT", ignore_error=True)


# ── Short links ─────────────────────────────────────────────────────────────

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
        r = await _execute("SELECT state FROM routes WHERE code = ?", [code])
        rows = r.get("rows", [])
        if rows:
            return json.loads(_cell(rows[0][0]))
        return None
    return _routes.get(code)


# ── Saved routes ─────────────────────────────────────────────────────────────

async def save_result(name: str, result_dict: dict, inputs_dict: dict, user_id: str) -> str:
    code = secrets.token_urlsafe(6)
    if _turso_configured():
        await _execute(
            "INSERT INTO saved_routes (code, name, result, inputs, user_id) VALUES (?, ?, ?, ?, ?)",
            [code, name, json.dumps(result_dict), json.dumps(inputs_dict), user_id],
        )
    else:
        _saved[code] = {"name": name, "result": result_dict, "inputs": inputs_dict, "user_id": user_id}
    return code


async def get_result(code: str) -> dict | None:
    if _turso_configured():
        r = await _execute("SELECT result FROM saved_routes WHERE code = ?", [code])
        rows = r.get("rows", [])
        if rows:
            return json.loads(_cell(rows[0][0]))
        return None
    entry = _saved.get(code)
    return entry["result"] if entry else None


async def list_results(user_id: str) -> list[dict]:
    if _turso_configured():
        r = await _execute(
            "SELECT code, name, result, inputs, created_at FROM saved_routes "
            "WHERE user_id = ? ORDER BY created_at DESC LIMIT 50",
            [user_id],
        )
        rows = r.get("rows", [])
        return [
            {
                "code":       _cell(row[0]),
                "name":       _cell(row[1]),
                "result":     json.loads(_cell(row[2])),
                "inputs":     json.loads(_cell(row[3])),
                "created_at": _cell(row[4]),
            }
            for row in rows
        ]
    return [
        {"code": k, "name": v["name"], "result": v["result"], "inputs": v["inputs"], "created_at": None}
        for k, v in _saved.items()
        if v.get("user_id") == user_id
    ]


# ── Users & sessions ─────────────────────────────────────────────────────────

async def find_or_create_user(email: str) -> dict:
    if _turso_configured():
        r = await _execute("SELECT id, email, created_at FROM users WHERE email = ?", [email])
        rows = r.get("rows", [])
        if rows:
            return {"id": _cell(rows[0][0]), "email": _cell(rows[0][1]), "created_at": _cell(rows[0][2])}
        user_id = str(uuid.uuid4())
        created_at = _now_iso()
        await _execute(
            "INSERT INTO users (id, email, created_at) VALUES (?, ?, ?)",
            [user_id, email, created_at],
        )
        return {"id": user_id, "email": email, "created_at": created_at}
    # in-memory fallback
    for user in _users.values():
        if user["email"] == email:
            return user
    user_id = str(uuid.uuid4())
    user = {"id": user_id, "email": email, "created_at": _now_iso()}
    _users[user_id] = user
    return user


async def create_session(user_id: str) -> str:
    token = secrets.token_urlsafe(32)
    if _turso_configured():
        await _execute(
            "INSERT INTO sessions (token, user_id) VALUES (?, ?)",
            [token, user_id],
        )
    else:
        _sessions[token] = user_id
    return token


async def get_user_by_token(token: str) -> dict | None:
    if _turso_configured():
        r = await _execute(
            "SELECT u.id, u.email FROM sessions s JOIN users u ON s.user_id = u.id WHERE s.token = ?",
            [token],
        )
        rows = r.get("rows", [])
        if rows:
            return {"id": _cell(rows[0][0]), "email": _cell(rows[0][1])}
        return None
    user_id = _sessions.get(token)
    if user_id:
        return _users.get(user_id)
    return None
