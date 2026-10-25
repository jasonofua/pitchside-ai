"""Settings from environment variables. See .env.example for local mode."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

REPO_ROOT = Path(os.environ.get("PITCHSIDE_ROOT", Path(__file__).resolve().parents[2]))


def _env(name: str, default: str = "") -> str:
    return os.environ.get(name, default).strip()


@dataclass(frozen=True)
class Settings:
    mode: Literal["local", "azure"]
    data_dir: Path
    mcp_url: str
    # Models: Foundry in Azure, any OpenAI-compatible endpoint locally, or the offline mock.
    foundry_endpoint: str
    model_large: str
    model_small: str
    openai_compat_base_url: str
    openai_compat_api_key: str
    llm: Literal["foundry", "openai", "mock"]
    model_timeout_s: float
    # Reasoning models (gpt-5.x, o-series) take an effort level instead of a temperature.
    reasoning_effort: Literal["none", "low", "medium", "high"]
    # Azure resources (managed identity; no keys).
    eventhubs_namespace: str
    cosmos_endpoint: str
    cosmos_database: str
    webpubsub_endpoint: str
    webpubsub_hub: str
    appinsights_connection_string: str
    allowed_origins: tuple[str, ...]

    @classmethod
    def from_env(cls) -> Settings:
        mode: Literal["local", "azure"] = (
            "azure" if _env("PITCHSIDE_MODE", "local") == "azure" else "local"
        )
        foundry = _env("FOUNDRY_ENDPOINT")
        compat = _env("OPENAI_COMPAT_BASE_URL")
        llm_env = _env("PITCHSIDE_LLM")
        llm: Literal["foundry", "openai", "mock"]
        if llm_env in ("foundry", "openai", "mock"):
            llm = llm_env  # type: ignore[assignment]
        elif foundry:
            llm = "foundry"
        elif compat:
            llm = "openai"
        else:
            llm = "mock"
        origins = _env("PITCHSIDE_ALLOWED_ORIGINS", "*")
        effort_env = _env("PITCHSIDE_REASONING_EFFORT", "low")
        effort: Literal["none", "low", "medium", "high"] = (
            effort_env if effort_env in ("none", "low", "medium", "high") else "low"  # type: ignore[assignment]
        )
        return cls(
            mode=mode,
            data_dir=Path(_env("PITCHSIDE_DATA_DIR", str(REPO_ROOT / "data" / "runtime"))),
            mcp_url=_env("PITCHSIDE_MCP_URL", "http://127.0.0.1:8000/mcp"),
            foundry_endpoint=foundry,
            model_large=_env("MODEL_LARGE", "gpt-large"),
            model_small=_env("MODEL_SMALL", "gpt-small"),
            openai_compat_base_url=compat,
            openai_compat_api_key=_env("OPENAI_COMPAT_API_KEY"),
            llm=llm,
            model_timeout_s=float(_env("PITCHSIDE_MODEL_TIMEOUT_S", "4")),
            reasoning_effort=effort,
            eventhubs_namespace=_env("EVENTHUBS_NAMESPACE"),
            cosmos_endpoint=_env("COSMOS_ENDPOINT"),
            cosmos_database=_env("COSMOS_DATABASE", "pitchside"),
            webpubsub_endpoint=_env("WEBPUBSUB_ENDPOINT"),
            webpubsub_hub=_env("WEBPUBSUB_HUB", "pitchside"),
            appinsights_connection_string=_env("APPLICATIONINSIGHTS_CONNECTION_STRING"),
            allowed_origins=tuple(o.strip() for o in origins.split(",") if o.strip()),
        )
