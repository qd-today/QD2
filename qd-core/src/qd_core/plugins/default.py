"""Default built-in plugins for QD2.

These plugins are always available and cannot be uninstalled.
"""

from qd_core.plugins.base import PluginHook, api_function_plugin

# Namespace for default plugins
DEFAULT_NAMESPACE = "qd.plugins.default"


@api_function_plugin(
    namespace=DEFAULT_NAMESPACE,
    name="util-delay",
    hook=PluginHook.SCHEDULE_TASK,
)
async def util_delay(seconds: float) -> None:
    """Simple delay utility plugin for testing.

    Args:
        seconds: Number of seconds to delay. Negative values are clamped to 0.
    """
    import asyncio

    await asyncio.sleep(max(0, seconds))
