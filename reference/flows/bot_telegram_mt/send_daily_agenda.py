"""
Envía a Leo (operador) el kit completo del día con botones inline.

Para CADA pieza scheduleada hoy en Supabase:
  - 1 mensaje "Post en perfil (Instagram)" (foto + texto + botón Abrir Instagram + Listo/Saltar)
  - 1 mensaje "Post en perfil (Facebook)"  (mismo + botón Abrir Facebook)
  - 1 mensaje "Historia (Instagram)" (foto + texto encima + botón Abrir Instagram)
  - 1 mensaje "Estado (WhatsApp)" (foto + texto encima + instrucción manual)

Para piezas sin foto asignada: solo 1 mensaje combinado (perfil Instagram + Facebook).

Usage:
  python flows/bot_telegram_mt/send_daily_agenda.py
  python flows/bot_telegram_mt/send_daily_agenda.py --date 2026-05-16
  python flows/bot_telegram_mt/send_daily_agenda.py --dry-run

Para automatizar: agendarlo via cron diario a las 09:00 AR.
"""
import sys, json, urllib.request, urllib.error, urllib.parse, re
from datetime import datetime, timezone, timedelta
from pathlib import Path

sys.stdout.reconfigure(encoding='utf-8') if hasattr(sys.stdout, 'reconfigure') else None

REPO_ROOT = Path(__file__).resolve().parents[2]
env = {}
for line in (REPO_ROOT / ".env").read_text(encoding="utf-8").splitlines():
    line = line.strip()
    if line and not line.startswith("#") and "=" in line:
        k, _, v = line.partition("=")
        env[k.strip()] = v.strip()

# Multi-tenant: --client SLUG (default stylo_fino para compat con cron actual)
CLIENT_SLUG = "stylo_fino"
for i, arg in enumerate(sys.argv):
    if arg == '--client' and i + 1 < len(sys.argv):
        CLIENT_SLUG = sys.argv[i + 1]

sys.path.insert(0, str(Path(__file__).resolve().parent))
from client_config import load_client_config
cfg = load_client_config(CLIENT_SLUG)

SB_URL = cfg.supabase_url
SVC = cfg.supabase_service_role_key
H = {"apikey": SVC, "Authorization": f"Bearer {SVC}"}
CLIENT_ID = cfg.client_uuid
TG_TOKEN = cfg.tg_bot_token
# DESTINO: si hay grupo dedicado configurado → usa ese chat_id.
# Si no → cae al chat 1-a-1 con el operador (Leo). Backwards compatible.
LEO = cfg.tg_publish_chat_id if cfg.tg_publish_chat_id else cfg.tg_operator_user_id
DEST_KIND = "grupo dedicado" if cfg.tg_publish_chat_id else "chat 1-a-1 con operador"
WA_LINK = cfg.wa_link or "https://wa.me/"
AR = timezone(timedelta(hours=-3))

DRY = '--dry-run' in sys.argv

# Argumento --date YYYY-MM-DD opcional
target_date = None
for i, arg in enumerate(sys.argv):
    if arg == '--date' and i + 1 < len(sys.argv):
        try:
            target_date = datetime.strptime(sys.argv[i+1], '%Y-%m-%d').date()
        except ValueError:
            print(f"ERROR: fecha inválida '{sys.argv[i+1]}'. Usar YYYY-MM-DD")
            sys.exit(1)
if target_date is None:
    target_date = datetime.now(AR).date()


def tg_send(text, buttons=None):
    if DRY:
        print(f"  [DRY] {text[:80]}...")
        return
    url = f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage"
    data = {"chat_id": LEO, "text": text, "parse_mode": "HTML",
            "disable_web_page_preview": True}
    if buttons:
        data["reply_markup"] = {"inline_keyboard": buttons}
    try:
        urllib.request.urlopen(urllib.request.Request(url, data=json.dumps(data).encode(),
            headers={"Content-Type": "application/json"}), timeout=15).read()
    except urllib.error.HTTPError as e:
        print(f"  ✗ tg_send {e.code}: {e.read().decode()[:200]}")


