from __future__ import annotations

import secrets

_routes: dict[str, dict] = {}


def save_route(state: dict) -> str:
    code = secrets.token_urlsafe(6)
    while code in _routes:
        code = secrets.token_urlsafe(6)
    _routes[code] = state
    return code


def get_route(code: str) -> dict | None:
    return _routes.get(code)
