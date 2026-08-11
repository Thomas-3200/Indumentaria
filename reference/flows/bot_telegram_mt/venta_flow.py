"""
Flow conversacional del comando /venta para Stylo Fino.

State machine en memoria por user_id:
  ASK_PRODUCT → ASK_PRICE → ASK_COST → ASK_DIRECT_COSTS →
  ASK_SALE_ORIGIN → ASK_STOCK_ORIGIN → ASK_MODEL →
  CONFIRM → (insert Supabase) → DONE

Uso desde fetch_intake.py:
  - is_venta_active(user_id) → bool
  - start_venta(token, chat_id, user_id, args_text="")
  - handle_venta_text(token, chat_id, user_id, text) → bool (True si consumió el msg)
  - handle_venta_callback(token, cbq) → bool (True si consumió el callback)
"""
from __future__ import annotations

import json
import urllib.request
import urllib.error
from pathlib import Path
from typing import Any, Optional
from datetime import datetime, timezone, timedelta

# Reusar finance_calculator (mismo paquete)
from finance_calculator import (
    SaleData, calculate_sale_split, format_sale_summary_for_telegram,
    SALE_ORIGINS, _money,
)

# El bot de fetch_intake importa estas funciones; tg_send/tg_answer_callback se inyectan
# vía un dict TG (para no duplicar implementaciones HTTP).
TG: dict = {}  # se setea con register_tg_helpers() desde fetch_intake.py


def register_tg_helpers(tg_send, tg_answer_callback, tg_edit_message_text, env,
                        client_cfg=None):
    """env: dict con TOKEN + SUPABASE_URL + SUPABASE_SERVICE_ROLE_KEY (compat)
    client_cfg: instancia de ClientConfig (recomendado, multi-tenant).
    """
    TG["send"] = tg_send
    TG["ack"] = tg_answer_callback
    TG["edit"] = tg_edit_message_text
    TG["env"] = env
    TG["client_cfg"] = client_cfg  # opcional, si está usa client_uuid de acá


# Estado por user_id
_VENTA: dict[int, dict] = {}

STEP_PRODUCT = "ASK_PRODUCT"
STEP_PRICE = "ASK_PRICE"
STEP_COST = "ASK_COST"
STEP_DIRECT = "ASK_DIRECT_COSTS"
STEP_SALE_ORIGIN = "ASK_SALE_ORIGIN"
STEP_STOCK_ORIGIN = "ASK_STOCK_ORIGIN"
STEP_MODEL = "ASK_MODEL"
STEP_CONFIRM = "CONFIRM"


# LEGACY: CLIENT_UUID por compat — preferir TG["client_cfg"].client_uuid
# Si no hay client_cfg registrado, cae a este default (Stylo Fino).
CLIENT_UUID = "202477af-9207-4e09-b180-dca895df4743"
AR = timezone(timedelta(hours=-3))


def _client_uuid() -> str:
    """Resuelve client_uuid desde client_cfg si existe, sino del default legacy."""
    cfg = TG.get("client_cfg")
    if cfg is not None:
        return cfg.client_uuid
    return CLIENT_UUID


# ─────────────────────────────────────────────
# State helpers
# ─────────────────────────────────────────────

def is_venta_active(user_id: int) -> bool:
    return user_id in _VENTA


def _reset(user_id: int):
    _VENTA.pop(user_id, None)


def _parse_money(text: str) -> Optional[float]:
    """Acepta '45000', '45.000', '45,000', '$45.000,50' → 45000.50"""
    if text is None:
        return None
    s = text.strip().replace("$", "").replace(" ", "")
    if not s:
        return None
    # Si tiene tanto . como , → asumir formato AR (puntos miles, coma decimal)
    if "," in s and "." in s:
        s = s.replace(".", "").replace(",", ".")
    elif "," in s:
        # solo coma → si tiene exactamente 3 dígitos después → asumir miles (45,000)
        # si tiene 1 o 2 → decimal AR (45,50)
        parts = s.rsplit(",", 1)
        if len(parts[1]) == 3 and parts[1].isdigit():
            s = s.replace(",", "")
        else:
            s = s.replace(",", ".")
    # solo punto → puede ser miles (45.000) o decimal (45.50)
    elif s.count(".") == 1 and len(s.split(".")[1]) == 3:
        # punto como miles
        s = s.replace(".", "")
    try:
        return float(s)
    except ValueError:
        return None


