"""
Crea slots adicionales en el calendario para los próximos 7 días.
Asigna productos NO usados todavía + genera captions estilo Lucas.

Configuración (variables abajo):
  EXTRA_SLOTS_PER_DAY = 2   # cuántos slots EXTRA por día (suma a los existentes)
  HORARIOS = ["12:30", "19:30"]  # horarios fijos para los nuevos slots
  DIAS = 7  # cuántos días hacia adelante (incluye hoy)
"""
import sys, json, urllib.request, urllib.error, urllib.parse
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

SB_URL = env["SUPABASE_URL"]
SVC = env["SUPABASE_SERVICE_ROLE_KEY"]
OPENAI_KEY = env["OPENAI_API_KEY"]
H = {"apikey": SVC, "Authorization": f"Bearer {SVC}"}
H_W = {**H, "Content-Type": "application/json", "Prefer": "return=representation"}
CLIENT_ID = "202477af-9207-4e09-b180-dca895df4743"
AR = timezone(timedelta(hours=-3))

DRY = '--dry-run' in sys.argv

# Configuración
EXTRA_SLOTS_PER_DAY = 2
HORARIOS = ["12:30", "19:30"]
DIAS = 7

SYSTEM_CAPTION = """Sos copywriter de Stylo Fino, indumentaria masculina urbana en Avellaneda.

ESTILO LUCAS (referencia exacta):
"Chaleco Nike verde militar, ideal para esos días frescos.
Disponibles en talles S a XXL.
🇦🇷👇"

REGLAS:
- MÁXIMO 2 líneas + talles + emoji.
- Estructura: nombre+contexto / Disponibles en talles S a XXL / 1-2 emojis.
- PROHIBIDO: "dale un upgrade", "aliado perfecto", "ideal para combinar", marketing-speak.
- Sin comillas, sin markdown, sin hashtags.
Devolvé SOLO el caption."""


def gen_caption(producto_name, brand, color):
    payload = json.dumps({
        "model": "gpt-4o-mini", "max_tokens": 100, "temperature": 0.6,
        "messages": [
            {"role": "system", "content": SYSTEM_CAPTION},
            {"role": "user", "content": f"Producto: {producto_name}\nMarca: {brand}\nColor: {color}\n\nGenerá caption estilo Lucas."},
        ],
    }).encode()
    try:
        r = json.loads(urllib.request.urlopen(urllib.request.Request(
            "https://api.openai.com/v1/chat/completions", data=payload,
            headers={"Authorization": f"Bearer {OPENAI_KEY}", "Content-Type": "application/json"}
        ), timeout=30).read())
        return r['choices'][0]['message']['content'].strip()
    except Exception as e:
        return f"{producto_name}\nDisponibles en talles S a XXL.\n👇"


def main():
    # 1. Productos disponibles (los que no están asignados a ningún content_item)
    print("Cargando productos...")
    prods_url = f"{SB_URL}/rest/v1/client_products?client_id=eq.{CLIENT_ID}&select=id,name,image_url,tags"
    products = json.loads(urllib.request.urlopen(urllib.request.Request(prods_url, headers=H), timeout=15).read())
    print(f"  Total productos: {len(products)}")

    items_url = f"{SB_URL}/rest/v1/content_items?client_id=eq.{CLIENT_ID}&select=file_url"
    items = json.loads(urllib.request.urlopen(urllib.request.Request(items_url, headers=H), timeout=15).read())
    used_urls = {it['file_url'] for it in items if it.get('file_url') and not it['file_url'].startswith('pending://')}
    print(f"  URLs ya usadas en calendario: {len(used_urls)}")

    available = [p for p in products if p['image_url'] not in used_urls]
    # También filtrar los que ya tienen tag use_in_sprint:false (ya publicados, ej chaleco test)
    available = [p for p in available if not any(
        isinstance(t, str) and t.startswith('use_in_sprint:false')
        for t in (p.get('tags') or [])
    )]
    print(f"  Productos disponibles para asignar: {len(available)}\n")

    # 2. Calcular qué slots necesito crear (saltea slots en el pasado)
    now_ar = datetime.now(AR)
    today_ar = now_ar.date()
    new_slots = []  # datetime_ar
    skipped_past = 0
    for d in range(DIAS):
        date = today_ar + timedelta(days=d)
        for hora in HORARIOS:
            hh, mm = map(int, hora.split(':'))
            dt_ar = datetime.combine(date, datetime.min.time()).replace(
                hour=hh, minute=mm, tzinfo=AR
            )
            if dt_ar <= now_ar:
                skipped_past += 1
                continue
            new_slots.append(dt_ar)

    print(f"Slots posibles: {DIAS * len(HORARIOS)} · Skipeados por pasado: {skipped_past} · A crear: {len(new_slots)}")

    # Asignar productos disponibles a slots (1:1)
    n_to_create = min(len(new_slots), len(available))
    new_slots = new_slots[:n_to_create]

    # 3. Generar y crear cada content_item
    print(f"\nCreando {n_to_create} content_items con captions estilo Lucas...\n")

    for i, (dt_ar, prod) in enumerate(zip(new_slots, available[:n_to_create]), 1):
        # Extraer brand y color de tags
        brand, color = "", ""
        for t in (prod.get('tags') or []):
            if isinstance(t, str):
                if t.startswith('brand:'): brand = t[6:]
                elif t.startswith('color:'): color = t[6:]

        caption = gen_caption(prod['name'], brand, color)

        # Hashtags genéricos por categoría (extraídos del nombre)
        name_lower = prod['name'].lower()
        cat_tag = next((c for c in ('chaleco','campera','conjunto','pantalon','remera','buzo') if c in name_lower), '')
        brand_tag = brand.lower().replace(' ', '') if brand else ''
        hashtags = ['#stylofino']
        if brand_tag: hashtags.append(f'#{brand_tag}')
        if cat_tag: hashtags.append(f'#{cat_tag}s')
        hashtags += ['#ropamasculina', '#urbanwearargentina', '#avellaneda']

        # ID único para esta pieza nueva (no usa el formato SF-D## viejo)
        cid = f"SF-X{dt_ar.strftime('%m%d')}-{dt_ar.strftime('%H%M')}"

        body = {
            'client_id': CLIENT_ID,
            'file_url': prod['image_url'],
            'file_type': 'image',
            'post_type': 'feed',
            'description': f"[{cid} | phase=cruise | publish_mode=manual]\n{prod['name']}",
            'caption': caption,
            'hashtags': hashtags,
            'status': 'pending_approval',
            'scheduled_at': dt_ar.isoformat(),
            'upload_mode': 'manual',
        }

        dia_sem = ['Lun','Mar','Mié','Jue','Vie','Sáb','Dom'][dt_ar.weekday()]
        marker = "[DRY]" if DRY else "  "
        print(f"{marker} {dia_sem} {dt_ar.strftime('%d-%m %H:%M')}  {prod['name'][:35]:35s}")

        if not DRY:
            req = urllib.request.Request(f"{SB_URL}/rest/v1/content_items",
                                         data=json.dumps(body).encode(),
                                         headers=H_W, method='POST')
            try:
                urllib.request.urlopen(req, timeout=15).read()
            except urllib.error.HTTPError as e:
                print(f"      ✗ {e.code}: {e.read().decode()[:200]}")

    print(f"\n✓ Creados {n_to_create} slots adicionales {'(DRY-RUN)' if DRY else ''}")
    print(f"  Productos sobrantes (sin asignar): {len(available) - n_to_create}")


if __name__ == "__main__":
    main()