def tg_send_photo(photo_url, caption, buttons=None):
    if DRY:
        print(f"  [DRY] PHOTO + caption: {caption[:80]}...")
        return
    url = f"https://api.telegram.org/bot{TG_TOKEN}/sendPhoto"
    data = {"chat_id": LEO, "photo": photo_url, "caption": caption, "parse_mode": "HTML"}
    if buttons:
        data["reply_markup"] = {"inline_keyboard": buttons}
    try:
        urllib.request.urlopen(urllib.request.Request(url, data=json.dumps(data).encode(),
            headers={"Content-Type": "application/json"}), timeout=20).read()
    except urllib.error.HTTPError as e:
        print(f"  ✗ tg_send_photo {e.code}: {e.read().decode()[:200]}")


def get_pieces_for_date(date):
    """Devuelve content_items con scheduled_at en la fecha indicada."""
    iso_start = datetime.combine(date, datetime.min.time()).replace(tzinfo=AR).isoformat()
    iso_end = datetime.combine(date + timedelta(days=1), datetime.min.time()).replace(tzinfo=AR).isoformat()
    url = (f"{SB_URL}/rest/v1/content_items?client_id=eq.{CLIENT_ID}"
           f"&scheduled_at=gte.{urllib.parse.quote(iso_start)}"
           f"&scheduled_at=lt.{urllib.parse.quote(iso_end)}"
           f"&status=neq.published"
           f"&select=id,description,scheduled_at,post_type,caption,hashtags,file_url"
           f"&order=scheduled_at.asc")
    return json.loads(urllib.request.urlopen(urllib.request.Request(url, headers=H), timeout=15).read())


def get_product_by_image(image_url):
    if not image_url or image_url.startswith('pending://'):
        return None
    url = (f"{SB_URL}/rest/v1/client_products?client_id=eq.{CLIENT_ID}"
           f"&image_url=eq.{urllib.parse.quote(image_url)}&select=name,tags")
    try:
        rows = json.loads(urllib.request.urlopen(urllib.request.Request(url, headers=H), timeout=10).read())
        return rows[0] if rows else None
    except Exception:
        return None


def extract_photos(product):
    """Devuelve lista de URLs de fotos disponibles para un producto.
    Las fotos están guardadas dentro de tags['__ai__:...'].photos (JSON serializado).
    Si solo hay 1 foto o no se puede parsear, devuelve [image_url_primaria].
    """
    if not product:
        return []
    tags = product.get('tags') or []
    for t in tags:
        if isinstance(t, str) and t.startswith('__ai__:'):
            try:
                meta = json.loads(t[len('__ai__:'):])
                photos = meta.get('photos') or []
                if photos:
                    # Filtrar duplicados manteniendo orden
                    seen = set()
                    unique = []
                    for p in photos:
                        if p and p not in seen:
                            seen.add(p)
                            unique.append(p)
                    return unique
            except Exception:
                pass
    return []


def pick_photos_for_pieces(all_photos, n_slots):
    """Rotación: distribuye n_slots fotos sin repetir hasta agotar el banco.
    Si hay menos fotos que slots, repite las que hay (pero marca duplicados).

    Devuelve lista de (photo_url, is_duplicate) de tamaño n_slots.
    """
    if not all_photos:
        return [(None, False)] * n_slots
    out = []
    for i in range(n_slots):
        if i < len(all_photos):
            out.append((all_photos[i], False))
        else:
            # Ya consumimos todas — repetir desde el principio, marcar duplicate
            out.append((all_photos[i % len(all_photos)], True))
    return out


# ─── Botones reusables ───
def btn_url_ig():
    return {"text": "📷 Abrir Instagram", "url": "https://www.instagram.com/"}
