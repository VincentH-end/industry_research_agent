import pytest
from fastapi import HTTPException

from app.config import Settings
from app.security import current_principal


@pytest.mark.asyncio
async def test_dev_mode_is_open_when_no_keys_are_configured():
    principal = await current_principal(x_api_key=None, settings=Settings(app_env="dev"))
    assert "reports:write" in principal.scopes


@pytest.mark.asyncio
async def test_prod_mode_rejects_missing_key():
    with pytest.raises(HTTPException) as exc:
        await current_principal(
            x_api_key=None,
            settings=Settings(app_env="prod", api_keys="secret:analyst:reports:read"),
        )
    assert exc.value.status_code == 401


@pytest.mark.asyncio
async def test_key_resolves_role_and_scopes():
    principal = await current_principal(
        x_api_key="secret",
        settings=Settings(app_env="prod", api_keys="secret:analyst:reports:read|evals:read"),
    )
    assert principal.role == "analyst"
    assert principal.scopes == {"reports:read", "evals:read"}

