"""
Stylo Fino — Telegram Intake

Lee mensajes nuevos del bot @indumentariastylofino_bot, descarga fotos/videos
y guarda metadata estructurada en data/clients/stylo_fino/.
Responde a Lucas en el chat (confirmacion / ayuda / errores) para cerrar el loop.

Uso:
    # Una corrida (baja lo nuevo y sale)
    python flows/bot_telegram_mt/fetch_intake.py

    # Watch mode: long polling, dejalo corriendo en una terminal
    python flows/bot_telegram_mt/fetch_intake.py --watch

    # Solo replies, sin descargar nada (debug)
    python flows/bot_telegram_mt/fetch_intake.py --watch --no-replies

Variables de entorno requeridas (en .env):
    STYLO_FINO_TG_BOT_TOKEN
    STYLO_FINO_TG_LUCAS_USER_ID   (opcional; si está, filtra solo mensajes de Lucas)
"""

from __future__ import annotations

import json
import os
import re
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any

import urllib.request
import urllib.error

# Flow conversacional /venta
import venta_flow

# Forzar UTF-8 en consola Windows (Python 3.7+)
try:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except Exception:
    pass


# ─────────────────────────────────────────────
# Config
# ─────────────────────────────────────────────

REPO_ROOT = Path(__file__).resolve().parents[2]

# Multi-tenant: default Stylo Fino, override con --client SLUG en main()
# Estas globales se re-bindean desde _bind_client_paths(slug) al inicio de main().
CLIENT_SLUG = "stylo_fino"
CLIENT_DIR = REPO_ROOT / "data" / "clients" / CLIENT_SLUG
PRODUCTS_DIR = CLIENT_DIR / "products"
INBOX_DIR = CLIENT_DIR / "inbox"
LOG_FILE = CLIENT_DIR / "intake_log.jsonl"
OFFSET_FILE = CLIENT_DIR / ".last_update_id"
CLIENT_CFG = None  # ClientConfig instance (cargado en main())

TELEGRAM_API = "https://api.telegram.org"


def _bind_client_paths(slug: str):
    """Re-bindea las globals de paths al cliente indicado. Llamar antes de cualquier I/O."""
    global CLIENT_SLUG, CLIENT_DIR, PRODUCTS_DIR, INBOX_DIR, LOG_FILE, OFFSET_FILE
    global GROUP_INDEX_FILE
    CLIENT_SLUG = slug
    CLIENT_DIR = REPO_ROOT / "data" / "clients" / slug
    PRODUCTS_DIR = CLIENT_DIR / "products"
    INBOX_DIR = CLIENT_DIR / "inbox"
    LOG_FILE = CLIENT_DIR / "intake_log.jsonl"
    OFFSET_FILE = CLIENT_DIR / ".last_update_id"
    # GROUP_INDEX_FILE se define más abajo en el módulo; lo re-bindeamos también
    try:
        GROUP_INDEX_FILE = CLIENT_DIR / "product_groups.json"
    except NameError:
        pass


# ─────────────────────────────────────────────
# .env loader (sin dependencias)
# ─────────────────────────────────────────────

def load_env(env_path: Path) -> dict[str, str]:
    env: dict[str, str] = {}
    if not env_path.exists():
        return env
    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, _, v = line.partition("=")
        env[k.strip()] = v.strip()
    return env


# ─────────────────────────────────────────────
# Telegram API helpers
# ─────────────────────────────────────────────