# ─────────────────────────────────────────────
# Step renderers (mostrar pregunta + botones)
# ─────────────────────────────────────────────

def _ask_product(chat_id, user_id):
    sess = _VENTA[user_id]
    msg = (
        "🛒 <b>Nueva venta — paso 1/9</b>\n\n"
        "¿Qué producto se vendió?\n"
        "Mandame el <b>nombre o código</b> (ej. <code>Chaleco Nike Negro</code> o <code>REM-001</code>).\n\n"
        "Si querés salir: /cancelar"
    )
    TG["send"](TG["env"]["TOKEN"], chat_id, msg)
    sess["step"] = STEP_PRODUCT


def _ask_price(chat_id, user_id):
    sess = _VENTA[user_id]
    msg = (
        f"✅ Producto: <b>{sess['data']['product_name']}</b>\n\n"
        "💰 <b>Paso 2/9 — Precio de venta</b>\n"
        "¿Cuánto pagó el cliente? (sin descuentos ni cuotas)\n\n"
        "Mandame el número. Ej: <code>65000</code>"
    )
    TG["send"](TG["env"]["TOKEN"], chat_id, msg)
    sess["step"] = STEP_PRICE


def _ask_cost(chat_id, user_id):
    sess = _VENTA[user_id]
    msg = (
        f"Precio: {_money(sess['data']['gross_amount'])}\n\n"
        "📦 <b>Paso 3/9 — Costo del producto</b>\n"
        "¿Cuánto costó la prenda al proveedor?\n\n"
        "Mandame el número. Ej: <code>45000</code>\n"
        "(si no sabés exacto, poné el costo aproximado)"
    )
    TG["send"](TG["env"]["TOKEN"], chat_id, msg)
    sess["step"] = STEP_COST


def _ask_direct(chat_id, user_id):
    sess = _VENTA[user_id]
    msg = (
        f"Costo producto: {_money(sess['data']['product_cost'])}\n\n"
        "🚚 <b>Paso 4/9 — Costos directos extras</b>\n"
        "Suma de envío + packaging + comisión MP/débito + descuentos.\n\n"
        "Mandame el número total. Si no hubo, mandá <code>0</code>.\n"
        "Ej: <code>3000</code>"
    )
    TG["send"](TG["env"]["TOKEN"], chat_id, msg)
    sess["step"] = STEP_DIRECT


def _ask_sale_origin(chat_id, user_id):
    sess = _VENTA[user_id]
    msg = (
        f"Costos directos: {_money(sess['data']['direct_costs'])}\n\n"
        "📍 <b>Paso 5/9 — Origen de la venta</b>\n"
        "¿Cómo llegó el cliente?"
    )
    buttons = [
        [{"text": "📱 IG DM", "callback_data": "venta_o:INSTAGRAM_DM"},
         {"text": "💬 WA Estado", "callback_data": "venta_o:WHATSAPP_ESTADO"}],
        [{"text": "🔗 WA Redirect", "callback_data": "venta_o:WHATSAPP_REDIRECT"},
         {"text": "📘 FB Marketplace", "callback_data": "venta_o:FACEBOOK_MARKETPLACE"}],
        [{"text": "👥 FB Grupo", "callback_data": "venta_o:FACEBOOK_GRUPO"},
         {"text": "🏪 Local + Stepflow", "callback_data": "venta_o:LOCAL_CON_ORIGEN_STEPFLOW"}],
        [{"text": "🚶 Local sin Stepflow", "callback_data": "venta_o:LOCAL_DIRECTA_SIN_STEPFLOW"},
         {"text": "📦 Encargo", "callback_data": "venta_o:PEDIDO_POR_ENCARGO"}],
        [{"text": "❓ Revisión manual", "callback_data": "venta_o:REVISION_MANUAL"},
         {"text": "❌ Cancelar", "callback_data": "venta_o:_CANCEL"}],
    ]
    TG["send"](TG["env"]["TOKEN"], chat_id, msg, buttons=buttons)
    sess["step"] = STEP_SALE_ORIGIN


