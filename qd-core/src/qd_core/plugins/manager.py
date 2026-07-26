"""Plugin manager for QD2.

Handles plugin lifecycle: discovery, installation, enabling, disabling, and uninstallation.
Uses plux for plugin discovery and importlib.metadata for package management.
"""

import asyncio
import importlib.metadata as importlib_metadata
import sys
from typing import Dict, Optional

from plux import Plugin, PluginManager  # type: ignore

from qd_core.plugins.base import logger_plugins
from qd_core.utils.log import Log

logger = Log("QD.Core.PluginManager").getlogger()


class QDPluginManager:
    """Manages the lifecycle of QD2 plugins.

    Plugins are discovered via plux namespaces. Default plugins (in the
    'qd.plugins.default' namespace) are always enabled and cannot be
    uninstalled. Third-party plugins can be installed via pip.
    """

    def __init__(self, namespace: str, strict_default_plugins: bool = True):
        self.namespace = namespace
        self.plugin_manager = PluginManager(namespace)
        self._default_plugins_manager = PluginManager("qd.plugins.default")
        self._strict_default_plugins = strict_default_plugins
        self.enabled_plugins: Dict[str, Plugin] = {}

        # Auto-enable default plugins
        for plugin_name in self._default_plugins_manager._plugins.keys():
            self.enable_plugin(plugin_name)

    def _is_default_plugin(self, plugin_name: str) -> bool:
        """Check if a plugin is a built-in default plugin."""
        return plugin_name in self._default_plugins_manager._plugins.keys()

    def enable_plugin(self, plugin_name: str, default: bool = False) -> None:
        """Enable a plugin by name.

        Args:
            plugin_name: Name of the plugin to enable.
            default: If True, load from default plugins namespace.

        Raises:
            Exception: If the plugin cannot be loaded.
        """
        if plugin_name in self.enabled_plugins:
            logger.info("Plugin '%s' is already enabled.", plugin_name)
            return

        if default or (self._strict_default_plugins and self._is_default_plugin(plugin_name)):
            plugin = self._default_plugins_manager.load(plugin_name)
        else:
            plugin = self.plugin_manager.load(plugin_name)

        if plugin:
            self.enabled_plugins[plugin_name] = plugin
            logger.info("Plugin '%s' has been enabled.", plugin_name)
        else:
            logger.error("Failed to load plugin '%s'.", plugin_name)
            raise Exception(f"Failed to load plugin '{plugin_name}'.")

    def disable_plugin(self, plugin_name: str) -> None:
        """Disable a plugin. Default plugins cannot be disabled.

        Args:
            plugin_name: Name of the plugin to disable.
        """
        if plugin_name not in self.enabled_plugins:
            logger.info("Plugin '%s' is already disabled.", plugin_name)
            return

        if self._is_default_plugin(plugin_name):
            logger.error("Default plugin '%s' cannot be disabled.", plugin_name)
            return

        self.enabled_plugins.pop(plugin_name)
        logger.info("Plugin '%s' has been disabled.", plugin_name)

    async def install_plugin(self, plugin_name_or_vcs: str) -> bool:
        """Install a plugin via pip.

        Args:
            plugin_name_or_vcs: Package name or VCS URL.

        Returns:
            True if installation succeeded, False otherwise.
        """
        from qd_core.utils.shell import run_command_and_log_output_async

        try:
            from pip._internal.req.constructors import install_req_from_line

            plugin_name = install_req_from_line(plugin_name_or_vcs).name

            # Check if already installed
            try:
                importlib_metadata.distribution(plugin_name)
                logger.info("Plugin '%s' is already installed.", plugin_name)
                return True
            except importlib_metadata.PackageNotFoundError:
                pass

            # Install via pip
            return_code = await run_command_and_log_output_async(
                sys.executable, "-m", "pip", "install", plugin_name_or_vcs
            )

            if return_code == 0:
                logger.info("Plugin '%s' has been installed.", plugin_name)
                return True
            else:
                logger.error("Failed to install plugin '%s'. Return code: %d", plugin_name, return_code)
                return False

        except Exception as e:
            logger.error("Failed to install plugin '%s': %s", plugin_name_or_vcs, e)
            raise

    async def uninstall_plugin(self, plugin_name: str) -> None:
        """Uninstall a plugin via pip. Default plugins cannot be uninstalled.

        Args:
            plugin_name: Name of the plugin to uninstall.

        Raises:
            Exception: If trying to uninstall a default plugin.
        """
        from qd_core.utils.shell import run_command_and_log_output_async

        if self._is_default_plugin(plugin_name):
            logger.error("Default plugin '%s' cannot be uninstalled.", plugin_name)
            raise Exception(f"Default plugin '{plugin_name}' cannot be uninstalled.")

        try:
            importlib_metadata.distribution(plugin_name)
        except importlib_metadata.PackageNotFoundError:
            logger.info("Plugin '%s' is not installed.", plugin_name)
            return

        return_code = await run_command_and_log_output_async(
            sys.executable, "-m", "pip", "uninstall", "-y", plugin_name
        )

        if return_code == 0:
            logger.info("Plugin '%s' has been uninstalled.", plugin_name)
        else:
            logger.error("Failed to uninstall plugin '%s'. Return code: %d", plugin_name, return_code)

    def list_plugins(self) -> Dict[str, Any]:
        """List all available plugins with their status.

        Returns:
            Dict mapping plugin names to their enabled status.
        """
        result = {}
        for name in self._default_plugins_manager._plugins.keys():
            result[name] = {"enabled": name in self.enabled_plugins, "default": True}
        for name in self.plugin_manager._plugins.keys():
            result[name] = {"enabled": name in self.enabled_plugins, "default": False}
        return result
