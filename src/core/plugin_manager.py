"""
PluginManager - Extensible plugin system for external integrations
(Facebook, WhatsApp, Telegram, Gmail, Google Drive, GitHub, etc.)
without altering core system code.
"""

import os
import importlib
import logging
from typing import Dict, Any, List, Optional
from abc import ABC, abstractmethod

log = logging.getLogger("plugin_manager")

class BasePlugin(ABC):
    @property
    @abstractmethod
    def plugin_name(self) -> str:
        pass

    @property
    @abstractmethod
    def description(self) -> str:
        pass

    @abstractmethod
    async def initialize(self) -> bool:
        pass

    @abstractmethod
    async def execute_action(self, action_name: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        pass

class PluginManager:
    def __init__(self):
        self.plugins: Dict[str, BasePlugin] = {}

    def register_plugin(self, plugin: BasePlugin):
        """Register a plugin instance."""
        self.plugins[plugin.plugin_name.lower()] = plugin
        log.info(f"[PluginManager] Registered plugin '{plugin.plugin_name}'")

    async def initialize_all(self):
        """Initialize all registered plugins."""
        for name, plugin in self.plugins.items():
            try:
                ok = await plugin.initialize()
                log.info(f"[PluginManager] Plugin '{name}' initialized: {ok}")
            except Exception as e:
                log.error(f"[PluginManager] Error initializing plugin '{name}': {e}")

    async def invoke(self, plugin_name: str, action_name: str, payload: Dict[str, Any] = None) -> Dict[str, Any]:
        """Invoke action on a target plugin."""
        name = plugin_name.lower()
        if name not in self.plugins:
            log.error(f"[PluginManager] Plugin '{plugin_name}' not registered.")
            return {"status": "error", "message": f"Plugin '{plugin_name}' not found."}

        plugin = self.plugins[name]
        try:
            return await plugin.execute_action(action_name, payload or {})
        except Exception as e:
            log.error(f"[PluginManager] Action '{action_name}' on '{plugin_name}' failed: {e}")
            return {"status": "error", "error": str(e)}

    def list_plugins(self) -> List[Dict[str, str]]:
        return [{"name": p.plugin_name, "description": p.description} for p in self.plugins.values()]

# Singleton
plugin_manager = PluginManager()
