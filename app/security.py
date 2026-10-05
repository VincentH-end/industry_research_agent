import hashlib
import hmac
from dataclasses import dataclass

from fastapi import Depends, Header, HTTPException, status

from .config import Settings, get_settings


@dataclass(frozen=True)
class Principal:
    subject: str
    role: str
    scopes: frozenset[str]


def _configured_keys(settings: Settings) -> list[tuple[str, Principal]]:
    records = []
    for raw in filter(None, (part.strip() for part in settings.api_keys.split(","))):
        parts = raw.split(":", 2)
        if len(parts) != 3:
            continue
        key, role, scope_text = parts
        fingerprint = hashlib.sha256(key.encode()).hexdigest()[:12]
        records.append(
            (key, Principal(f"apikey:{fingerprint}", role, frozenset(scope_text.split("|"))))
        )
    return records


async def current_principal(
    x_api_key: str | None = Header(default=None, alias="X-API-Key"),
    settings: Settings = Depends(get_settings),
) -> Principal:
    records = _configured_keys(settings)
    if settings.app_env.lower() != "prod" and not records:
        return Principal(
            "anonymous-dev",
            "developer",
            frozenset({"reports:read", "reports:write", "evals:read", "evals:write", "memory:read", "memory:write"}),
        )
    if not x_api_key:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "缺少 X-API-Key")
    for key, principal in records:
        if hmac.compare_digest(x_api_key, key):
            return principal
    raise HTTPException(status.HTTP_401_UNAUTHORIZED, "无效的 X-API-Key")


def require_scope(scope: str):
    async def dependency(principal: Principal = Depends(current_principal)) -> Principal:
        if scope not in principal.scopes:
            raise HTTPException(status.HTTP_403_FORBIDDEN, f"缺少权限: {scope}")
        return principal

    return dependency