def _ask_stock_origin(chat_id, user_id):
    sess = _VENTA[user_id]
    msg = (
        f"Origen venta: <code>{sess['data']['sale_origin']}</code>\n\n"
        "📦 <b>Paso 6/9 — Origen del stock</b>\n"
        "¿De qué stock salió la prenda?"
    )
    buttons = [
        [{"text": "👤 Stock de Lucas", "callback_data": "venta_s:LUCAS_STOCK"}],
        [{"text": "🤝 Stock sociedad", "callback_data": "venta_s:SOCIEDAD_STOCK"}],
        [{"text": "📦 Encargo proveedor", "callback_data": "venta_s:PROVEEDOR_ENCARGO"}],
        [{"text": "❌ Cancelar", "callback_data": "venta_s:_CANCEL"}],
    ]
    TG["send"](TG["env"]["TOKEN"], chat_id, msg, buttons=buttons)
    sess["step"] = STEP_STOCK_ORIGIN


def _ask_model(chat_id, user_id):
    sess = _VENTA[user_id]
    # Sugerir default según stock_origin
    suggestion = ""
    if sess["data"]["stock_origin"] == "SOCIEDAD_STOCK":
        suggestion = "\n<i>(Sugerido: 33/33/33 porque es stock de sociedad)</i>"
    elif sess["data"]["stock_origin"] in ("LUCAS_STOCK", "PROVEEDOR_ENCARGO"):
        suggestion = "\n<i>(Sugerido: 50/50 sobre ganancia neta)</i>"

    msg = (
        f"Stock origin: <code>{sess['data']['stock_origin']}</code>\n\n"
        "⚖️ <b>Paso 7/9 — Modelo de reparto</b>\n"
        "¿Cómo se reparte la ganancia?" + suggestion
    )
    buttons = [
        [{"text": "50/50 ganancia neta (Fase 1)", "callback_data": "venta_m:PROFIT_SPLIT_50_50"}],
        [{"text": "33/33/33 sociedad (Fase 2)", "callback_data": "venta_m:PARTNERSHIP_33_33_33"}],
        [{"text": "⚠ Revisión manual", "callback_data": "venta_m:CUSTOM_REVIEW"}],
        [{"text": "❌ Cancelar", "callback_data": "venta_m:_CANCEL"}],
    ]
    TG["send"](TG["env"]["TOKEN"], chat_id, msg, buttons=buttons)
    sess["step"] = STEP_MODEL


def _ask_confirm(chat_id, user_id):
    sess = _VENTA[user_id]
    d = sess["data"]
    sale = SaleData(
        gross_amount=d["gross_amount"],
        product_cost=d["product_cost"],
        other_direct_costs=d["direct_costs"],
        sale_origin=d["sale_origin"],
        stock_origin=d["stock_origin"],
        settlement_model=d["settlement_model"],
        product_name=d["product_name"],
    )
    result = calculate_sale_split(sale)
    sess["preview_result"] = result
    sess["preview_sale"] = sale

    summary = format_sale_summary_for_telegram(sale, result)
    msg = (
        "🧮 <b>Paso 8/9 — Revisar cálculo</b>\n\n"
        + summary +
        "\n\n¿Confirmás y guardo la venta?"
    )
    buttons = [
        [{"text": "✅ Confirmar y guardar", "callback_data": "venta_c:YES"}],
        [{"text": "❌ Cancelar", "callback_data": "venta_c:NO"}],
    ]
    TG["send"](TG["env"]["TOKEN"], chat_id, msg, buttons=buttons)
    sess["step"] = STEP_CONFIRM


# ─────────────────────────────────────────────
# Supabase insert
# ─────────────────────────────────────────────

