from typing import Dict, Any, Callable, List

class MCPRegistry:
    def __init__(self):
        self._tools: Dict[str, Dict[str, Any]] = {}

    def register_tool(self, name: str, description: str, handler: Callable):
        self._tools[name] = {
            "name": name,
            "description": description,
            "handler": handler
        }

    def get_tool(self, name: str):
        return self._tools.get(name)

    def list_tools(self) -> List[Dict[str, str]]:
        return [{"name": t["name"], "description": t["description"]} for t in self._tools.values()]

mcp_registry = MCPRegistry()
