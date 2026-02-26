# Mission Control - Proprietary Software
# © 2026 Alpha. All rights reserved.
# Unauthorized use or distribution prohibited.
"""
Ollama API client for model inference, listing, and health checks.
"""

import httpx
import asyncio
import json


async def generate(model: str, prompt: str, host: str, port: int = 11434) -> str:
    """
    Generate a completion from an Ollama model.

    Args:
        model: Model name (e.g. "qwen2.5-coder:32b").
        prompt: The text prompt to send.
        host: Hostname or IP of the Ollama server.
        port: Port number (default 11434).

    Returns:
        The generated text response.
    """
    url = f"http://{host}:{port}/api/generate"
    payload = {"model": model, "prompt": prompt, "stream": False}
    timeout = httpx.Timeout(300.0)

    async with httpx.AsyncClient(timeout=timeout) as client:
        resp = await client.post(url, json=payload)
        resp.raise_for_status()
        data = resp.json()
        return data["response"]


async def list_models(host: str, port: int = 11434) -> list:
    """
    List all models available on an Ollama instance.

    Args:
        host: Hostname or IP of the Ollama server.
        port: Port number (default 11434).

    Returns:
        List of model name strings.
    """
    url = f"http://{host}:{port}/api/tags"
    timeout = httpx.Timeout(30.0)

    async with httpx.AsyncClient(timeout=timeout) as client:
        resp = await client.get(url)
        resp.raise_for_status()
        data = resp.json()
        return [m["name"] for m in data.get("models", [])]


async def check_health(host: str, port: int = 11434) -> bool:
    """
    Check if an Ollama instance is reachable and healthy.

    Args:
        host: Hostname or IP of the Ollama server.
        port: Port number (default 11434).

    Returns:
        True if the server responds with 200, False otherwise.
    """
    url = f"http://{host}:{port}/"
    timeout = httpx.Timeout(10.0)

    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            resp = await client.get(url)
            return resp.status_code == 200
    except (httpx.ConnectError, httpx.TimeoutException, httpx.HTTPError, OSError):
        return False