def btn_url_fb():
    return {"text": "📘 Abrir Facebook", "url": "https://www.facebook.com/"}
def btn_url_wa():
    # WhatsApp NO tiene deep link público a Estados — wa.me/... siempre abre chat.
    # Mantengo el helper por compat por si otra parte lo importa, pero ESTADO WA
    # ya no lo usa (ver mensaje en el flujo principal).
    return {"text": "💬 Abrir WhatsApp", "url": WA_LINK}
def btn_action(label, ref):
    return [
        {"text": "✅ Listo", "callback_data": f"publicado:{ref}"},
        {"text": "⏭ Saltar", "callback_data": f"skip:{ref}"},
    ]


def build_overlay(producto_name):
    """Texto corto para encima de la foto (story/estado)."""
    return f"{producto_name}\nTalles S a XXL · Pedí info 👇"


def main():
    print(f"\n📅 Enviando agenda para: {target_date.strftime('%a %d-%m-%Y')}")
    print(f"   Cliente: {cfg.display_name} ({cfg.slug})")
    print(f"   Destino: {DEST_KIND} (chat_id={LEO})\n")
    if DRY:
        print("MODO DRY-RUN — no se envía nada\n")

    pieces = get_pieces_for_date(target_date)
    if not pieces:
        print("No hay piezas programadas para esa fecha.")
        return

    print(f"Piezas pendientes: {len(pieces)}\n")

    # Header — día en español (sin depender de locale del sistema)
    DIAS_ES = {0: "Lunes", 1: "Martes", 2: "Miércoles", 3: "Jueves",
               4: "Viernes", 5: "Sábado", 6: "Domingo"}
    fecha_str = f"{DIAS_ES[target_date.weekday()]} {target_date.strftime('%d/%m')}"
    tg_send(
        f"📅 <b>Agenda del día · {fecha_str}</b>\n\n"
        f"Tenés {len(pieces)} producto(s) para publicar hoy. Cada uno se "
        f"desglosa en:\n"
        f"  • Post en perfil (Instagram)\n"
        f"  • Post en perfil (Facebook)\n"
        f"  • Historia (Instagram)\n"
        f"  • Estado (WhatsApp)\n\n"
        f"Tocá <b>✅ Listo</b> a medida que vayas subiendo cada uno."
    )

    for it in pieces:
        cid = re.search(r'(SF-D\d+-\S+)', it['description'])
        cid = cid.group(1) if cid else 'SF-?'
        category_short = cid.split('-')[-1] if '-' in cid else '?'
        is_producto = category_short in ('PROD',)

        product = get_product_by_image(it.get('file_url', ''))
        product_name = product['name'] if product else 'pieza social_proof / BTS'
        caption = it.get('caption', '')
        # Hashtags pueden venir como list (jsonb), JSON-string ('["#a","#b"]'),
        # o string plano. Normalizar a "#a #b #c" sin brackets ni comillas.
        raw_h = it.get('hashtags') or []
        if isinstance(raw_h, str):
            s = raw_h.strip()
            if s.startswith('['):
                try:
                    raw_h = json.loads(s)
                except Exception:
                    raw_h = [s]
            else:
                raw_h = s.split()
        if isinstance(raw_h, list):
            hashtags = ' '.join(str(h).strip() for h in raw_h if str(h).strip())
        else:
            hashtags = str(raw_h)
        caption_full = f"{caption}\n\n{hashtags}" if hashtags else caption

        dt = datetime.fromisoformat(it['scheduled_at']).astimezone(AR)
        hora = dt.strftime('%H:%M')

        print(f"→ {cid} ({hora}) - {product_name}")

        # === Rotación de fotos: si el producto tiene varias, las distribuye
        # entre los 4 mensajes (post IG, post FB, story IG, estado WA).
        # Si solo hay 1, repite + marca duplicado para que el operador sepa.
        if it.get('file_url') and not it['file_url'].startswith('pending://'):
            all_photos = extract_photos(product) if product else []
            if not all_photos:
                # Fallback: usar el file_url del calendario
                all_photos = [it['file_url']]

            n_slots = 4 if (is_producto and product) else 2
            rotation = pick_photos_for_pieces(all_photos, n_slots)
            dup_warning = (len(all_photos) < n_slots)
            warn_line = ""
            if dup_warning:
                warn_line = (
                    f"\n\n⚠ <i>Solo hay {len(all_photos)} foto(s) cargada(s) "
                    f"de este producto. Pedile a Lucas más fotos para no repetir "
                    f"la misma imagen en todas las publicaciones.</i>"
                )

            def _dup_tag(idx, is_dup):
                if not is_dup:
                    return ""
                return f"\n<i>(foto repetida — slot {idx+1}, banco agotado)</i>"

            # === 1. Post en perfil (Instagram) ===
            ph, dup = rotation[0]
            tg_send_photo(
                ph,
                (
                    f"📌 <b>Post en perfil (Instagram)</b> · {hora}\n\n"
                    f"<b>Texto del post:</b>\n<code>{caption_full}</code>"
                    f"{_dup_tag(0, dup)}{warn_line if dup else ''}"
                ),
                buttons=[[btn_url_ig()], btn_action("Listo o Saltar", f"{cid}-IG")]
            )
            # === 2. Post en perfil (Facebook) ===
            ph, dup = rotation[1]
            tg_send_photo(
                ph,
                (
                    f"📌 <b>Post en perfil (Facebook)</b> · {hora}\n\n"
                    f"<b>Texto del post:</b>\n<code>{caption_full}</code>"
                    f"{_dup_tag(1, dup)}"
                ),
                buttons=[[btn_url_fb()], btn_action("Listo o Saltar", f"{cid}-FB")]
            )

            # Si es producto: historia + estado con fotos rotadas
            if is_producto and product:
                overlay = build_overlay(product['name'])
                # === 3. Historia (Instagram) ===
                ph, dup = rotation[2]
                tg_send_photo(
                    ph,
                    (
                        f"📲 <b>Historia (Instagram)</b>\n\n"
                        f"<b>Texto encima de la foto:</b>\n<code>{overlay}</code>"
                        f"{_dup_tag(2, dup)}"
                    ),
                    buttons=[[btn_url_ig()], btn_action("Listo o Saltar", f"{cid}-IGS")]
                )
                # === 4. Estado (WhatsApp) ===
                ph, dup = rotation[3]
                tg_send_photo(
                    ph,
                    (
                        f"💬 <b>Estado (WhatsApp)</b>\n\n"
                        f"1) Descargá la foto de arriba.\n"
                        f"2) Abrí WhatsApp → pestaña <b>Estados</b> → tocá la cámara o el +.\n"
                        f"3) Elegí la foto que descargaste.\n"
                        f"4) Pegá este texto como leyenda:\n"
                        f"<code>{overlay}</code>"
                        f"{_dup_tag(3, dup)}"
                    ),
                    buttons=[btn_action("Listo o Saltar", f"{cid}-WA")]
                )
        else:
            # Pieza sin foto asignada → solo enviar texto + botones
            tg_send(
                f"📌 <b>Publicación sin foto asignada</b> · {hora}\n"
                f"<i>Categoría: {category_short}</i>\n\n"
                f"<b>Texto del post:</b>\n<code>{caption_full}</code>\n\n"
                f"⚠ Conseguí una foto vos misma (del local, cliente real, repost o detrás de escena) y subila a perfil de Instagram y Facebook.",
                buttons=[
                    [btn_url_ig(), btn_url_fb()],
                    btn_action("Listo o Saltar", cid),
                ]
            )

    print(f"\n✅ Agenda enviada a Leo")


if __name__ == "__main__":
    main()
