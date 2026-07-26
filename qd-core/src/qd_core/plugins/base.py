"""Plugin base classes and decorators for QD2.

This module provides the foundational plugin infrastructure:
- PluginHook enum: defines standard hook points in the request lifecycle
- api_function_plugin: decorator to register functions as discoverable plugins with optional API routes
"""

import asyncio
import sys
from enum import Enum
from functools import partial, wraps
from typing import Any, Callable, Dict, List, Optional, Union

from fastapi import APIRouter
from plux import FunctionPlugin, PluginSpec  # type: ignore
from pydantic import validate_call
from pydantic_settings import BaseSettings

from qd_core.utils.log import Log

logger_plugins = Log("QD.Core.Plugins").getlogger()

router = APIRouter()


class PluginHook(Enum):
    """Standard hook points in the QD request lifecycle.

    Plugins can register handlers for these hooks to intercept
    and modify the request/response flow.
    """

    PRE_REQUEST = "pre_request"          # Before sending HTTP request (sign, encrypt, headers)
    POST_REQUEST = "post_request"        # After receiving response (data extraction, parsing)
    PARSE_HAR = "parse_har"              # HAR template parsing
    SCHEDULE_TASK = "schedule_task"      # When a scheduled task is triggered
    NOTIFY = "notify"                    # Notification dispatch (push, email, webhook)
    ON_ERROR = "on_error"                # Error handling hook


def add_api_routes(
    path_list: List[str],
    function: Callable,
    method_list: List[List[str]],
    router_kwargs: Dict = {},
    custom_router: Optional[APIRouter] = None,
    router_inclusion_kwargs: Dict = {},
) -> None:
    """Add API routes to a FastAPI router.

    Args:
        path_list: List of route paths.
        function: The function to handle the routes.
        method_list: List of HTTP methods for each path.
        router_kwargs: Additional kwargs for add_api_route.
        custom_router: Custom router to use instead of the default.
        router_inclusion_kwargs: Kwargs for include_router.
    """
    target_router = custom_router or router
    for path, methods in zip(path_list, method_list):
        target_router.add_api_route(path, function, methods=methods, **router_kwargs)
        logger_plugins.debug("Added API route: %s %s", path, methods)
    if custom_router:
        router.include_router(custom_router, **router_inclusion_kwargs)


def api_function_plugin(
    namespace: str,
    name: Optional[str] = None,
    path_list: Optional[List[str]] = None,
    method_list: Optional[List[List[str]]] = None,
    router_kwargs: Optional[Dict[str, Any]] = None,
    custom_router: Optional[APIRouter] = None,
    router_inclusion_kwargs: Optional[Dict[str, Any]] = None,
    hook: Optional[PluginHook] = None,
    should_load: Optional[Union[bool, Callable[[], bool]]] = None,
    load_function: Optional[Callable] = None,
    settings: Optional[BaseSettings] = None,
):
    """Decorator that registers a function as a discoverable plugin with optional API routing.

    Args:
        namespace: Plugin namespace for discovery.
        name: Plugin name (defaults to function name).
        path_list: API route paths to register.
        method_list: HTTP methods for each path.
        router_kwargs: Additional kwargs for route registration.
        custom_router: Custom FastAPI router.
        router_inclusion_kwargs: Kwargs for router inclusion.
        hook: The PluginHook this plugin handles.
        should_load: Whether the plugin should be loaded.
        load_function: Custom load function.
        settings: Plugin-specific settings.
    """
    router_kwargs = router_kwargs or {}
    router_inclusion_kwargs = router_inclusion_kwargs or {}
    settings = settings or BaseSettings()

    def decorator(function: Callable) -> Callable:
        plugin_name = name or function.__name__
        validated_function = validate_call(function)

        @wraps(validated_function)
        def plugin_factory():
            # Set up API routes if provided
            if path_list and method_list:
                route_setup_function = partial(
                    add_api_routes,
                    path_list,
                    validated_function,
                    method_list=method_list,
                    router_kwargs=router_kwargs,
                    custom_router=custom_router,
                    router_inclusion_kwargs=router_inclusion_kwargs,
                )
            else:
                route_setup_function = None

            plugin = FunctionPlugin(
                validated_function,
                should_load=should_load,
                load=route_setup_function or load_function,
            )
            plugin.namespace = namespace
            plugin.name = plugin_name
            # Attach hook metadata
            plugin.hook = hook
            return plugin

        # Attach the plugin spec for discovery
        function.__pluginspec__ = PluginSpec(namespace, plugin_name, plugin_factory)  # type: ignore

        return function

    return decorator


async def entrypoints(args: Optional[Any] = None) -> None:
    """Run plux entrypoints command for plugin discovery."""
    command = [sys.executable, "-m", "plux", "entrypoints"]
    from qd_core.utils.shell import set_env_variable_and_run_command

    env = {}
    if sys.version_info < (3, 12):
        env["SETUPTOOLS_USE_DISTUTILS"] = "stdlib"
    return await set_env_variable_and_run_command(command, env)
