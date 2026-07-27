"""
AI Operating System — Production CLI Entry Point.
Initializes plugins, scheduler, and Director Agent.
Processes user goals, executes workflows/plugins, and outputs structured results.

Usage:
  python src/main.py --goal "Research quantum computing"
  python src/main.py --plugin research --action research --payload '{"topic": "AI"}'
  python src/main.py --list-plugins
  python src/main.py --system-status
"""

import sys
import os
import json
import argparse
import asyncio
import logging

# Ensure src parent directory is in sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from src.core.event_bus import bus
from src.core.scheduler import scheduler
from src.core.plugin_manager import plugin_manager
from src.core.context_manager import context_mgr
from src.storage.storage_layer import storage
from src.agents.director import DirectorAgent

# Ensure all agent plugins are imported & registered
import src.agents.browser_agent
import src.agents.computer_agent
import src.agents.research_agent
import src.agents.facebook_agent
import src.agents.university_agent
import src.agents.media_agent

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
log = logging.getLogger("main")


async def async_main():
    parser = argparse.ArgumentParser(description="AI Operating System CLI")
    parser.add_argument("--goal", type=str, help="High-level user goal to orchestrate")
    parser.add_argument("--workflow", type=str, help="Optional registered workflow ID")
    parser.add_argument("--plugin", type=str, help="Plugin name to invoke directly")
    parser.add_argument("--action", type=str, help="Plugin action name")
    parser.add_argument("--payload", type=str, default="{}", help="JSON payload for plugin action")
    parser.add_argument("--list-plugins", action="store_true", help="List registered system plugins")
    parser.add_argument("--system-status", action="store_true", help="Show system status and storage metrics")

    args = parser.parse_args()

    # Initialize components
    await plugin_manager.initialize_all()
    await scheduler.start()

    try:
        if args.list_plugins:
            plugins = plugin_manager.list_plugins()
            print("\n=== REGISTERED PLUGINS ===")
            print(json.dumps(plugins, indent=2))
            return

        if args.system_status:
            status = {
                "system_status": "ONLINE",
                "registered_plugins": len(plugin_manager.plugins),
                "active_tasks": len(context_mgr.active_tasks),
                "cache_directory": str(storage.cache.cache_dir),
                "db_path": str(storage.sqlite_db.db_path),
                "artifacts_dir": str(storage.artifacts_dir)
            }
            print("\n=== SYSTEM STATUS ===")
            print(json.dumps(status, indent=2))
            return

        if args.plugin and args.action:
            try:
                payload_dict = json.loads(args.payload)
            except Exception as e:
                print(json.dumps({"status": "error", "message": f"Invalid JSON payload: {e}"}))
                return

            log.info(f"Invoking direct plugin '{args.plugin}' -> action '{args.action}'")
            result = await plugin_manager.invoke(args.plugin, args.action, payload_dict)
            print("\n=== PLUGIN RESULT ===")
            print(json.dumps(result, indent=2))
            return

        if args.goal:
            director = DirectorAgent()
            log.info(f"Delegating goal to DirectorAgent: '{args.goal}'")
            result = await director.handle_goal(args.goal, workflow_id=args.workflow)
            print("\n=== DIRECTOR ORCHESTRATION RESULT ===")
            print(json.dumps(result, indent=2))
            return

        # Default interactive prompt if no args provided
        parser.print_help()

    finally:
        await scheduler.stop()
        storage.close()


def main():
    asyncio.run(async_main())


if __name__ == "__main__":
    main()