def tg_get(token: str, method: str, **params: Any) -> dict[str, Any]:
    url = f"{TELEGRAM_API}/bot{token}/{method}"
    if params:
        qs = "&".join(f"{k}={urllib.parse.quote(str(v))}" for k, v in params.items())
        url = f"{url}?{qs}"
    req = urllib.request.Request(url, headers={"Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read().decode("utf-8"))


def tg_download(token: str, file_path: str, dest: Path) -> None:
    url = f"{TELEGRAM_API}/file/bot{token}/{file_path}"
    dest.parent.mkdir(parents=True, exist_ok=True)
    with urllib.request.urlopen(url, timeout=60) as resp, dest.open("wb") as f:
        f.write(resp.read())


# ─────────────────────────────────────────────
# Claude Vision — analiza la foto y devuelve metadata pre-llenada
# ─────────────────────────────────────────────

import base64

ANTHROPIC_API_KEY: str | None = None  # se setea en main() desde .env
OPENAI_API_KEY: str | None = None    # se setea en main() desde .env

# Cache del catálogo (se rebuildea cada cierto tiempo)
_CATALOG_CACHE: dict[str, Any] = {"items": [], "fetched_at": 0}


def _fetch_catalog_for_replies(env: dict) -> str:
    """Trae catálogo activo de Supabase y lo formatea para el prompt de GPT."""
    import time
    if time.time() - _CATALOG_CACHE.get("fetched_at", 0) < 600:
        return _CATALOG_CACHE.get("formatted", "")
    try:
        sb_url = env.get("SUPABASE_URL", "")
        sb_key = env.get("SUPABASE_SERVICE_ROLE_KEY", "")
        client_id = "202477af-9207-4e09-b180-dca895df4743"
        url = f"{sb_url}/rest/v1/client_products?client_id=eq.{client_id}&active=is.true&select=name,price,tags"
        r = urllib.request.Request(url, headers={"apikey": sb_key, "Authorization": f"Bearer {sb_key}"})
        rows = json.loads(urllib.request.urlopen(r, timeout=15).read())

        lines = []
        for p in rows:
            stock = "consultar"
            color = ""
            for t in p.get("tags") or []:
                if isinstance(t, str):
                    if t.startswith("color:"): color = t[6:]
                    elif t.startswith("stock_by_size:"):
                        try:
                            sbs = json.loads(t[14:])
                            stock = ", ".join(f"{k}:{v}" for k, v in sbs.items())
                        except Exception:
                            pass
            lines.append(f"- {p['name']} | precio ${p['price']:,} | color {color} | stock {stock}")
        formatted = "\n".join(lines)
        _CATALOG_CACHE["formatted"] = formatted
        _CATALOG_CACHE["fetched_at"] = time.time()
        return formatted
    except Exception as e:
        return f"(error cargando catálogo: {str(e)[:80]})"


def _reply_system_prompt() -> str:
    """REPLY_SYSTEM_PROMPT dinámico — usa display_name y lead_name del config."""
    vertical_blurb = ""
    if CLIENT_CFG is not None:
        v = getattr(CLIENT_CFG, "vertical", "")
        if v == "indumentaria_masculina":
            vertical_blurb = ", indumentaria masculina urbana"
        elif v:
            vertical_blurb = f", {v.replace('_', ' ')}"
    return REPLY_SYSTEM_PROMPT_TEMPLATE.format(
        display_name=_display_name(),
        vertical_blurb=vertical_blurb,
        lead_name=_lead_name(),
    )


REPLY_SYSTEM_PROMPT_TEMPLATE = """Sos asistente de {display_name}{vertical_blurb}. {lead_name} (el dueño) te reenvía un mensaje de un cliente, y tenés que sugerir UNA respuesta lista para que él copie/pegue al WhatsApp del cliente.

REGLAS:
1. Tono: rioplatense, masculino, directo, con onda. Sin "boludo", sin "che hermano".
2. SIEMPRE basate en el CATÁLOGO REAL que te paso. Nunca inventes productos, precios, talles o stock.
3. Si el cliente pregunta por un producto que NO está en el catálogo, decí que vas a consultar y volvés en un rato.
4. Si pregunta precio: respondé el precio del catálogo (acá SÍ va el precio, es WhatsApp privado).
5. Si pregunta talle: pedile altura y peso para recomendar.
6. Si pregunta envíos: "Hacemos envíos a todo el país. Costo según zona, te cotizo cuando me digas tu CP."
7. Si pregunta cambios: "Sí, hacemos cambios dentro de 7 días con etiqueta y sin uso."
8. Si pregunta cómo pagar: "Aceptamos efectivo, transferencia y MP."
9. Si quiere cerrar la venta: pedí nombre, forma de pago y si retira o envío.
10. Largo: 1-3 frases. Conciso. Sin filler.

Devolvés SOLO la respuesta sugerida, sin "Sugerencia:" ni comillas. Lista para copy/paste."""


def gpt_reply_suggestion(client_message: str, catalog: str) -> tuple[str | None, dict]:
    """Llama GPT-4o-mini con catálogo + mensaje del cliente, devuelve sugerencia."""
    if not OPENAI_API_KEY:
        return None, {"_error": "OPENAI_API_KEY no configurada"}

    user_msg = (
        f"CATÁLOGO ACTUAL DE STYLO FINO:\n{catalog}\n\n"
        f"---\nMENSAJE DEL CLIENTE A RESPONDER:\n\"{client_message}\"\n\n"
        f"Sugerí una respuesta corta para Lucas."
    )
    payload = json.dumps({
        "model": "gpt-4o-mini",
        "max_tokens": 250,
        "temperature": 0.7,
        "messages": [
            {"role": "system", "content": _reply_system_prompt()},
            {"role": "user", "content": user_msg},
        ],
    }).encode("utf-8")
    req = urllib.request.Request(
        "https://api.openai.com/v1/chat/completions",
        data=payload,
        headers={"Authorization": f"Bearer {OPENAI_API_KEY}", "Content-Type": "application/json"},
    )
    try:
        r = json.loads(urllib.request.urlopen(req, timeout=30).read())
        text = r["choices"][0]["message"]["content"].strip()
        if text.startswith('"') and text.endswith('"'):
            text = text[1:-1]
        return text, r.get("usage", {})
    except urllib.error.HTTPError as e:
        return None, {"_error": f"HTTP {e.code}: {e.read().decode()[:200]}"}
    except Exception as e:
        return None, {"_error": str(e)[:200]}

VISION_SYSTEM = (
    "Sos un asistente que clasifica fotos de prendas de indumentaria "
    "masculina para una tienda online. Respondés SOLO con JSON válido, "
    "sin markdown, sin explicaciones. Si no podés identificar algo, dejá "
    "el campo en null."
)

VISION_USER = (
    "Mirá esta foto de una prenda y devolveme este JSON exacto:\n\n"
    "{\n"
    '  "category": "remera | buzo | campera | chaleco | pantalon | short | conjunto | accesorio | otro",\n'
    '  "color_principal": "string (un solo color, ej: negro, gris, azul)",\n'
    '  "colores_extra": ["array de colores secundarios visibles"],\n'
    '  "marca_visible": "string o null (ej: Nike, Adidas, sin marca visible)",\n'
    '  "estilo": "string corto (ej: streetwear, urbano, deportivo, casual)",\n'
    '  "descripcion": "string de 1-2 frases comerciales para post de IG",\n'
    '  "nombre_sugerido": "string corto, máx 4 palabras (ej: Chaleco Nike Negro)",\n'
    '  "codigo_sugerido": "string MAYUS-MAYUS-NNN (ej: CHA-NEG-001)"\n'
    "}\n\n"
    "El código sugerido es: 3 letras de categoría + 3 letras de color principal + 001."
)


def analyze_photo(image_path: Path) -> dict[str, Any] | None:
    """Envía la imagen a Claude Haiku Vision y devuelve la metadata sugerida."""
    if not ANTHROPIC_API_KEY:
        return None
    if not image_path.exists():
        return None
    # Codificar imagen
    img_bytes = image_path.read_bytes()
    img_b64 = base64.b64encode(img_bytes).decode("ascii")
    media_type = "image/jpeg" if image_path.suffix.lower() in (".jpg", ".jpeg") else "image/png"

    payload = json.dumps({
        "model": "claude-haiku-4-5",
        "max_tokens": 1200,   # subido para no truncar respuestas con arrays largos
        "system": VISION_SYSTEM,
        "messages": [{
            "role": "user",
            "content": [
                {"type": "image", "source": {
                    "type": "base64", "media_type": media_type, "data": img_b64
                }},
                {"type": "text", "text": VISION_USER},
            ],
        }],
    }).encode("utf-8")

    req = urllib.request.Request(
        "https://api.anthropic.com/v1/messages",
        data=payload,
        headers={
            "x-api-key": ANTHROPIC_API_KEY,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        },
    )
    try:
        r = urllib.request.urlopen(req, timeout=30)
        body = json.loads(r.read())
        text = body["content"][0]["text"].strip()
        # Limpiar markdown
        if text.startswith("```"):
            text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text, flags=re.MULTILINE).strip()
        parsed = json.loads(text)
        # Si Claude devuelve un array (foto con múltiples productos),
        # tomamos el PRIMER producto y agregamos flag para revisión manual.
        if isinstance(parsed, list):
            if not parsed:
                return {"_error": "respuesta lista vacía"}
            multi_count = len(parsed)
            parsed = parsed[0]
            parsed["_multi_products_detected"] = multi_count
            parsed["_needs_manual_review"] = True
        elif not isinstance(parsed, dict):
            return {"_error": f"respuesta tipo inesperado: {type(parsed).__name__}"}
        parsed["_ai_model"] = body.get("model", "")
        parsed["_ai_tokens_in"] = body.get("usage", {}).get("input_tokens", 0)
        parsed["_ai_tokens_out"] = body.get("usage", {}).get("output_tokens", 0)
        return parsed
    except urllib.error.HTTPError as e:
        return {"_error": f"HTTP {e.code}", "_details": e.read().decode()[:300]}
    except Exception as e:
        return {"_error": str(e)[:200]}


def tg_send(token: str, chat_id: int | str, text: str, reply_to: int | None = None,
            buttons: list[list[dict]] | None = None) -> int | None:
    """Envia un mensaje al chat. Devuelve message_id si OK.
    buttons: lista de filas, cada fila lista de {text, callback_data}.
    """
    if not REPLIES_ENABLED:
        return None
    url = f"{TELEGRAM_API}/bot{token}/sendMessage"
    data = {
        "chat_id": chat_id,
        "text": text,
        "parse_mode": "HTML",
        "disable_web_page_preview": True,
    }
    if reply_to:
        data["reply_to_message_id"] = reply_to
    if buttons:
        data["reply_markup"] = {"inline_keyboard": buttons}
    payload = json.dumps(data).encode("utf-8")
    req = urllib.request.Request(url, data=payload,
                                 headers={"Content-Type": "application/json"})
    try:
        r = json.loads(urllib.request.urlopen(req, timeout=15).read())
        return r.get("result", {}).get("message_id")
    except Exception as exc:
        print(f"  ↳ tg_send error: {exc}")
        return None


def tg_send_photo(token: str, chat_id: int | str, photo_url: str, caption: str = "",
                  buttons: list[list[dict]] | None = None) -> int | None:
    if not REPLIES_ENABLED:
        return None
    url = f"{TELEGRAM_API}/bot{token}/sendPhoto"
    data = {"chat_id": chat_id, "photo": photo_url, "caption": caption,
            "parse_mode": "HTML"}
    if buttons:
        data["reply_markup"] = {"inline_keyboard": buttons}
    payload = json.dumps(data).encode("utf-8")
    req = urllib.request.Request(url, data=payload,
                                 headers={"Content-Type": "application/json"})
    try:
        r = json.loads(urllib.request.urlopen(req, timeout=20).read())
        return r.get("result", {}).get("message_id")
    except Exception as exc:
        print(f"  ↳ tg_send_photo error: {exc}")
        return None


def tg_answer_callback(token: str, callback_query_id: str, text: str = "") -> None:
    """Responde al callback_query (popup pequeño en Telegram)."""
    url = f"{TELEGRAM_API}/bot{token}/answerCallbackQuery"
    data = {"callback_query_id": callback_query_id}
    if text:
        data["text"] = text
        data["show_alert"] = False
    payload = json.dumps(data).encode("utf-8")
    req = urllib.request.Request(url, data=payload,
                                 headers={"Content-Type": "application/json"})
    try:
        urllib.request.urlopen(req, timeout=10).read()
    except Exception as exc:
        print(f"  ↳ tg_answer_callback error: {exc}")


def tg_edit_message_text(token: str, chat_id: int | str, message_id: int,
                         text: str, buttons: list | None = None) -> None:
    url = f"{TELEGRAM_API}/bot{token}/editMessageText"
    data = {"chat_id": chat_id, "message_id": message_id, "text": text,
            "parse_mode": "HTML", "disable_web_page_preview": True}
    if buttons is not None:
        data["reply_markup"] = {"inline_keyboard": buttons}
    payload = json.dumps(data).encode("utf-8")
    req = urllib.request.Request(url, data=payload,
                                 headers={"Content-Type": "application/json"})
    try:
        urllib.request.urlopen(req, timeout=10).read()
    except Exception as exc:
        print(f"  ↳ tg_edit error: {exc}")


def tg_edit_caption(token: str, chat_id: int | str, message_id: int,
                    caption: str, buttons: list | None = None) -> None:
    url = f"{TELEGRAM_API}/bot{token}/editMessageCaption"
    data = {"chat_id": chat_id, "message_id": message_id, "caption": caption,
            "parse_mode": "HTML"}
    if buttons is not None:
        data["reply_markup"] = {"inline_keyboard": buttons}
    payload = json.dumps(data).encode("utf-8")
    req = urllib.request.Request(url, data=payload,
                                 headers={"Content-Type": "application/json"})
    try:
        urllib.request.urlopen(req, timeout=10).read()
    except Exception as exc:
        print(f"  ↳ tg_edit_caption error: {exc}")


# ─────────────────────────────────────────────
# Mensajes que el bot le manda a Lucas
# ─────────────────────────────────────────────

REPLIES_ENABLED = True  # se sobreescribe desde main() con --no-replies

def _display_name() -> str:
    """Helper para inyectar nombre del cliente en mensajes."""
    if CLIENT_CFG is not None and getattr(CLIENT_CFG, "display_name", None):
        return CLIENT_CFG.display_name
    return "Stylo Fino"  # default legacy


def _lead_name() -> str:
    if CLIENT_CFG is not None and getattr(CLIENT_CFG, "lead_role_name", None):
        return CLIENT_CFG.lead_role_name
    return "Lucas"


def _welcome_msg() -> str:
    return (
        f"¡Hola! Soy el bot de carga de stock de <b>{_display_name()}</b>.\n\n"
        "Mandame los productos así, uno por uno:\n\n"
        "<pre>PRODUCTO\n"
        "Código: REM-NEG-001\n"
        "Nombre: Remera Boxy Negra\n"
        "Categoría: remera\n"
        "Precio: 45000\n"
        "Colores: negro\n"
        "Talles: S, M, L, XL\n"
        "Stock: S 2 / M 4 / L 3 / XL 1</pre>\n\n"
        "Y después mandame 1 a 5 fotos del producto.\n\n"
        "Para avisar movimientos:\n"
        "<code>Vendido REM-NEG-001 talle M cantidad 1</code>\n"
        "<code>Sin stock REM-NEG-001</code>\n"
        "<code>Agregar stock REM-NEG-001 L 2</code>\n\n"
        "Mandá /ayuda en cualquier momento."
    )


WELCOME_MSG = (
    "¡Hola! Soy el bot de carga de stock de <b>Stylo Fino</b>.\n\n"
    "Mandame los productos así, uno por uno:\n\n"
    "<pre>PRODUCTO\n"
    "Código: REM-NEG-001\n"
    "Nombre: Remera Boxy Negra\n"
    "Categoría: remera\n"
    "Precio: 45000\n"
    "Colores: negro\n"
    "Talles: S, M, L, XL\n"
    "Stock: S 2 / M 4 / L 3 / XL 1</pre>\n\n"
    "Y después mandame 1 a 5 fotos del producto.\n\n"
    "Para avisar movimientos:\n"
    "<code>Vendido REM-NEG-001 talle M cantidad 1</code>\n"
    "<code>Sin stock REM-NEG-001</code>\n"
    "<code>Agregar stock REM-NEG-001 L 2</code>\n\n"
    "Mandá /ayuda en cualquier momento."
)

UNKNOWN_TEXT_MSG = (
    "No entendí ese mensaje 🤔\n"
    "Mandá /ayuda para ver el formato, o pegá un bloque que empiece con "
    "<b>PRODUCTO</b>."
)

FIRST_PHOTO_MSG = (
    "Recibido. Voy a procesar todas las fotos en silencio.\n"
    "Cuando termines de mandar todas, escribime <b>LISTO</b> y te paso "
    "el link del formulario para completar precios y stock."
)

SESSION_SUMMARY_MSG = (
    "✅ <b>Sesión cerrada</b>\n\n"
    "📸 Fotos recibidas: {photos}\n"
    "🛍️ Productos detectados: {groups}\n\n"
    "<b>Detalle:</b>\n"
    "{group_lines}\n\n"
    "Abrí este link para completar precio, talles y stock:\n"
    "{form_url}\n\n"
    "Vas a poder editar todo si la IA detectó algo mal."
)


# ─────────────────────────────────────────────
# Message parsers
# ─────────────────────────────────────────────

PRODUCT_HEADER = re.compile(r"^\s*PRODUCTO\s*$", re.IGNORECASE | re.MULTILINE)
FIELD_LINE = re.compile(r"^\s*([A-Za-zÁÉÍÓÚáéíóúñÑ]+)\s*:\s*(.+?)\s*$")
# Conectores que NO son talles aunque parezcan letras
_NOT_A_SIZE = {"Y", "E", "O", "U", "DE", "CON", "DEL", "AL"}


def _parse_stock_string(s: str) -> dict[str, int]:
    """
    Tolera formatos variados:
      - "S 2 / M 4 / L 3 / XL 1"   (canónico SIZE QTY)
      - "S:2, M:4, L:3, XL:1"
      - "1S 2M 4L 6XL"             (QTY pegada al talle)
      - "1S. 2M. 4L Y 6XL"         (como Lucas: puntos y "Y")
      - "S2 M4 L3 XL1"             (pegado, ambiguo)
    """
    if not s:
        return {}
    # Normalizar separadores: .,/:  y la "Y" conectora → espacio
    normalized = re.sub(r"[.,/:]", " ", s)
    normalized = re.sub(r"\b[Yy]\b", " ", normalized)
    # Insertar espacio entre letra-dígito y dígito-letra para que "S2" → "S 2"
    normalized = re.sub(r"([A-Za-z])(\d)", r"\1 \2", normalized)
    normalized = re.sub(r"(\d)([A-Za-z])", r"\1 \2", normalized)
    normalized = re.sub(r"\s+", " ", normalized).strip()
    if not normalized:
        return {}

    by_size: dict[str, int] = {}
    # Decidir el orden mirando el primer token: si empieza con dígito → QTY SIZE.
    first = normalized.split()[0]
    qty_first = first.isdigit()

    if qty_first:
        pattern = re.compile(r"(\d+)\s+([A-Za-z]{1,4})\b")
        for m in pattern.finditer(normalized):
            size = m.group(2).upper()
            if size in _NOT_A_SIZE:
                continue
            by_size[size] = int(m.group(1))
    else:
        pattern = re.compile(r"\b([A-Za-z]{1,4})\s+(\d+)")
        for m in pattern.finditer(normalized):
            size = m.group(1).upper()
            if size in _NOT_A_SIZE:
                continue
            by_size[size] = int(m.group(2))

    return by_size


def _parse_sizes_string(s: str) -> list[str]:
    """Extrae solo letras de los talles, ignorando números/puntuación/conectores."""
    if not s:
        return []
    raw = re.split(r"[,/\s]+", s)
    out: list[str] = []
    seen: set[str] = set()
    for token in raw:
        # Quitar todo lo que no sea letra (incluido tildes y dígitos)
        letters_only = re.sub(r"[^A-Za-zÁÉÍÓÚáéíóúÑñÜü]", "", token).upper()
        # Normalizar tildes en mayúsculas
        for a, b in (("Á","A"),("É","E"),("Í","I"),("Ó","O"),("Ú","U"),("Ü","U"),("Ñ","N")):
            letters_only = letters_only.replace(a, b)
        if letters_only and letters_only not in _NOT_A_SIZE and letters_only not in seen:
            out.append(letters_only)
            seen.add(letters_only)
    return out

STOCK_UPDATE_PATTERNS = [
    (re.compile(r"^vendido\s+(\S+)\s+talle\s+(\S+)\s+cantidad\s+(\d+)", re.IGNORECASE),
     lambda m: {"action": "sale", "code": m.group(1), "size": m.group(2).upper(), "qty": int(m.group(3))}),
    (re.compile(r"^sin\s+stock\s+(\S+)", re.IGNORECASE),
     lambda m: {"action": "set_zero", "code": m.group(1)}),
    (re.compile(r"^stock\s+(\S+)\s+(\S+)\s+(\d+)", re.IGNORECASE),
     lambda m: {"action": "set", "code": m.group(1), "size": m.group(2).upper(), "qty": int(m.group(3))}),
    (re.compile(r"^agregar\s+stock\s+(\S+)\s+(?:talle\s+)?(\S+)\s+(\d+)", re.IGNORECASE),
     lambda m: {"action": "restock", "code": m.group(1), "size": m.group(2).upper(), "qty": int(m.group(3))}),
]


def parse_product_block(text: str) -> dict[str, Any] | None:
    if not PRODUCT_HEADER.search(text):
        return None
    fields: dict[str, str] = {}
    for line in text.splitlines():
        m = FIELD_LINE.match(line)
        if m:
            fields[m.group(1).lower().strip()] = m.group(2).strip()

    code = fields.get("código") or fields.get("codigo")
    if not code:
        return None

    # STOCK — tolera múltiples formatos
    stock_raw = fields.get("stock", "")
    stock_by_size = _parse_stock_string(stock_raw)

    # TALLES — extrae solo letras
    sizes_raw = fields.get("talles", "")
    sizes = _parse_sizes_string(sizes_raw)

    # Fallback: si Lucas puso stock dentro del campo "Talles" (porque puso
    # números ahí), intentar extraerlo
    if not stock_by_size and re.search(r"\d", sizes_raw):
        stock_by_size = _parse_stock_string(sizes_raw)

    # COLORES — split por coma o slash
    colors_raw = fields.get("colores", "")
    colors = [c.strip().lower() for c in re.split(r"[,/]", colors_raw) if c.strip()]

    try:
        price = int(re.sub(r"[^\d]", "", fields.get("precio", "0")) or "0")
    except ValueError:
        price = 0

    return {
        "code": code,
        "name": fields.get("nombre", ""),
        "category": fields.get("categoría", fields.get("categoria", "")).lower(),
        "price": price,
        "currency": "ARS",
        "colors": colors,
        "sizes": sizes or list(stock_by_size.keys()),
        "stock_by_size": stock_by_size,
        "total_stock": sum(stock_by_size.values()),
        "status": "active" if sum(stock_by_size.values()) > 0 else "out_of_stock",
    }


def parse_stock_update(text: str) -> dict[str, Any] | None:
    line = text.strip().splitlines()[0] if text.strip() else ""
    for pattern, builder in STOCK_UPDATE_PATTERNS:
        m = pattern.match(line)
        if m:
            return builder(m)
    return None


# ─────────────────────────────────────────────
# Product grouping — agrupa fotos sucesivas del MISMO producto
# ─────────────────────────────────────────────

GROUP_INDEX_FILE = CLIENT_DIR / "product_groups.json"
GROUP_TIME_WINDOW_SEC = 90  # fotos que llegan en <90s con mismo cat+color se agrupan
_PG_CACHE: dict[str, Any] = {}


def _load_groups() -> dict[str, Any]:
    """Carga el índice de grupos desde disco. Estructura:
       { "groups": [{ "id": "...", "category": "...", "color": "...",
                       "brand": "...", "last_photo_ts": "...", "photos": [] }],
         "next_seq": 1 }
    """
    global _PG_CACHE
    if _PG_CACHE:
        return _PG_CACHE
    if GROUP_INDEX_FILE.exists():
        _PG_CACHE = json.loads(GROUP_INDEX_FILE.read_text(encoding="utf-8"))
    else:
        _PG_CACHE = {"groups": [], "next_seq": 1}
    return _PG_CACHE


def _save_groups() -> None:
    GROUP_INDEX_FILE.parent.mkdir(parents=True, exist_ok=True)
    GROUP_INDEX_FILE.write_text(
        json.dumps(_PG_CACHE, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def _norm(v: Any) -> str:
    return str(v or "").strip().lower()


def assign_product_group(ai_data: dict[str, Any], photo_ref: str) -> dict[str, Any]:
    """Devuelve {group_id, group_seq, group_status} para esta foto.

    Si encuentra un grupo abierto (<90s) con misma category+color → la suma.
    Si no, crea un grupo nuevo.
    """
    state = _load_groups()
    now = datetime.now(timezone.utc)
    cat = _norm(ai_data.get("category"))
    color = _norm(ai_data.get("color_principal"))
    brand = _norm(ai_data.get("marca_visible"))

    # Buscar último grupo abierto que matchee (categoría + color + marca)
    # Sin marca → solo cat+color. Con marca → cat+color+brand.
    match = None
    for g in reversed(state["groups"]):
        try:
            last_ts = datetime.fromisoformat(g["last_photo_ts"].replace("Z", "+00:00"))
        except Exception:
            continue
        if (now - last_ts).total_seconds() > GROUP_TIME_WINDOW_SEC:
            continue
        if g.get("category") != cat or g.get("color") != color:
            continue
        # Si ambas tienen marca, deben coincidir. Si una no tiene marca, no matchear
        # (mejor crear grupo separado que mezclar)
        if brand and g.get("brand") and g.get("brand") != brand:
            continue
        if (brand and not g.get("brand")) or (g.get("brand") and not brand):
            continue
        match = g
        break

    if match:
        match["photos"].append(photo_ref)
        match["last_photo_ts"] = now_iso()
        result = {
            "group_id": match["id"],
            "group_seq": match["seq"],
            "group_status": "merged",
            "photos_in_group": len(match["photos"]),
        }
    else:
        seq = state["next_seq"]
        new_group = {
            "id": f"PG-{seq:03d}",
            "seq": seq,
            "category": cat,
            "color": color,
            "brand": brand,
            "first_photo_ts": now_iso(),
            "last_photo_ts": now_iso(),
            "photos": [photo_ref],
            "tagged": False,
        }
        state["groups"].append(new_group)
        state["next_seq"] = seq + 1
        result = {
            "group_id": new_group["id"],
            "group_seq": seq,
            "group_status": "new",
            "photos_in_group": 1,
        }

    _save_groups()
    return result


# ─────────────────────────────────────────────
# Storage
# ─────────────────────────────────────────────

def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def append_log(entry: dict[str, Any]) -> None:
    LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
    with LOG_FILE.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")


def upsert_product_meta(product: dict[str, Any]) -> Path:
    pdir = PRODUCTS_DIR / product["code"]
    pdir.mkdir(parents=True, exist_ok=True)
    meta_path = pdir / "meta.json"
    if meta_path.exists():
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
    else:
        meta = {"assets": [], "received_from": "lucas", "first_seen_at": now_iso()}
    meta.update({k: v for k, v in product.items() if k != "assets"})
    meta["last_updated"] = now_iso()
    meta_path.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    return pdir


def attach_asset(code: str, file_name: str, asset_type: str, msg_id: int) -> Path:
    pdir = PRODUCTS_DIR / code
    pdir.mkdir(parents=True, exist_ok=True)
    meta_path = pdir / "meta.json"
    meta = json.loads(meta_path.read_text(encoding="utf-8")) if meta_path.exists() else {
        "code": code, "assets": [], "received_from": "lucas", "first_seen_at": now_iso()
    }
    meta.setdefault("assets", []).append({
        "file": file_name,
        "type": asset_type,
        "received_at": now_iso(),
        "telegram_msg_id": msg_id,
    })
    meta["last_updated"] = now_iso()
    meta_path.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    return pdir / file_name


# ─────────────────────────────────────────────
# Update processor
# ─────────────────────────────────────────────

def get_offset() -> int:
    if OFFSET_FILE.exists():
        try:
            return int(OFFSET_FILE.read_text().strip())
        except ValueError:
            return 0
    return 0


def set_offset(value: int) -> None:
    OFFSET_FILE.parent.mkdir(parents=True, exist_ok=True)
    OFFSET_FILE.write_text(str(value), encoding="utf-8")


# Memoria volátil del último product_code visto en la sesión, para asociar
# fotos sueltas que vienen DESPUÉS del bloque PRODUCTO.
_LAST_CODE_BY_USER: dict[int, str] = {}


# ─────────────────────────────────────────────
# Sesiones de intake (silenciosas hasta LISTO o idle)
# ─────────────────────────────────────────────

_SESSION_IDLE_SEC = 180  # 3 min sin foto → auto-cerrar sesión
_SESSIONS: dict[int, dict[str, Any]] = {}


def _get_session(user_id: int) -> dict[str, Any]:
    if user_id not in _SESSIONS:
        _SESSIONS[user_id] = {
            "started_at": None,
            "last_photo_ts": None,
            "photos": 0,
            "groups": [],   # lista de group_ids vistos en esta sesión
            "greeting_sent": False,
            "link_sent": False,
            "chat_id": None,
        }
    return _SESSIONS[user_id]


def _reset_session(user_id: int) -> None:
    _SESSIONS.pop(user_id, None)


def _form_url() -> str:
    """Resuelve el URL del form de tagueo según el cliente.
    Busca: <CLIENT_ENV_PREFIX>_FORM_URL → STYLOFINO_FORM_URL (legacy) → default.
    """
    if CLIENT_CFG is not None:
        key = f"{CLIENT_CFG.env_prefix}_FORM_URL"
        v = os.environ.get(key)
        if v:
            return v
    return os.environ.get(
        "STYLOFINO_FORM_URL",
        "https://n8n.agenciaiasm.online/webhook/stylofino-tag",
    )


def _close_session(token: str, user_id: int, chat_id: int) -> None:
    """Envía resumen + link y resetea la sesión. También dispara sync a Supabase."""
    sess = _SESSIONS.get(user_id)
    if not sess or sess.get("link_sent") or sess["photos"] == 0:
        return

    # Construir resumen de grupos
    state = _load_groups()
    groups_in_session = [g for g in state["groups"] if g["id"] in sess["groups"]]
    lines = []
    for g in groups_in_session:
        brand = g.get("brand") or ""
        brand_suffix = f" · {brand}" if brand else ""
        lines.append(f"  #{g['seq']} — {g['category']} {g['color']}{brand_suffix} ({len(g['photos'])} fotos)")
    detail = "\n".join(lines) if lines else "  (ninguno)"

    msg = SESSION_SUMMARY_MSG.format(
        photos=sess["photos"],
        groups=len(sess["groups"]),
        group_lines=detail,
        form_url=_form_url(),
    )
    tg_send(token, chat_id, msg)
    sess["link_sent"] = True
    print(f"  ↳ SESIÓN CERRADA usuario={user_id} fotos={sess['photos']} grupos={len(sess['groups'])}")

    # Auto-disparar sync a Supabase en background (fire-and-forget)
    # para que las fotos nuevas aparezcan en el form sin intervención manual.
    try:
        import subprocess
        sync_script = REPO_ROOT / "flows" / "bot_telegram_mt" / "sync_to_supabase.py"
        if sync_script.exists():
            # Pasar --client SLUG para que sync_to_supabase use el cliente correcto
            cmd = [sys.executable, str(sync_script), "--client", CLIENT_SLUG]
            subprocess.Popen(
                cmd,
                cwd=str(REPO_ROOT),
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                start_new_session=True if hasattr(subprocess, "DEVNULL") else False,
            )
            tg_send(token, chat_id,
                    "🔄 <i>Sincronizando con el sistema... Las fotos aparecerán en el formulario en ~1 minuto.</i>")
            print(f"  ↳ Sync a Supabase disparado en background")
    except Exception as e:
        print(f"  ↳ Error disparando sync: {e}")


def check_idle_sessions(token: str) -> None:
    """Llamar entre polls. Cierra sesiones con >3min de inactividad."""
    now = datetime.now(timezone.utc)
    for uid, sess in list(_SESSIONS.items()):
        if sess.get("link_sent") or not sess.get("last_photo_ts"):
            continue
        try:
            last = datetime.fromisoformat(sess["last_photo_ts"].replace("Z", "+00:00"))
        except Exception:
            continue
        if (now - last).total_seconds() > _SESSION_IDLE_SEC:
            chat_id = sess.get("chat_id")
            if chat_id:
                _close_session(token, uid, chat_id)


_DONE_KEYWORDS = {
    "listo", "ya", "termine", "terminé", "termino", "ok", "ya está", "ya esta",
    "all done", "done", "fin", "terminado", "todas listas",
}


def _is_done_command(text: str) -> bool:
    if not text:
        return False
    cleaned = text.strip().lower().rstrip("!.")
    cleaned = re.sub(r"^/", "", cleaned)
    return cleaned in _DONE_KEYWORDS


def process_message(token: str, message: dict[str, Any], lucas_id: int | None,
                    leo_id: int | None = None) -> None:
    msg_id = message.get("message_id")
    user = message.get("from") or {}
    user_id = user.get("id")
    chat_id = (message.get("chat") or {}).get("id") or user_id

    # Determinar rol del usuario
    if user_id == lucas_id:
        role = "lucas"   # cliente que manda fotos productos
    elif user_id == leo_id:
        role = "leo"     # operador que recibe agenda y publica
    elif lucas_id or leo_id:
        # Hay filtro activo y este usuario no es ninguno de los autorizados
        append_log({"ts": now_iso(), "msg_id": msg_id, "from": user_id,
                    "type": "ignored", "reason": "user_not_authorized"})
        return
    else:
        role = "unknown"

    text = message.get("text") or message.get("caption") or ""
    photos = message.get("photo") or []
    video = message.get("video")
    document = message.get("document")

    # 0.0) Si el usuario tiene un flow /venta activo, los mensajes de texto los maneja venta_flow.
    # Excepción: si manda foto, dejamos seguir el flow normal (no interrumpe la captura de fotos).
    if text and not photos and not video and not document and venta_flow.is_venta_active(user_id):
        if venta_flow.handle_venta_text(chat_id, user_id, text):
            return

    # 0) Comandos
    cmd = text.strip().lower() if text else ""
    if cmd in ("/start", "/ayuda", "/help"):
        tg_send(token, chat_id, _welcome_msg(), reply_to=msg_id)
        append_log({"ts": now_iso(), "msg_id": msg_id, "from": "lucas",
                    "type": "command", "action": cmd.strip("/")})
        print(f"  ↳ comando {cmd}: enviado welcome")
        return

    # 0.2) Comando /venta → inicia flow conversacional para registrar venta
    if text and text.strip().lower().startswith("/venta"):
        args = text.strip()[len("/venta"):].strip()
        venta_flow.start_venta(chat_id, user_id, args)
        append_log({"ts": now_iso(), "msg_id": msg_id, "from": user_id,
                    "type": "command", "action": "venta_start", "args": args[:200]})
        print(f"  ↳ /venta iniciado por {user_id} (args='{args[:80]}')")
        return

    # 0.3) Comando /reply <mensaje del cliente> → sugerencia GPT para responder WA
    if text and text.strip().lower().startswith("/reply"):
        client_msg = text.strip()[len("/reply"):].strip()
        if not client_msg:
            tg_send(token, chat_id,
                    "Para usar: <code>/reply &lt;mensaje del cliente&gt;</code>\n\n"
                    "Ejemplo:\n<code>/reply Hola, cuánto sale la campera negra?</code>\n\n"
                    "Te devuelvo una respuesta lista para copiar y mandar al cliente.",
                    reply_to=msg_id)
            return

        # Cargar env de nuevo (necesario porque process_message no recibe env)
        env_local = {}
        for line in (REPO_ROOT / ".env").read_text(encoding='utf-8').splitlines():
            line = line.strip()
            if line and not line.startswith('#') and '=' in line:
                k, _, v = line.partition('=')
                env_local[k.strip()] = v.strip()

        catalog = _fetch_catalog_for_replies(env_local)
        suggestion, usage = gpt_reply_suggestion(client_msg, catalog)

        if suggestion:
            reply_msg = (
                f"💡 <b>Sugerencia para responder al cliente:</b>\n\n"
                f"<code>{suggestion}</code>\n\n"
                f"<i>Tocá la sugerencia para copiarla. Editala si querés.</i>"
            )
            tg_send(token, chat_id, reply_msg, reply_to=msg_id)
            append_log({"ts": now_iso(), "msg_id": msg_id, "from": "lucas",
                        "type": "command", "action": "reply",
                        "client_msg": client_msg[:200],
                        "suggestion": suggestion[:300],
                        "tokens": usage.get("total_tokens", 0)})
            print(f"  ↳ /reply → sugerencia generada ({usage.get('total_tokens',0)} tokens)")
        else:
            err = (usage or {}).get('_error', 'sin respuesta')
            tg_send(token, chat_id, f"⚠ Error al generar sugerencia: {err[:150]}", reply_to=msg_id)
            print(f"  ↳ /reply FAIL: {err}")
        return

    # 0.5) Comando "LISTO" o equivalente → cerrar sesión y enviar link del form
    if _is_done_command(text or ""):
        sess = _get_session(user_id)
        if sess["photos"] == 0:
            tg_send(token, chat_id,
                    "Todavía no recibí ninguna foto en esta sesión. Mandá fotos primero.",
                    reply_to=msg_id)
        else:
            sess["chat_id"] = chat_id
            _close_session(token, user_id, chat_id)
            _reset_session(user_id)
        append_log({"ts": now_iso(), "msg_id": msg_id, "from": "lucas",
                    "type": "command", "action": "done"})
        return

    # 1) Bloque PRODUCTO
    product = parse_product_block(text) if text else None
    if product:
        upsert_product_meta(product)
        _LAST_CODE_BY_USER[user_id] = product["code"]
        append_log({"ts": now_iso(), "msg_id": msg_id, "from": "lucas",
                    "type": "text", "action": "product_intake",
                    "code": product["code"], "raw": text})
        ack = (
            f"✅ Producto cargado\n\n"
            f"<b>{product['name'] or product['code']}</b>\n"
            f"Código: <code>{product['code']}</code>\n"
            f"Precio: ${product['price']:,}\n"
            f"Stock total: {product['total_stock']} unidades\n"
            f"Talles: {', '.join(product['sizes']) or '-'}\n\n"
            f"Ahora mandame las fotos del producto."
        ).replace(",", ".")
        tg_send(token, chat_id, ack, reply_to=msg_id)
        print(f"  ↳ PRODUCTO cargado: {product['code']}")
        # No return — la misma foto puede venir adjunta con la caption.

    # 2) Stock update
    if text and not product:
        update = parse_stock_update(text)
        if update:
            append_log({"ts": now_iso(), "msg_id": msg_id, "from": "lucas",
                        "type": "text", "action": "stock_update", **update,
                        "raw": text})
            print(f"  ↳ stock update: {update}")
            action = update["action"]
            code = update.get("code", "")
            if action == "sale":
                ack = (f"📉 Anotado: venta de <code>{code}</code> "
                       f"talle {update['size']} x{update['qty']}.\n"
                       f"Acordate de cargarlo también en el tracker de ventas.")
            elif action == "set_zero":
                ack = (f"🛑 Marcado SIN STOCK: <code>{code}</code>.\n"
                       f"Voy a revisar si hay piezas programadas que usen este producto.")
            elif action == "set":
                ack = (f"📊 Stock seteado: <code>{code}</code> "
                       f"talle {update['size']} = {update['qty']}.")
            elif action == "restock":
                ack = (f"📈 Stock sumado: <code>{code}</code> "
                       f"talle {update['size']} +{update['qty']}.")
            else:
                ack = f"Anotado: {action} {code}"
            tg_send(token, chat_id, ack, reply_to=msg_id)
            return

    # 3) Foto / video / documento
    media: list[tuple[str, str]] = []  # [(file_id, asset_type)]
    if photos:
        # Telegram manda variantes; tomar la más grande
        biggest = max(photos, key=lambda p: p.get("file_size", 0))
        media.append((biggest["file_id"], "photo"))
    if video:
        media.append((video["file_id"], "video"))
    if document:
        mime = document.get("mime_type", "")
        atype = "video" if mime.startswith("video/") else "image" if mime.startswith("image/") else "file"
        media.append((document["file_id"], atype))

    if media:
        code = _LAST_CODE_BY_USER.get(user_id)
        # Init / update session — silencioso por defecto, solo greeting en la 1ra foto
        sess = _get_session(user_id)
        sess["chat_id"] = chat_id
        first_in_session = sess["photos"] == 0 and not sess["greeting_sent"]
        if not sess["started_at"]:
            sess["started_at"] = now_iso()
        if first_in_session:
            tg_send(token, chat_id, FIRST_PHOTO_MSG, reply_to=msg_id)
            sess["greeting_sent"] = True
        for file_id, asset_type in media:
            file_info = tg_get(token, "getFile", file_id=file_id).get("result", {})
            file_path = file_info.get("file_path")
            if not file_path:
                continue
            ext = Path(file_path).suffix or (".jpg" if asset_type == "photo" else ".bin")
            file_name = f"msg{msg_id}_{file_id[:10]}{ext}"
            if code:
                dest = attach_asset(code, file_name, asset_type, msg_id)
                tg_download(token, file_path, dest)
                append_log({"ts": now_iso(), "msg_id": msg_id, "from": "lucas",
                            "type": asset_type, "linked_to": code,
                            "saved_as": str(dest.relative_to(REPO_ROOT))})
                print(f"  ↳ {asset_type} → {dest.relative_to(REPO_ROOT)}")
            else:
                day = datetime.now(timezone.utc).strftime("%Y-%m-%d")
                dest = INBOX_DIR / day / file_name
                tg_download(token, file_path, dest)
                meta_dest = dest.with_suffix(".json")
                base_meta = {
                    "msg_id": msg_id,
                    "type": asset_type,
                    "received_at": now_iso(),
                    "caption": text,
                    "from_user_id": user_id,
                    "tagged": False,   # marca para el form: foto pendiente de etiquetar
                }
                meta_dest.write_text(json.dumps(base_meta, ensure_ascii=False, indent=2), encoding="utf-8")
                append_log({"ts": now_iso(), "msg_id": msg_id, "from": "lucas",
                            "type": asset_type, "linked_to": None,
                            "saved_as": str(dest.relative_to(REPO_ROOT))})
                print(f"  ↳ {asset_type} → INBOX: {dest.relative_to(REPO_ROOT)}")

                # Actualizar sesión (silencioso, no enviar reply por foto)
                sess["photos"] += 1
                sess["last_photo_ts"] = now_iso()
                sess["link_sent"] = False  # nueva foto reabre la sesión si ya se había cerrado

                # AI: analizar la foto con Claude Vision (solo fotos, no videos)
                if asset_type == "photo" and ANTHROPIC_API_KEY:
                    ai = analyze_photo(dest)
                    ai_dest = dest.with_suffix(".ai.json")
                    ai_dest.write_text(json.dumps(ai or {}, ensure_ascii=False, indent=2),
                                       encoding="utf-8")
                    base_meta["ai"] = ai

                    # Agrupar con producto previo si matchea
                    group_info = {}
                    if ai and "_error" not in ai:
                        photo_ref = str(dest.relative_to(REPO_ROOT)).replace("\\", "/")
                        group_info = assign_product_group(ai, photo_ref)
                        base_meta["product_group"] = group_info

                    meta_dest.write_text(json.dumps(base_meta, ensure_ascii=False, indent=2),
                                         encoding="utf-8")
                    append_log({"ts": now_iso(), "msg_id": msg_id, "type": "ai_analysis",
                                "saved_as": str(ai_dest.relative_to(REPO_ROOT)),
                                "group_id": group_info.get("group_id"),
                                "group_status": group_info.get("group_status"),
                                "tokens_out": (ai or {}).get("_ai_tokens_out", 0)})

                    if ai and "_error" not in ai:
                        category = ai.get("category", "?")
                        color = ai.get("color_principal", "?")
                        brand = ai.get("marca_visible")
                        # Solo registrar internamente, NO enviar mensaje a Lucas
                        gid = group_info.get("group_id")
                        if gid and gid not in sess["groups"]:
                            sess["groups"].append(gid)
                        print(f"  ↳ AI: {category} / {color} / {brand}  [grupo {gid}, {group_info.get('group_status')}]")
                    else:
                        err = (ai or {}).get("_error", "sin respuesta")
                        print(f"  ↳ AI FAIL: {err}")
        return

    # 4) Texto sin clasificar
    if text and not product:
        day = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        dest = INBOX_DIR / day / f"msg{msg_id}.json"
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(json.dumps({
            "msg_id": msg_id, "received_at": now_iso(),
            "text": text, "from_user_id": user_id,
        }, ensure_ascii=False, indent=2), encoding="utf-8")
        append_log({"ts": now_iso(), "msg_id": msg_id, "from": "lucas",
                    "type": "text", "action": "unclassified",
                    "saved_as": str(dest.relative_to(REPO_ROOT)), "raw": text})
        print(f"  ↳ texto sin clasificar → INBOX: {dest.relative_to(REPO_ROOT)}")
        tg_send(token, chat_id, UNKNOWN_TEXT_MSG, reply_to=msg_id)


# ─────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────

def process_callback(token: str, cbq: dict, lucas_id: int | None,
                     leo_id: int | None) -> None:
    """Procesa click en botón inline de Telegram.

    callback_data formato: <action>:<id>
      - publicado:DIA2-POST-1   → marca como publicado, ✅ verde
      - skip:DIA2-STORY-1       → marca como salteado, ⏭ gris
      - regen:DIA2-POST-1       → pide regenerar caption (futuro)
    """
    cbq_id = cbq.get("id")
    user_id = (cbq.get("from") or {}).get("id")
    msg = cbq.get("message", {})
    chat_id = (msg.get("chat") or {}).get("id")
    msg_id = msg.get("message_id")
    data = cbq.get("data", "")
    has_photo = bool(msg.get("photo"))

    # Validar usuario autorizado
    if (lucas_id or leo_id) and user_id not in (lucas_id, leo_id):
        tg_answer_callback(token, cbq_id, "No autorizado")
        return

    # Callbacks del flow /venta tienen prefijo venta_*
    if data.startswith("venta_"):
        try:
            venta_flow.handle_venta_callback(cbq)
        except Exception as exc:
            print(f"  ↳ VENTA CALLBACK ERROR: {exc}")
            tg_answer_callback(token, cbq_id, f"Error: {str(exc)[:80]}")
        return

    if ":" not in data:
        tg_answer_callback(token, cbq_id, "Acción no reconocida")
        return

    action, ref = data.split(":", 1)
    now_local = datetime.now(timezone(timedelta(hours=-3))).strftime("%H:%M")

    if action == "publicado":
        # Confirmar visualmente: editar caption/text con ✅
        original = msg.get("caption") or msg.get("text") or ""
        if not original.startswith("✅"):
            new_text = f"✅ <b>PUBLICADO {now_local}</b> · {ref}\n\n" + original[:1000]
            if has_photo:
                tg_edit_caption(token, chat_id, msg_id, new_text, buttons=[])
            else:
                tg_edit_message_text(token, chat_id, msg_id, new_text, buttons=[])
        tg_answer_callback(token, cbq_id, f"✅ Anotado: {ref} publicado a las {now_local}")
        append_log({"ts": now_iso(), "from": user_id, "type": "callback",
                    "action": "publicado", "ref": ref, "hora": now_local})
        print(f"  ↳ ✅ {ref} marcado publicado")

    elif action == "skip":
        original = msg.get("caption") or msg.get("text") or ""
        if not original.startswith("⏭"):
            new_text = f"⏭ <b>OMITIDO</b> · {ref}\n\n" + original[:1000]
            if has_photo:
                tg_edit_caption(token, chat_id, msg_id, new_text, buttons=[])
            else:
                tg_edit_message_text(token, chat_id, msg_id, new_text, buttons=[])
        tg_answer_callback(token, cbq_id, f"⏭ Salteado: {ref}")
        append_log({"ts": now_iso(), "from": user_id, "type": "callback",
                    "action": "skip", "ref": ref})
        print(f"  ↳ ⏭ {ref} salteado")

    elif action == "regen":
        tg_answer_callback(token, cbq_id, "Función pendiente de implementar")
        print(f"  ↳ regen pedido para {ref} (no implementado todavía)")

    else:
        tg_answer_callback(token, cbq_id, f"Acción '{action}' no reconocida")


def poll_once(token: str, lucas_id: int | None, long_poll_timeout: int = 0,
              leo_id: int | None = None) -> tuple[int, set[int]]:
    """Una pasada por getUpdates. Devuelve (procesados, set de user_ids vistos)."""
    offset = get_offset()
    try:
        resp = tg_get(token, "getUpdates", offset=offset,
                      timeout=long_poll_timeout, limit=100)
    except urllib.error.HTTPError as e:
        print(f"ERROR HTTP {e.code}: {e.read().decode('utf-8', errors='replace')}",
              file=sys.stderr)
        return 0, set()
    except (urllib.error.URLError, TimeoutError) as e:
        print(f"  (timeout/red — reintento) {e}")
        return 0, set()

    if not resp.get("ok"):
        print(f"ERROR Telegram: {resp}", file=sys.stderr)
        return 0, set()

    updates = resp.get("result", [])
    if not updates:
        return 0, set()

    last_update_id = offset
    seen_users: set[int] = set()
    for upd in updates:
        upd_id = upd.get("update_id", 0)
        last_update_id = max(last_update_id, upd_id)

        # 1) Callback query (botón presionado)
        cbq = upd.get("callback_query")
        if cbq:
            from_user = (cbq.get("from") or {}).get("id")
            if from_user:
                seen_users.add(from_user)
            print(f"[update {upd_id}] CALLBACK from {from_user} data='{cbq.get('data','')}'")
            try:
                process_callback(token, cbq, lucas_id, leo_id)
            except Exception as exc:
                print(f"  ↳ CALLBACK ERROR: {exc}")
            continue

        # 2) Mensaje normal
        msg = upd.get("message") or upd.get("edited_message")
        if not msg:
            continue
        from_user = (msg.get("from") or {}).get("id")
        if from_user:
            seen_users.add(from_user)
        print(f"[update {upd_id}] msg {msg.get('message_id')} from {from_user}")
        try:
            process_message(token, msg, lucas_id, leo_id)
        except Exception as exc:
            append_log({"ts": now_iso(), "msg_id": msg.get("message_id"),
                        "from": from_user, "type": "error", "error": str(exc)})
            print(f"  ↳ ERROR: {exc}")

    set_offset(last_update_id + 1)
    return len(updates), seen_users


def main() -> int:
    global REPLIES_ENABLED, ANTHROPIC_API_KEY, OPENAI_API_KEY, CLIENT_CFG
    args = sys.argv[1:]
    watch = "--watch" in args
    if "--no-replies" in args:
        REPLIES_ENABLED = False

    # Multi-tenant: --client SLUG (default stylo_fino para compat)
    slug = "stylo_fino"
    for i, a in enumerate(args):
        if a == "--client" and i + 1 < len(args):
            slug = args[i + 1]

    # Cargar config del cliente (resuelve env vars + JSON identidad)
    from client_config import load_client_config
    try:
        CLIENT_CFG = load_client_config(slug)
    except FileNotFoundError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 2

    # Bindear paths CLIENT_DIR/INBOX_DIR/etc al cliente correcto
    _bind_client_paths(slug)

    token = CLIENT_CFG.tg_bot_token
    if not token:
        print(f"ERROR: {CLIENT_CFG.env_prefix}_TG_BOT_TOKEN no encontrado en .env",
              file=sys.stderr)
        return 2

    env_file = REPO_ROOT / ".env"
    env = load_env(env_file)

    # Cargar Anthropic para visión (opcional)
    ANTHROPIC_API_KEY = env.get("ANTHROPIC_API_KEY") or os.environ.get("ANTHROPIC_API_KEY")
    if not ANTHROPIC_API_KEY:
        print("AVISO: ANTHROPIC_API_KEY vacío — fotos no se van a analizar con IA.")

    # Cargar OpenAI para sugerencias /reply (opcional)
    OPENAI_API_KEY = env.get("OPENAI_API_KEY") or os.environ.get("OPENAI_API_KEY")
    if not OPENAI_API_KEY:
        print("AVISO: OPENAI_API_KEY vacío — comando /reply no va a funcionar.")

    # Lead (Lucas en Stylo Fino) y Operator (Leo) del config
    lead_id = CLIENT_CFG.tg_lead_user_id
    op_id = CLIENT_CFG.tg_operator_user_id

    if not lead_id:
        print(f"AVISO: {CLIENT_CFG.env_prefix}_TG_LEAD_USER_ID vacío — acepto mensajes de cualquiera.")
        print(f"       Después de la 1ra corrida, copiá el 'from.id' del lead al .env.")
    else:
        print(f"  {CLIENT_CFG.lead_role_name} (lead) configurado: {lead_id}")
    if op_id:
        print(f"  {CLIENT_CFG.operator_role_name} (operador) configurado: {op_id}")

    CLIENT_DIR.mkdir(parents=True, exist_ok=True)

    # Registrar helpers + cfg en venta_flow (DI multi-tenant)
    venta_env = {
        "TOKEN": token,
        "SUPABASE_URL": CLIENT_CFG.supabase_url,
        "SUPABASE_SERVICE_ROLE_KEY": CLIENT_CFG.supabase_service_role_key,
    }
    venta_flow.register_tg_helpers(tg_send, tg_answer_callback, tg_edit_message_text,
                                   venta_env, client_cfg=CLIENT_CFG)

    print(f"Cliente: {CLIENT_CFG.display_name} ({CLIENT_CFG.slug})")
    print(f"Bot: @{CLIENT_CFG.tg_bot_username or '(sin username configurado)'}")
    print(f"Offset inicial: {get_offset()}")
    print(f"Replies: {'ON' if REPLIES_ENABLED else 'OFF (--no-replies)'}")
    print(f"Modo: {'watch (long polling)' if watch else 'one-shot'}")

    all_seen: set[int] = set()

    if not watch:
        processed, seen = poll_once(token, lead_id, long_poll_timeout=0, leo_id=op_id)
        all_seen.update(seen)
        if processed == 0:
            print("Sin mensajes nuevos.")
        else:
            print(f"\nMensajes procesados: {processed}")
        if all_seen and not lead_id:
            print(f"Usuarios vistos esta corrida: {sorted(all_seen)}")
            print(f"Copiá el ID del lead a {CLIENT_CFG.env_prefix}_TG_LEAD_USER_ID en .env.")
        return 0

    # Watch mode: long polling indefinido.
    print("\n[watch] Esperando mensajes. Ctrl+C para salir.\n")
    try:
        while True:
            check_idle_sessions(token)
            processed, seen = poll_once(token, lead_id, long_poll_timeout=25, leo_id=op_id)
            if seen:
                new = seen - all_seen
                if new and not lead_id:
                    print(f"  ↳ Nuevos user_ids vistos: {sorted(new)}")
                    print(f"     Pegá uno en .env → {CLIENT_CFG.env_prefix}_TG_LEAD_USER_ID")
                all_seen.update(seen)
    except KeyboardInterrupt:
        print("\n[watch] Detenido por usuario.")
        if all_seen and not lead_id:
            print(f"Usuarios vistos: {sorted(all_seen)}")
        return 0


if __name__ == "__main__":
    sys.exit(main())
