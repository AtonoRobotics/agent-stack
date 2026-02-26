# Mission Control - Proprietary Software
# © 2026 Alpha. All rights reserved.
# Unauthorized use or distribution prohibited.
"""
Auto-discovers tool modules from all .py files in the tools/ directory.
"""

import os
import importlib
import importlib.util


TOOLS_DIR = os.path.expanduser("~/agent-stack/tools")
EXCLUDED = {"__init__.py", "__registry.py"}


def scan_tools() -> dict:
    """
    Scan the tools/ directory for Python modules and import them.

    Returns:
        dict mapping tool_name (str) to the imported module object.
        Example: {"ollama": <module>, "bash": <module>, ...}
    """
    tools = {}

    if not os.path.isdir(TOOLS_DIR):
        return tools

    for filename in sorted(os.listdir(TOOLS_DIR)):
        if filename in EXCLUDED:
            continue
        if not filename.endswith(".py"):
            continue

        module_name = filename[:-3]  # strip .py

        try:
            spec = importlib.util.spec_from_file_location(
                f"tools.{module_name}",
                os.path.join(TOOLS_DIR, filename),
            )
            if spec is None or spec.loader is None:
                continue

            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            tools[module_name] = module
        except Exception as exc:
            # Log but don't crash on broken modules
            print(f"[registry] Failed to load tools/{filename}: {exc}")

    return tools
