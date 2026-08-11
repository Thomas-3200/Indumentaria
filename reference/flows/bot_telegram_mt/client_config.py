"""
Loader de configuración multi-tenant para el bot Telegram de Stepflow.

Uso:
    from client_config import load_client_config
    cfg = load_client_config("stylo_fino")
    cfg.client_uuid          # 202477af-...
    cfg.tg_bot_token         # leído de STYLO_FINO_TG_BOT_TOKEN
    cfg.tg_lead_user_id      # leído de STYLO_FINO_TG_LUCAS_USER_ID (legacy)
                             #         o STYLO_FINO_TG_LEAD_USER_ID
    cfg.tg_operator_user_id  # leído de STYLO_FINO_TG_LEO_USER_ID (legacy)
                             #         o STYLO_FINO_TG_OPERATOR_USER_ID
    cfg.wa_link
    cfg.timezone
    cfg.finance.default_settlement_model
    cfg.content.story_overlay_default

Resolución:
    1. Lee `clients/<slug>/client_config.json` (identidad NO secreta)
    2. Resuelve secretos del .env del repo usando env_prefix del JSON
       (fallback a nombres legacy si no encuentra los nuevos)

Compat: nombres legacy aceptados:
    STYLO_FINO_TG_LUCAS_USER_ID   ← STYLO_FINO_TG_LEAD_USER_ID
    STYLO_FINO_TG_LEO_USER_ID     ← STYLO_FINO_TG_OPERATOR_USER_ID
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional, Any

REPO_ROOT = Path(__file__).resolve().parents[2]


def _read_env_file(path: Path) -> dict[str, str]:
    out = {}
    if not path.exists():
        return out
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, _, v = line.partition("=")
            out[k.strip()] = v.strip()
    return out


def _resolve_env(env: dict, prefix: str, *candidates: str) -> Optional[str]:
    """Devuelve el primer env var no-vacío encontrado.
    candidates es lista de sufijos: ("TG_LEAD_USER_ID", "TG_LUCAS_USER_ID").
    """
    for suffix in candidates:
        key = f"{prefix}_{suffix}"
        val = env.get(key) or os.environ.get(key)
        if val:
            return val.strip()
    return None


@dataclass
class FinanceCfg:
    phase: str
    default_settlement_model: str
    default_stock_origin: str
    internal_split: dict


@dataclass
class ContentCfg:
    publish_mode: str
    platforms: list[str]
    story_overlay_default: str


@dataclass
class ClientConfig:
    slug: str
    display_name: str
    vertical: str
    client_uuid: str
    timezone: str
    env_prefix: str
    supabase_tables: dict
    # Telegram identity (resolved from env)
    tg_bot_token: Optional[str]
    tg_bot_username: Optional[str]
    tg_lead_user_id: Optional[int]
    tg_operator_user_id: Optional[int]
    tg_publish_chat_id: Optional[int]   # grupo dedicado para enviar kits (opcional)
    lead_role_name: str
    operator_role_name: str
    # Otros
    wa_link: Optional[str]
    finance: FinanceCfg
    content: ContentCfg
    # Supabase global (no por cliente, viene del .env)
    supabase_url: Optional[str] = None
    supabase_service_role_key: Optional[str] = None
    # Raw para acceso libre
    _raw: dict = field(default_factory=dict)


def load_client_config(slug: str, env_path: Optional[Path] = None) -> ClientConfig:
    """Carga config del cliente. Slug ej: 'stylo_fino'."""
    cfg_path = REPO_ROOT / "clients" / slug / "client_config.json"
    if not cfg_path.exists():
        raise FileNotFoundError(
            f"No existe {cfg_path}. Crear con la plantilla en "
            f"clients/_template_client_config.json"
        )
    raw = json.loads(cfg_path.read_text(encoding="utf-8"))

    env = _read_env_file(env_path or (REPO_ROOT / ".env"))
    prefix = raw.get("env_prefix") or slug.upper()

    # Telegram
    tg_token = _resolve_env(env, prefix, "TG_BOT_TOKEN")
    tg_lead_raw = _resolve_env(env, prefix, "TG_LEAD_USER_ID", "TG_LUCAS_USER_ID")
    tg_op_raw = _resolve_env(env, prefix, "TG_OPERATOR_USER_ID", "TG_LEO_USER_ID")
    tg_lead_id = int(tg_lead_raw) if tg_lead_raw and tg_lead_raw.isdigit() else None
    tg_op_id = int(tg_op_raw) if tg_op_raw and tg_op_raw.isdigit() else None
    # Grupo dedicado para publicaciones (negative ID para grupos). Opcional.
    tg_publish_raw = _resolve_env(env, prefix, "TG_PUBLISH_CHAT_ID")
    tg_publish_id = None
    if tg_publish_raw:
        try:
            tg_publish_id = int(tg_publish_raw.strip())
        except ValueError:
            tg_publish_id = None

    # WA link (prioriza env, luego JSON)
    wa_link = _resolve_env(env, prefix, "WA_LINK") or raw.get("wa_link")

    # Supabase global (no por cliente)
    sb_url = env.get("SUPABASE_URL") or os.environ.get("SUPABASE_URL")
    sb_key = env.get("SUPABASE_SERVICE_ROLE_KEY") or os.environ.get("SUPABASE_SERVICE_ROLE_KEY")

    fin = raw.get("finance", {})
    cnt = raw.get("content", {})
    tg = raw.get("telegram", {})

    return ClientConfig(
        slug=raw["slug"],
        display_name=raw.get("display_name", slug),
        vertical=raw.get("vertical", "unknown"),
        client_uuid=raw["client_uuid"],
        timezone=raw.get("timezone", "America/Argentina/Buenos_Aires"),
        env_prefix=prefix,
        supabase_tables=raw.get("supabase_tables", {}),
        tg_bot_token=tg_token,
        tg_bot_username=tg.get("bot_username"),
        tg_lead_user_id=tg_lead_id,
        tg_operator_user_id=tg_op_id,
        tg_publish_chat_id=tg_publish_id,
        lead_role_name=tg.get("lead_role_name", "Lead"),
        operator_role_name=tg.get("operator_role_name", "Operator"),
        wa_link=wa_link,
        finance=FinanceCfg(
            phase=fin.get("phase", "PHASE_1_VALIDATION"),
            default_settlement_model=fin.get("default_settlement_model", "PROFIT_SPLIT_50_50"),
            default_stock_origin=fin.get("default_stock_origin", "LUCAS_STOCK"),
            internal_split=fin.get("internal_split", {}),
        ),
        content=ContentCfg(
            publish_mode=cnt.get("publish_mode", "human_api"),
            platforms=cnt.get("platforms", ["instagram_post", "facebook_post"]),
            story_overlay_default=cnt.get("story_overlay_default", "Pedí info 👇"),
        ),
        supabase_url=sb_url,
        supabase_service_role_key=sb_key,
        _raw=raw,
    )


# CLI smoke test
if __name__ == "__main__":
    import sys
    sys.stdout.reconfigure(encoding='utf-8') if hasattr(sys.stdout, 'reconfigure') else None
    slug = sys.argv[1] if len(sys.argv) > 1 else "stylo_fino"
    cfg = load_client_config(slug)
    print(f"Cliente: {cfg.display_name} ({cfg.slug})")
    print(f"  UUID:           {cfg.client_uuid}")
    print(f"  env_prefix:     {cfg.env_prefix}")
    print(f"  TG bot token:   {'***SET***' if cfg.tg_bot_token else 'MISSING'}")
    print(f"  TG lead:        {cfg.tg_lead_user_id} ({cfg.lead_role_name})")
    print(f"  TG operator:    {cfg.tg_operator_user_id} ({cfg.operator_role_name})")
    print(f"  TG publish:     {cfg.tg_publish_chat_id or '(no configurado — usa chat 1-a-1 con operador)'}")
    print(f"  WA link:        {cfg.wa_link}")
    print(f"  Supabase URL:   {'***SET***' if cfg.supabase_url else 'MISSING'}")
    print(f"  Finance phase:  {cfg.finance.phase}")
    print(f"  Settlement:     {cfg.finance.default_settlement_model}")
    print(f"  Story overlay:  {cfg.content.story_overlay_default}")
