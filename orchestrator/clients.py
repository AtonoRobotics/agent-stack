# Mission Control - Proprietary Software
# © 2026 Alpha. All rights reserved.
# Unauthorized use or distribution prohibited.
"""Model client factory for AutoGen agents.

Creates OpenAIChatCompletionClient instances for Ollama endpoints.
Uses models.yml and fleet.yml for host/model configuration.
"""

import os
import yaml
from autogen_ext.models.openai import OpenAIChatCompletionClient

CONFIG_DIR = os.path.expanduser("~/agent-stack/config")

# Shared model_info for Ollama models (AutoGen requires this)
_OLLAMA_MODEL_INFO = {
    "vision": False,
    "function_calling": True,
    "json_output": True,
    "structured_output": False,
    "family": "unknown",
}


def _load_config(filename: str) -> dict:
    path = os.path.join(CONFIG_DIR, filename)
    with open(path) as f:
        return yaml.safe_load(f)


def create_client(model: str, host: str, port: int = 11434) -> OpenAIChatCompletionClient:
    """Create an OpenAIChatCompletionClient for an Ollama endpoint."""
    return OpenAIChatCompletionClient(
        model=model,
        api_key="ollama",
        base_url=f"http://{host}:{port}/v1",
        model_info=_OLLAMA_MODEL_INFO,
    )


def create_clients() -> dict[str, OpenAIChatCompletionClient]:
    """Create all model clients from config.

    Returns a dict keyed by role name:
      - "local" (qwen2.5:7b on localhost)
      - "spark_72b" (qwen2.5:72b on DGX Spark)
      - "spark_coder" (qwen2.5-coder:32b on DGX Spark)
    """
    models_config = _load_config("models.yml")["models"]

    # Extract unique host+model combos from config
    local_conf = models_config["monitoring"]
    spark_conf = models_config["research"]  # 72b
    coder_conf = models_config["code_generation"]  # 32b coder

    return {
        "local": create_client(
            model=local_conf["model"],
            host=local_conf["host"],
            port=local_conf.get("port", 11434),
        ),
        "spark_72b": create_client(
            model=spark_conf["model"],
            host=spark_conf["host"],
            port=spark_conf.get("port", 11434),
        ),
        "spark_coder": create_client(
            model=coder_conf["model"],
            host=coder_conf["host"],
            port=coder_conf.get("port", 11434),
        ),
    }
