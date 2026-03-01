"""Ollama client factories using AutoGen OpenAIChatCompletionClient."""

import yaml
import os
from autogen_ext.models.openai import OpenAIChatCompletionClient

CONFIG_PATH = os.path.expanduser("~/agent-stack/config/models.yml")

MODEL_INFO = {
    "vision": False,
    "function_calling": True,
    "json_output": True,
    "structured_output": False,
    "family": "unknown",
}


def _load_config():
    with open(CONFIG_PATH) as f:
        return yaml.safe_load(f)


def create_client(model: str, host: str, port: int = 11434, timeout: float = 300.0) -> OpenAIChatCompletionClient:
    return OpenAIChatCompletionClient(
        model=model,
        api_key="ollama",
        base_url=f"http://{host}:{port}/v1",
        model_info=MODEL_INFO,
        timeout=timeout,
    )


def create_clients() -> dict[str, OpenAIChatCompletionClient]:
    cfg = _load_config()
    models = cfg["models"]
    return {
        "local": create_client(
            models["monitoring"]["model"],
            models["monitoring"]["host"],
            models["monitoring"]["port"],
        ),
        "spark_72b": create_client(
            models["research"]["model"],
            models["research"]["host"],
            models["research"]["port"],
        ),
        "spark_coder": create_client(
            models["code_generation"]["model"],
            models["code_generation"]["host"],
            models["code_generation"]["port"],
        ),
    }