def _insert_to_supabase(sale: SaleData, result, sale_origin: str) -> tuple[bool, str]:
    env = TG["env"]
    sb_url = env.get("SUPABASE_URL")
    svc = env.get("SUPABASE_SERVICE_ROLE_KEY")
    if not sb_url or not svc:
        return False, "SUPABASE_URL o SERVICE_ROLE_KEY no configurados"

    body = {
        "client_id": _client_uuid(),
        "product_name": sale.product_name,
        "sale_date": datetime.now(AR).isoformat(),
        "sale_origin": sale_origin,
        "stock_origin": sale.stock_origin,
        "settlement_model": sale.settlement_model,
        "gross_amount": sale.gross_amount,
        "product_cost": sale.product_cost,
        "other_direct_costs": sale.other_direct_costs,
        "net_profit": result.net_profit,
        "lucas_cost_recovery": result.lucas_cost_recovery,
        "leo_cost_recovery": result.leo_cost_recovery,
        "tomi_cost_recovery": result.tomi_cost_recovery,
        "lucas_profit_share": result.lucas_profit_share,
        "leo_profit_share": result.leo_profit_share,
        "tomi_profit_share": result.tomi_profit_share,
        "stepflow_team_profit_share": result.stepflow_team_profit_share,
        "lucas_amount": result.lucas_amount,
        "leo_amount": result.leo_amount,
        "tomi_amount": result.tomi_amount,
        "stepflow_team_amount": result.stepflow_team_amount,
        "payment_status": "paid",
        "delivery_status": "delivered",
        "settlement_status": "disputed" if result.needs_review else "pending",
        "notes": result.review_reason or None,
    }
    headers = {
        "apikey": svc,
        "Authorization": f"Bearer {svc}",
        "Content-Type": "application/json",
        "Prefer": "return=representation",
    }
    req = urllib.request.Request(
        f"{sb_url}/rest/v1/sales",
        data=json.dumps(body).encode("utf-8"),
        headers=headers, method="POST",
    )
    try:
        resp = urllib.request.urlopen(req, timeout=15).read()
        rows = json.loads(resp)
        sale_id = rows[0]["id"] if rows else "?"
        return True, sale_id
    except urllib.error.HTTPError as e:
        return False, f"{e.code} {e.read().decode()[:300]}"
    except Exception as e:
        return False, str(e)


# ─────────────────────────────────────────────
# Public entry points
# ─────────────────────────────────────────────

def start_venta(chat_id: int, user_id: int, args_text: str = ""):
    _VENTA[user_id] = {
        "step": STEP_PRODUCT,
        "chat_id": chat_id,
        "data": {
            "product_name": None,
            "gross_amount": None,
            "product_cost": None,
            "direct_costs": 0.0,
            "sale_origin": None,
            "stock_origin": None,
            "settlement_model": None,
        },
        "started_at": datetime.now(AR).isoformat(),
    }
    if args_text and args_text.strip():
        # /venta Chaleco Nike Negro → saltea paso 1
        _VENTA[user_id]["data"]["product_name"] = args_text.strip()
        _ask_price(chat_id, user_id)
    else:
        _ask_product(chat_id, user_id)


def handle_venta_text(chat_id: int, user_id: int, text: str) -> bool:
    """Devuelve True si consumió el mensaje (estaba en flow de venta)."""
    if user_id not in _VENTA:
        return False

    sess = _VENTA[user_id]
    text = (text or "").strip()

    # Cancelar en cualquier momento
    if text.lower() in ("/cancelar", "/cancel", "cancelar", "cancel"):
        _reset(user_id)
        TG["send"](TG["env"]["TOKEN"], chat_id, "❌ Venta cancelada.")
        return True

    step = sess["step"]

    if step == STEP_PRODUCT:
        if len(text) < 2:
            TG["send"](TG["env"]["TOKEN"], chat_id, "Nombre muy corto. Mandá el nombre del producto o /cancelar.")
            return True
        sess["data"]["product_name"] = text
        _ask_price(chat_id, user_id)
        return True

    if step == STEP_PRICE:
        n = _parse_money(text)
        if n is None or n <= 0:
            TG["send"](TG["env"]["TOKEN"], chat_id,
                       "No entendí ese número. Mandá solo el monto, ej: <code>65000</code>")
            return True
        sess["data"]["gross_amount"] = n
        _ask_cost(chat_id, user_id)
        return True

    if step == STEP_COST:
        n = _parse_money(text)
        if n is None or n < 0:
            TG["send"](TG["env"]["TOKEN"], chat_id,
                       "No entendí ese número. Mandá solo el costo, ej: <code>45000</code>")
            return True
        sess["data"]["product_cost"] = n
        _ask_direct(chat_id, user_id)
        return True

    if step == STEP_DIRECT:
        n = _parse_money(text) if text not in ("0", "no", "ninguno", "n") else 0.0
        if n is None or n < 0:
            TG["send"](TG["env"]["TOKEN"], chat_id,
                       "No entendí. Mandá un número (0 si no hubo costos extras).")
            return True
        sess["data"]["direct_costs"] = n
        _ask_sale_origin(chat_id, user_id)
        return True

    # En los pasos con botones, ignoramos el texto y recordamos al user
    if step in (STEP_SALE_ORIGIN, STEP_STOCK_ORIGIN, STEP_MODEL, STEP_CONFIRM):
        TG["send"](TG["env"]["TOKEN"], chat_id,
                   "👆 Tocá uno de los botones de arriba para continuar (o /cancelar).")
        return True

    return False


