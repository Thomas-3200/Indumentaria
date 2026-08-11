"""
lib/config_loader.py
─────────────────────────────────────────────────────────────────────────
Client config loader — reads clients/{slug}.json, validates structure,
resolves $ENV_VAR references, and caches results.

Usage:
  from lib import load_client_config, require_feature
  config = load_client_config("amapola")
  intake = require_feature("amapola", "intake")   # raises if disabled
─────────────────────────────────────────────────────────────────────────
"""
from __future__ import annotations

import json
import logging
import os
import threading
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)

# ── Paths ──────────────────────────────────────────────────────────────────────

_LIB_DIR     = Path(__file__).parent
_PROJECT_DIR = _LIB_DIR.parent
_CLIENTS_DIR = _PROJECT_DIR / "clients"

# ── Exceptions ─────────────────────────────────────────────────────────────────

class ConfigError(Exception):
    """Base config exception."""

class ClientNotFoundError(ConfigError):
    """clients/{slug}.json does not exist."""

class FeatureDisabledError(ConfigError):
    """A feature flag is explicitly set to false for this client."""
    def __init__(self, client_id: str, feature: str = "intake"):
        super().__init__(
            f"Feature '{feature}' is disabled for client '{client_id}'. "
            f"Set clients/{client_id}.json → {feature}.enabled = true to activate."
        )
        self.client_id = client_id
        self.feature   = feature

class MissingEnvVarError(ConfigError):
    """A required $ENV_VAR reference could not be resolved."""

# ── Validation constants ────────────────────────────────────────────────────────

_REQUIRED_TOP   = ["slug", "display_name"]
_VALID_PRIORITY = {"high", "medium", "low"}
_VALID_SOURCES  = {"whatsapp", "local_folder", "web_upload", "api"}
_VALID_TASKS    = {
    "PRODUCT_ENRICH", "DATA_CONFIRMATION", "MEDIA_REVIEW",
    "PLATFORM_ACTION", "APPROVAL", "FAILED_ACTION_REVIEW",
}

# ── Thread-safe in-process cache ───────────────────────────────────────────────

_cache:      dict[str, dict] = {}
_cache_lock: threading.Lock  = threading.Lock()

# ── Public API ─────────────────────────────────────────────────────────────────

def load_client_config(slug: str, resolve_env: bool = True) -> dict:
    """
    Load, validate and return the config dict for *slug*.

    Args:
        slug:        client identifier, e.g. "amapola"
        resolve_env: if True, replaces "$VAR_NAME" strings with os.environ values.
                     Unresolvable refs become None (they fail later at point-of-use).

    Raises:
        ClientNotFoundError  if clients/{slug}.json is missing.
        ConfigError          if the config file is structurally invalid.
    """
    cache_key = f"{slug}:{resolve_env}"
    with _cache_lock:
        if cache_key in _cache:
            return _cache[cache_key]

    path = _CLIENTS_DIR / f"{slug}.json"
    if not path.exists():
        available = sorted(
            p.stem for p in _CLIENTS_DIR.glob("*.json")
            if not p.stem.startswith("_")
        )
        raise ClientNotFoundError(
            f"Client '{slug}' not found. "
            f"Expected: {path}. "
            f"Available clients: {available}"
        )

    with open(path, encoding="utf-8") as fh:
        try:
            config = json.load(fh)
        except json.JSONDecodeError as exc:
            raise ConfigError(f"Invalid JSON in clients/{slug}.json: {exc}") from exc

    _validate(slug, config)

    if resolve_env:
        config = _resolve_env(config)

    with _cache_lock:
        _cache[cache_key] = config

    log.debug("Loaded config for client '%s'", slug)
    return config


def require_feature(client_id: str, feature: str = "intake") -> dict:
    """
    Load config and return the feature sub-dict.
    Raises FeatureDisabledError if feature.enabled is not True.

    Example:
        cfg = require_feature("amapola", "intake")
        grouping_strategy = cfg["grouping"]["strategy"]
    """
    config      = load_client_config(client_id)
    feature_cfg = config.get(feature, {})
    if not feature_cfg.get("enabled", False):
        raise FeatureDisabledError(client_id, feature)
    return feature_cfg


def list_clients() -> list[str]:
    """Return sorted list of all configured client slugs (excludes _template)."""
    return sorted(
        p.stem
        for p in _CLIENTS_DIR.glob("*.json")
        if not p.stem.startswith("_")
    )


def invalidate_cache(slug: str | None = None) -> None:
    """
    Clear the config cache.
    Pass slug to clear one client, or None to clear everything.
    """
    with _cache_lock:
        if slug is None:
            _cache.clear()
            log.debug("Config cache cleared (all clients)")
        else:
            keys = [k for k in _cache if k.startswith(f"{slug}:")]
            for k in keys:
                del _cache[k]
            log.debug("Config cache cleared for client '%s'", slug)


# ── Validation ─────────────────────────────────────────────────────────────────

def _validate(slug: str, config: dict) -> None:
    """Structural validation. Raises ConfigError on first violation."""

    # Required top-level keys
    for key in _REQUIRED_TOP:
        if key not in config:
            raise ConfigError(
                f"[{slug}] Missing required top-level key: '{key}'"
            )

    # slug must match filename
    if config["slug"] != slug:
        raise ConfigError(
            f"Config slug '{config['slug']}' does not match filename '{slug}.json'. "
            "They must be identical."
        )

    # Validate intake block (if present)
    intake = config.get("intake", {})
    if not isinstance(intake, dict):
        raise ConfigError(f"[{slug}] 'intake' must be an object.")

    # Source channel names
    for source_name in intake.get("sources", {}):
        if source_name not in _VALID_SOURCES:
            raise ConfigError(
                f"[{slug}] Unknown intake source '{source_name}'. "
                f"Valid: {sorted(_VALID_SOURCES)}"
            )

    # Task priority values
    task_defaults = intake.get("human_tasks", {}).get("default_priority", {})
    for task_type, priority in task_defaults.items():
        if task_type not in _VALID_TASKS:
            raise ConfigError(
                f"[{slug}] Unknown task type '{task_type}' in "
                "intake.human_tasks.default_priority."
            )
        if priority not in _VALID_PRIORITY:
            raise ConfigError(
                f"[{slug}] Invalid priority '{priority}' for task '{task_type}'. "
                f"Must be one of: {sorted(_VALID_PRIORITY)}"
            )


# ── Env reference resolution ────────────────────────────────────────────────────

def _resolve_env(obj: Any, _path: str = "root") -> Any:
    """
    Recursively replace "$VAR_NAME" strings with os.environ values.
    - Strings not starting with "$" are returned unchanged.
    - null / None values are returned unchanged.
    - Unresolvable env vars → None (not a hard error at load time;
      modules that actually need the value will raise clearly at point-of-use).
    """
    if isinstance(obj, dict):
        return {k: _resolve_env(v, f"{_path}.{k}") for k, v in obj.items()}
    if isinstance(obj, list):
        return [_resolve_env(item, f"{_path}[{i}]") for i, item in enumerate(obj)]
    if isinstance(obj, str) and obj.startswith("$") and len(obj) > 1:
        var_name = obj[1:]
        value    = os.environ.get(var_name)
        if value is None:
            log.debug(
                "Config ref $%s at %s not set in environment — resolved to None.",
                var_name, _path,
            )
        return value
    return obj
