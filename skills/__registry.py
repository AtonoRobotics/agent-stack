# Mission Control - Proprietary Software
# © 2026 Alpha. All rights reserved.
# Unauthorized use or distribution prohibited.
"""Auto-discovers skill classes from all subdirectories."""
import os
import importlib
import sys

SKILLS_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(SKILLS_DIR))


def scan_skills() -> dict:
    """Scan all subdirectories for skill classes.
    Returns dict of skill_name -> skill_class."""
    skills = {}
    for subdir in os.listdir(SKILLS_DIR):
        subdir_path = os.path.join(SKILLS_DIR, subdir)
        if not os.path.isdir(subdir_path) or subdir.startswith("_"):
            continue
        for fname in os.listdir(subdir_path):
            if fname.endswith(".py") and not fname.startswith("_"):
                module_name = f"skills.{subdir}.{fname[:-3]}"
                try:
                    mod = importlib.import_module(module_name)
                    for attr_name in dir(mod):
                        attr = getattr(mod, attr_name)
                        if isinstance(attr, type) and attr_name.endswith("Skill") and attr_name != "Skill":
                            skill_key = fname[:-3]  # filename without .py
                            skills[skill_key] = attr
                except Exception as e:
                    print(f"Warning: Could not load skill {module_name}: {e}")
    return skills
