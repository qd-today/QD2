"""Plugin management API routes."""

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from typing import Optional

from qd_server.middleware.auth import get_current_user, require_admin
from qd_server.models.user import User

router = APIRouter()


class PluginInfo(BaseModel):
    name: str
    enabled: bool
    is_default: bool


class PluginInstallRequest(BaseModel):
    name: str


class PluginListResponse(BaseModel):
    plugins: list[PluginInfo]


@router.get("", response_model=PluginListResponse)
async def list_plugins(current_user: User = Depends(get_current_user)):
    """List all installed plugins."""
    from qd_core.plugins.manager import QDPluginManager

    pm = QDPluginManager("qd.plugins")
    plugins = pm.list_plugins()

    return PluginListResponse(
        plugins=[
            PluginInfo(
                name=name,
                enabled=info["enabled"],
                is_default=info["default"],
            )
            for name, info in plugins.items()
        ]
    )


@router.post("/install", status_code=status.HTTP_201_CREATED)
async def install_plugin(
    request: PluginInstallRequest,
    current_user: User = Depends(require_admin),
):
    """Install a plugin (admin only)."""
    from qd_core.plugins.manager import QDPluginManager

    pm = QDPluginManager("qd.plugins")
    success = await pm.install_plugin(request.name)

    if not success:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to install plugin: {request.name}",
        )

    return {"message": f"Plugin '{request.name}' installed successfully"}


@router.delete("/{plugin_name}")
async def uninstall_plugin(
    plugin_name: str,
    current_user: User = Depends(require_admin),
):
    """Uninstall a plugin (admin only)."""
    from qd_core.plugins.manager import QDPluginManager

    pm = QDPluginManager("qd.plugins")

    try:
        await pm.uninstall_plugin(plugin_name)
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )

    return {"message": f"Plugin '{plugin_name}' uninstalled"}