def handle_venta_callback(cbq: dict) -> bool:
    """Devuelve True si consumió el callback."""
    data = cbq.get("data", "")
    if not data.startswith("venta_"):
        return False

    user_id = (cbq.get("from") or {}).get("id")
    chat_id = (cbq.get("message") or {}).get("chat", {}).get("id")
    cbq_id = cbq.get("id")
    token = TG["env"]["TOKEN"]

    if user_id not in _VENTA:
        TG["ack"](token, cbq_id, "⚠ Sesión de venta expirada. Empezá con /venta")
        return True

    sess = _VENTA[user_id]
    action, _, value = data.partition(":")

    # Cancel desde cualquier botón
    if value == "_CANCEL" or (action == "venta_c" and value == "NO"):
        _reset(user_id)
        TG["ack"](token, cbq_id, "Cancelado")
        TG["send"](token, chat_id, "❌ Venta cancelada.")
        return True

    if action == "venta_o" and sess["step"] == STEP_SALE_ORIGIN:
        if value not in SALE_ORIGINS:
            TG["ack"](token, cbq_id, "Origen no válido")
            return True
        sess["data"]["sale_origin"] = value
        TG["ack"](token, cbq_id, f"✓ {value}")
        _ask_stock_origin(chat_id, user_id)
        return True

    if action == "venta_s" and sess["step"] == STEP_STOCK_ORIGIN:
        if value not in ("LUCAS_STOCK", "SOCIEDAD_STOCK", "PROVEEDOR_ENCARGO"):
            TG["ack"](token, cbq_id, "Stock origin no válido")
            return True
        sess["data"]["stock_origin"] = value
        TG["ack"](token, cbq_id, f"✓ {value}")
        _ask_model(chat_id, user_id)
        return True

    if action == "venta_m" and sess["step"] == STEP_MODEL:
        if value not in ("PROFIT_SPLIT_50_50", "PARTNERSHIP_33_33_33", "CUSTOM_REVIEW"):
            TG["ack"](token, cbq_id, "Modelo no válido")
            return True
        sess["data"]["settlement_model"] = value
        TG["ack"](token, cbq_id, f"✓ {value}")
        _ask_confirm(chat_id, user_id)
        return True

    if action == "venta_c" and sess["step"] == STEP_CONFIRM:
        if value == "YES":
            TG["ack"](token, cbq_id, "Guardando…")
            sale = sess["preview_sale"]
            result = sess["preview_result"]
            ok, info = _insert_to_supabase(sale, result, sess["data"]["sale_origin"])
            if ok:
                badge = "⚠ disputed" if result.needs_review else "✅ pending"
                TG["send"](token, chat_id,
                           f"💾 <b>Venta guardada</b>\n\n"
                           f"ID: <code>{info}</code>\n"
                           f"Estado: {badge}\n"
                           f"Lucas: {_money(result.lucas_amount)} · "
                           f"Leo: {_money(result.leo_amount)} · "
                           f"Tomi: {_money(result.tomi_amount)}")
            else:
                TG["send"](token, chat_id,
                           f"❌ Error guardando venta:\n<code>{info[:300]}</code>\n\n"
                           "Probá de nuevo con /venta")
            _reset(user_id)
            return True

    TG["ack"](token, cbq_id, "")
    return True
