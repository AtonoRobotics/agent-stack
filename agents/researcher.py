#!/usr/bin/env python3
# Mission Control - Proprietary Software
# © 2026 Alpha. All rights reserved.
# Unauthorized use or distribution prohibited.
"""Researcher agent for documentation lookup, compatibility checks, and dependency resolution."""

import os
import sys
import json
import re
from datetime import datetime

sys.path.insert(0, os.path.expanduser("~/agent-stack"))
from agents.base_agent import BaseAgent


class ResearcherAgent(BaseAgent):
    """Agent for research queries, compatibility checks, API docs, and dependency resolution."""

    task_type = "research"

    KNOWLEDGE_DOMAINS = [
        "Isaac Sim 5.1 API",
        "cuRobo 0.7.7 API",
        "ROS2 Jazzy API",
        "NVIDIA Cosmos",
        "NVIDIA GR00T",
        "DGX Spark hardware",
        "Jetson AGX Thor hardware",
    ]

    def __init__(self):
        super().__init__(self.task_type)

    def _strip_fences(self, text: str) -> str:
        """Remove markdown code fences from model output."""
        text = text.strip()
        if text.startswith("```json"):
            text = text[len("```json"):].strip()
        if text.startswith("```"):
            text = text[3:].strip()
        if text.endswith("```"):
            text = text[:-3].strip()
        return text

    def _extract_json(self, text: str) -> dict:
        """Extract a JSON object from model output, handling markdown fences."""
        text = self._strip_fences(text)
        # Try to find JSON object in the text
        match = re.search(r'\{.*\}', text, re.DOTALL)
        if match:
            try:
                return json.loads(match.group())
            except json.JSONDecodeError:
                pass
        # Fallback: try the whole text
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            return {}

    def research(self, query: str, context: str = "") -> str:
        """Research a topic using the knowledge base and model.

        Loads relevant knowledge, builds a research prompt, queries the model,
        and returns the response.

        Args:
            query: The research question.
            context: Optional additional context to include.

        Returns:
            The model's research response as a string.
        """
        knowledge = self.load_knowledge(self.task_type)
        model_info = self.get_model_info()

        prompt = f"""You are an expert robotics research assistant with deep knowledge of
NVIDIA Isaac Sim, cuRobo, ROS2, Cosmos, and GR00T.

Knowledge base:
{knowledge}

Additional context:
{context}

Research question: {query}

Provide a thorough, accurate answer. Cite specific versions, APIs, and configuration
details where applicable. If you are uncertain about something, say so explicitly."""

        try:
            response = self.query_with_retry(prompt)
            self.log_task(task=f"research:{query[:80]}", result=f"Response: {len(response)} chars",
                          model=model_info["model"], success=True)
            self.log_activity("research", f"Researched: {query[:80]}")
            return response
        except RuntimeError as e:
            self.log_task(task=f"research:{query[:80]}", result=str(e),
                          model=model_info["model"], success=False)
            raise

    def check_compatibility(self, package_a: str, version_a: str,
                            package_b: str, version_b: str) -> dict:
        """Check compatibility between two packages/versions.

        Queries the model about whether the two packages are compatible,
        parses the response into a structured dict.

        Args:
            package_a: First package name (e.g., "Isaac Sim").
            version_a: First package version (e.g., "5.1").
            package_b: Second package name (e.g., "cuRobo").
            version_b: Second package version (e.g., "0.7.7").

        Returns:
            Dict with keys: compatible (bool), notes (str), recommended_versions (dict).
        """
        knowledge = self.load_knowledge(self.task_type)
        model_info = self.get_model_info()

        prompt = f"""You are an expert in robotics software compatibility.

Knowledge base:
{knowledge}

Check compatibility between:
- {package_a} {version_a}
- {package_b} {version_b}

Respond with ONLY a JSON object (no markdown, no explanation) in this exact format:
{{
    "compatible": true or false,
    "notes": "explanation of compatibility status",
    "recommended_versions": {{
        "{package_a}": "recommended version",
        "{package_b}": "recommended version"
    }}
}}"""

        try:
            response = self.query_with_retry(prompt)
            result = self._extract_json(response)

            # Ensure required keys exist with proper types
            if "compatible" not in result:
                result["compatible"] = False
            if "notes" not in result:
                result["notes"] = response.strip()
            if "recommended_versions" not in result:
                result["recommended_versions"] = {
                    package_a: version_a,
                    package_b: version_b,
                }

            # Coerce compatible to bool
            if isinstance(result["compatible"], str):
                result["compatible"] = result["compatible"].lower() in ("true", "yes", "1")

            self.log_task(
                task=f"compat_check:{package_a}@{version_a}_vs_{package_b}@{version_b}",
                result=f"Compatible: {result['compatible']}",
                model=model_info["model"], success=True,
            )
            self.log_activity("compatibility_check",
                              f"{package_a} {version_a} vs {package_b} {version_b}: "
                              f"{'compatible' if result['compatible'] else 'incompatible'}")
            return result
        except RuntimeError as e:
            self.log_task(
                task=f"compat_check:{package_a}@{version_a}_vs_{package_b}@{version_b}",
                result=str(e), model=model_info["model"], success=False,
            )
            raise

    def find_documentation(self, api_name: str, version: str = "") -> str:
        """Query model for API documentation.

        Searches the knowledge base and queries the model for documentation
        on a specific API or function.

        Args:
            api_name: The API, class, or function name to look up.
            version: Optional version constraint.

        Returns:
            Formatted documentation string.
        """
        knowledge = self.load_knowledge(self.task_type)
        model_info = self.get_model_info()

        version_str = f" (version {version})" if version else ""
        prompt = f"""You are a robotics API documentation expert.

Knowledge base:
{knowledge}

Provide comprehensive documentation for: {api_name}{version_str}

Include:
1. Description and purpose
2. Parameters/arguments with types
3. Return values
4. Usage examples
5. Common pitfalls or notes
6. Related APIs or functions

If you are unsure about specific details, indicate this clearly."""

        try:
            response = self.query_with_retry(prompt)
            self.log_task(task=f"find_docs:{api_name}{version_str}",
                          result=f"Docs: {len(response)} chars",
                          model=model_info["model"], success=True)
            self.log_activity("documentation", f"Looked up docs for {api_name}{version_str}")
            return response
        except RuntimeError as e:
            self.log_task(task=f"find_docs:{api_name}{version_str}",
                          result=str(e), model=model_info["model"], success=False)
            raise

    def resolve_dependency_conflict(self, packages: list) -> str:
        """Resolve dependency conflicts between a list of packages.

        Sends the package list to the model and gets resolution advice.

        Args:
            packages: List of package strings, e.g. ["isaac-sim==5.1", "curobo==0.7.7", "torch>=2.1"].

        Returns:
            Resolution advice as a string.
        """
        knowledge = self.load_knowledge(self.task_type)
        model_info = self.get_model_info()

        packages_str = "\n".join(f"  - {pkg}" for pkg in packages)

        prompt = f"""You are an expert in Python dependency management for robotics software.

Knowledge base:
{knowledge}

The following packages have dependency conflicts:
{packages_str}

Analyze the conflicts and provide:
1. Root cause of the conflict
2. Step-by-step resolution
3. Recommended version pins that satisfy all constraints
4. Any known workarounds if a clean resolution is not possible
5. A requirements.txt snippet with the resolved versions"""

        try:
            response = self.query_with_retry(prompt)
            self.log_task(task=f"dep_conflict:{len(packages)}_packages",
                          result=f"Resolution: {len(response)} chars",
                          model=model_info["model"], success=True)
            self.log_activity("dependency_resolution",
                              f"Resolved conflicts for {len(packages)} packages")
            return response
        except RuntimeError as e:
            self.log_task(task=f"dep_conflict:{len(packages)}_packages",
                          result=str(e), model=model_info["model"], success=False)
            raise

    def lookup_hardware_spec(self, device_name: str) -> dict:
        """Look up hardware specifications for a device.

        Loads hardware knowledge base, queries the model, and returns
        a structured specs dictionary.

        Args:
            device_name: The device name (e.g., "DGX Spark", "Jetson AGX Thor", "RTX 4070").

        Returns:
            Dict with hardware specs including keys like gpu, vram, ram, cpu, storage, etc.
        """
        knowledge = self.load_knowledge("health_check")  # hardware knowledge
        model_info = self.get_model_info()

        prompt = f"""You are a hardware specifications expert for NVIDIA robotics platforms.

Knowledge base:
{knowledge}

Look up the hardware specifications for: {device_name}

Respond with ONLY a JSON object (no markdown, no explanation) containing the specs:
{{
    "device": "device name",
    "gpu": "GPU model",
    "vram_gb": numeric value,
    "ram_gb": numeric value,
    "cpu": "CPU model",
    "storage": "storage details",
    "connectivity": "network/IO details",
    "power_draw_w": numeric value,
    "supported_frameworks": ["list", "of", "frameworks"],
    "notes": "any important notes"
}}"""

        try:
            response = self.query_with_retry(prompt)
            result = self._extract_json(response)

            # Ensure at least the device key exists
            if not result:
                result = {
                    "device": device_name,
                    "notes": response.strip(),
                    "raw_response": True,
                }

            self.log_task(task=f"hw_spec:{device_name}",
                          result=f"Specs retrieved for {device_name}",
                          model=model_info["model"], success=True)
            self.log_activity("hardware_lookup", f"Looked up specs for {device_name}")
            return result
        except RuntimeError as e:
            self.log_task(task=f"hw_spec:{device_name}",
                          result=str(e), model=model_info["model"], success=False)
            raise
