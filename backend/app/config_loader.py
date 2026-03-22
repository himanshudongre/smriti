"""
Provider configuration loader.
Priority: env vars > config/providers.yaml > built-in defaults.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

try:
    import yaml
    _YAML_AVAILABLE = True
except ImportError:
    _YAML_AVAILABLE = False


# ── Typed config objects ──────────────────────────────────────────────────────

@dataclass
class ProviderConfig:
    enabled: bool = False
    api_key: str = ""
    default_model: str = ""
    base_url: str = ""
    missing_package: bool = False


@dataclass
class ChatConfig:
    default_provider: str = "openrouter"
    autosave_turns: int = 50
    auto_commit: bool = False

@dataclass
class BackgroundConfig:
    provider: str = "openai"
    model: str = "gpt-4o-mini"


@dataclass
class AppProviderConfig:
    openai: ProviderConfig = field(default_factory=ProviderConfig)
    anthropic: ProviderConfig = field(default_factory=ProviderConfig)
    openrouter: ProviderConfig = field(default_factory=ProviderConfig)
    chat: ChatConfig = field(default_factory=ChatConfig)
    background: BackgroundConfig = field(default_factory=BackgroundConfig)


class ProviderNotConfiguredError(Exception):
    """Raised when a requested provider is missing its API key."""


# ── Config loader ─────────────────────────────────────────────────────────────

_CONFIG_PATH = Path(__file__).parent.parent / "config" / "providers.yaml"


import logging
logger = logging.getLogger(__name__)

def _load_yaml() -> dict:
    if not _YAML_AVAILABLE:
        logger.warning("PyYAML not installed, skipping providers.yaml config load")
        return {}
    if not _CONFIG_PATH.exists():
        logger.info(f"Config file not found: {_CONFIG_PATH} (using env vars / defaults)")
        return {}
    with _CONFIG_PATH.open("r") as f:
        return yaml.safe_load(f) or {}


def load_config() -> AppProviderConfig:
    raw = _load_yaml()
    providers_raw = raw.get("providers", {})
    chat_raw = raw.get("chat", {})

    def _provider(name: str, env_var: str, base_url_default: str = "") -> ProviderConfig:
        """Merge YAML config + env override for a provider."""
        p = providers_raw.get(name, {})
        api_key = (
            os.environ.get(env_var)
            or p.get("api_key", "")
        )
        enabled = bool(api_key) and p.get("enabled", bool(api_key))
        return ProviderConfig(
            enabled=enabled,
            api_key=api_key,
            default_model=p.get("default_model", ""),
            base_url=p.get("base_url", base_url_default),
        )

    openai = _provider("openai", "OPENAI_API_KEY")
    anthropic = _provider("anthropic", "ANTHROPIC_API_KEY")
    openrouter = _provider(
        "openrouter", "OPENROUTER_API_KEY",
        base_url_default="https://openrouter.ai/api/v1",
    )

    chat = ChatConfig(
        default_provider=os.environ.get("SMRITI_DEFAULT_PROVIDER")
            or chat_raw.get("default_provider", "openrouter"),
        autosave_turns=int(chat_raw.get("autosave_turns", 50)),
        auto_commit=bool(chat_raw.get("auto_commit", False)),
    )
    
    bg_raw = raw.get("background_intelligence", {})
    background = BackgroundConfig(
        provider=bg_raw.get("provider", "openai"),
        model=bg_raw.get("model", "gpt-4o-mini")
    )

    return AppProviderConfig(
        openai=openai,
        anthropic=anthropic,
        openrouter=openrouter,
        chat=chat,
        background=background,
    )


# Singleton — loaded once at import time
_config: AppProviderConfig | None = None


def get_config() -> AppProviderConfig:
    global _config
    if _config is None:
        _config = load_config()
    return _config


def get_provider_config(provider: str) -> ProviderConfig:
    cfg = get_config()
    pc = getattr(cfg, provider.lower(), None)
    if pc is None:
        raise ProviderNotConfiguredError(f"Unknown provider: {provider}")
    if not pc.api_key:
        raise ProviderNotConfiguredError(
            f"Provider '{provider}' has no API key configured. "
            f"Set the environment variable or add it to config/providers.yaml."
        )
    return pc


def _check_package(provider: str) -> bool:
    try:
        if provider in ("openai", "openrouter"):
            import openai  # noqa
        elif provider == "anthropic":
            import anthropic  # noqa
        return False
    except ImportError:
        return True


def providers_status() -> dict[str, dict]:
    """Return a dict summarising which providers are enabled — safe to expose in API."""
    cfg = get_config()
    status = {
        name: {
            "enabled": getattr(cfg, name).enabled,
            "has_key": bool(getattr(cfg, name).api_key),
            "missing_package": _check_package(name),
            "configured": getattr(cfg, name).enabled and bool(getattr(cfg, name).api_key) and not _check_package(name),
            "status_label": "Ready" if getattr(cfg, name).enabled else "Disabled",
            "default_model": getattr(cfg, name).default_model,
        }
        for name in ("openai", "anthropic", "openrouter")
    }
    status["background_intelligence"] = {
        "provider": cfg.background.provider,
        "model": cfg.background.model,
        "enabled": True,
        "has_key": True,
        "missing_package": False,
        "configured": True,
        "status_label": "Ready",
    }
    return status
