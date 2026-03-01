"""Skills module — domain-specific code and config generators.

Each skill function takes keyword arguments and returns a string
(generated code, YAML config, test script, etc.).
"""

from skills import robotics, safety, deployment

# ---------------------------------------------------------------------------
# Registry — maps skill names to (function, description)
# ---------------------------------------------------------------------------

SKILL_REGISTRY: dict[str, tuple[callable, str]] = {}


def _register(module, prefix=""):
    """Auto-register all public functions from a module as skills."""
    for name in dir(module):
        if name.startswith("_"):
            continue
        fn = getattr(module, name)
        if callable(fn) and hasattr(fn, "__doc__") and fn.__doc__:
            key = f"{prefix}{name}" if prefix else name
            SKILL_REGISTRY[key] = (fn, fn.__doc__.strip().split("\n")[0])


_register(robotics)
_register(safety)
_register(deployment)


def run_skill(name: str, **kwargs) -> str:
    """Run a skill by name with keyword arguments. Returns generated code/config string."""
    if name not in SKILL_REGISTRY:
        available = "\n".join(f"  {k}: {desc}" for k, (_, desc) in sorted(SKILL_REGISTRY.items()))
        return f"Unknown skill: {name}\n\nAvailable skills:\n{available}"
    fn, _ = SKILL_REGISTRY[name]
    try:
        return fn(**kwargs)
    except Exception as e:
        return f"Skill '{name}' error: {e}"


def list_skills() -> str:
    """List all available skills with descriptions."""
    lines = [f"# Available Skills ({len(SKILL_REGISTRY)})"]
    for name, (_, desc) in sorted(SKILL_REGISTRY.items()):
        lines.append(f"  {name}: {desc}")
    return "\n".join(lines)
