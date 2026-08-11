"""
Regenera captions de TODAS las piezas pendientes del sprint con el estilo
minimalista de Lucas (2 líneas + talles + 1-2 emojis).

Solo regenera piezas con status != 'published'. No toca las ya publicadas.
"""
import sys, json, urllib.request, urllib.error, urllib.parse, re
from pathlib import Path

sys.stdout.reconfigure(encoding='utf-8') if hasattr(sys.stdout, 'reconfigure') else None

REPO_ROOT = Path(__file__).resolve().parents[2]
env = {}
for line in (REPO_ROOT / ".env").read_text(encoding="utf-8").splitlines():
    line = line.strip()
    if line and not line.startswith("#") and "=" in line:
        k, _, v = line.partition("=")
        env[k.strip()] = v.strip()

OPENAI_KEY = env["OPENAI_API_KEY"]
SB_URL = env["SUPABASE_URL"]
SVC = env["SUPABASE_SERVICE_ROLE_KEY"]
H = {"apikey": SVC, "Authorization": f"Bearer {SVC}"}
H_W = {**H, "Content-Type": "application/json", "Prefer": "return=minimal"}
CLIENT_ID = "202477af-9207-4e09-b180-dca895df4743"

DRY = '--dry-run' in sys.argv

SYSTEM = """Sos copywriter de Stylo Fino, indumentaria masculina urbana en Avellaneda.

FORMATO EXACTO (2 líneas, NADA MÁS):

Línea 1: [Prenda] [marca opcional] [color]. (punto al final, sin nada más)
Línea 2: Disponibles en talles S a XXL.

NO uses emojis. NO uses hashtags. NO uses comillas. NO uses markdown.
NO agregues una 3ra línea bajo ningún concepto.

EJEMPLOS OK (copiá este formato literal):
  Chaleco Nike verde militar.
  Disponibles en talles S a XXL.

  Pantalón Adidas negro AFA.
  Disponibles en talles S a XXL.

  Buzo TNF gris.
  Disponibles en talles S a XXL.

EJEMPLOS PROHIBIDOS:
  Pantalón Adidas negro AFA, cómodo y con estilo.      ← prohibido el extra
  Conjunto Puma rojo, perfecto para tus salidas.       ← prohibido
  Campera Nike negra, ideal para esos días frescos.    ← prohibido
  Buzo TNF gris 🇦🇷👇                                    ← prohibido emoji
  Chaleco NOCTA 🖤                                       ← prohibido emoji

FRASES PROHIBIDAS (cualquier variante es banneo automático):
- "cómodo y con estilo", "con estilo", "cómodo", "estiloso"
- "perfecto para", "ideal para", "el aliado perfecto"
- "para tus salidas", "para el día a día", "para todos los días"
- "el clásico que no puede faltar", "no te quedes sin"
- "para los fanáticos", "para los verdaderos"
- "dale un upgrade", "lucir un look", "mostrar tu pasión"
- "tela de calidad", "tecnología", "diseño moderno"
- adjetivos: versátil, esencial, infaltable, único, exclusivo
- verbos de venta: llevátelo, conseguilo, no te lo pierdas, reservalo

Para social_proof / BTS / lifestyle: 1 frase corta neutra (sin inventar producto, sin emojis, sin "Disponibles en talles").

Devolvé SOLO las 2 líneas. Sin comillas, sin emojis, sin nada extra."""


# Frases prohibidas (lowercase) — se chequean en el output del GPT.
FORBIDDEN_PHRASES = [
    "cómodo y con estilo", "con estilo", "cómodo", "estiloso",
    "ideal para cualquier", "ideal para esos", "ideal para",
    "perfecto para", "el aliado perfecto", "el clásico",
    "no te quedes sin", "para los verdaderos",
    "dale un upgrade", "mandá un mensajito", "lucir un look",
    "pasión y estilo", "para todos los días",
    "para tus salidas", "para el día a día",
    "mostrar tu pasión",
    "tela de calidad", "tecnología", "diseño moderno",
    "versátil", "esencial", "infaltable", "único en su", "exclusivo",
    "llevátelo", "no te lo pierdas", "conseguilo", "reservalo",
]

# Rango unicode de emojis a eliminar / detectar
_EMOJI_RE = re.compile(
    "["
    "\U0001F600-\U0001F64F"   # emoticons
    "\U0001F300-\U0001F5FF"   # symbols & pictographs
    "\U0001F680-\U0001F6FF"   # transport & map
    "\U0001F1E0-\U0001F1FF"   # flags (iOS)
    "\U0001F900-\U0001F9FF"   # supplemental symbols
    "\U0001FA70-\U0001FAFF"
    "\U00002600-\U000026FF"   # misc symbols
    "\U00002700-\U000027BF"   # dingbats
    "]+", flags=re.UNICODE
)


def has_forbidden(text):
    """Devuelve la primera violación encontrada (frase o 'emoji'). None si todo OK."""
    if not text:
        return None
    if _EMOJI_RE.search(text):
        return "emoji"
    low = text.lower()
    for phrase in FORBIDDEN_PHRASES:
        if phrase in low:
            return phrase
    return None


def strip_emojis(text):
    return _EMOJI_RE.sub("", text or "").strip()


def fallback_clean(producto_info, pieza_info):
    """Caption de fallback determinístico (sin emojis, sin filler)."""
    name = producto_info.get('name', 'Prenda Stylo Fino')
    if pieza_info.get('category') == 'producto':
        return f"{name}.\nDisponibles en talles S a XXL."
    return f"{name}."


def gen_caption(producto_info, pieza_info):
    user_prompt = f"""Pieza: {pieza_info['cid']} (día {pieza_info['day']}, {pieza_info['category']}, {pieza_info['type']})
Producto asignado: {producto_info.get('name', 'sin producto específico')}
Marca: {producto_info.get('brand', '-')}
Color: {producto_info.get('color', '-')}

Generá el caption en estilo Lucas."""

    payload = json.dumps({
        "model": "gpt-4o-mini",
        "max_tokens": 80,
        "temperature": 0.3,
        "messages": [
            {"role": "system", "content": SYSTEM},
            {"role": "user", "content": user_prompt},
        ]
    }).encode('utf-8')

    req = urllib.request.Request("https://api.openai.com/v1/chat/completions",
        data=payload,
        headers={'Authorization': f'Bearer {OPENAI_KEY}', 'Content-Type': 'application/json'})
    try:
        r = json.loads(urllib.request.urlopen(req, timeout=30).read())
        text = r['choices'][0]['message']['content'].strip()
        if text.startswith('"') and text.endswith('"'):
            text = text[1:-1]
        return text, r.get('usage', {})
    except urllib.error.HTTPError as e:
        return None, {'_error': e.read().decode()[:200]}


def main():
    # Traer piezas pendientes (status != published)
    items_url = f"{SB_URL}/rest/v1/content_items?client_id=eq.{CLIENT_ID}&status=neq.published&select=id,description,scheduled_at,post_type,caption,file_url&order=scheduled_at.asc"
    items = json.loads(urllib.request.urlopen(urllib.request.Request(items_url, headers=H), timeout=15).read())
    print(f"Piezas pendientes a regenerar: {len(items)}\n")

    total_in = 0
    total_out = 0

    for it in items:
        cid_match = re.search(r'(SF-[A-Z0-9]+(?:-\S+)?)', it['description'])
        if not cid_match:
            continue
        cid = cid_match.group(1)
        day_match = re.search(r'D(\d+)', cid)
        day = day_match.group(1) if day_match else '?'
        cat_short = cid.split('-')[-1] if '-' in cid else '?'
        category = {'PROD':'producto','SP':'social_proof','LIFE':'lifestyle','BTS':'bts'}.get(cat_short, cat_short)

        # Buscar producto asignado por image_url
        producto_info = {}
        if it.get('file_url') and not it['file_url'].startswith('pending://'):
            url = f"{SB_URL}/rest/v1/client_products?client_id=eq.{CLIENT_ID}&image_url=eq.{urllib.parse.quote(it['file_url'])}&select=name,tags"
            try:
                prods = json.loads(urllib.request.urlopen(urllib.request.Request(url, headers=H), timeout=10).read())
                if prods:
                    p = prods[0]
                    producto_info['name'] = p['name']
                    for t in (p.get('tags') or []):
                        if isinstance(t, str):
                            if t.startswith('color:'): producto_info['color'] = t[6:]
                            elif t.startswith('brand:'): producto_info['brand'] = t[6:]
            except Exception:
                pass

        pieza_info = {'cid': cid, 'day': day, 'type': it['post_type'], 'category': category}

        new_caption, usage = gen_caption(producto_info, pieza_info)
        if not new_caption:
            print(f"  ✗ {cid}: {usage.get('_error','?')[:80]}")
            continue
        total_in += usage.get('prompt_tokens', 0)
        total_out += usage.get('completion_tokens', 0)

        # Post-proceso defensivo: stripear emojis siempre + recortar a max 2 líneas no vacías
        new_caption = strip_emojis(new_caption)
        lines = [l.strip() for l in new_caption.split('\n') if l.strip()]
        if len(lines) > 2:
            lines = lines[:2]
        new_caption = '\n'.join(lines)

        # Validar contra FORBIDDEN_PHRASES → retry una vez → fallback determinístico
        bad = has_forbidden(new_caption)
        if bad:
            print(f"  ⚠ {cid}: '{bad}' detectado, reintento...")
            retry_caption, retry_usage = gen_caption(producto_info, pieza_info)
            total_in += retry_usage.get('prompt_tokens', 0)
            total_out += retry_usage.get('completion_tokens', 0)
            if retry_caption:
                retry_caption = strip_emojis(retry_caption)
                rlines = [l.strip() for l in retry_caption.split('\n') if l.strip()][:2]
                retry_caption = '\n'.join(rlines)
            bad2 = has_forbidden(retry_caption) if retry_caption else "no_response"
            if retry_caption and not bad2:
                new_caption = retry_caption
            else:
                new_caption = fallback_clean(producto_info, pieza_info)
                print(f"  ↳ usando fallback determinístico")

        print(f"\n=== {cid} (día {day}, {category}) ===")
        if producto_info.get('name'):
            print(f"  Producto: {producto_info['name']}")
        for line in new_caption.split('\n'):
            print(f"  {line}")

        if not DRY:
            body = json.dumps({'caption': new_caption}).encode('utf-8')
            req = urllib.request.Request(f"{SB_URL}/rest/v1/content_items?id=eq.{it['id']}",
                                         data=body, headers=H_W, method='PATCH')
            urllib.request.urlopen(req, timeout=15).read()

    print(f"\n{'='*60}")
    print(f"  Total tokens: {total_in} in / {total_out} out")
    cost = total_in * 0.150 / 1_000_000 + total_out * 0.600 / 1_000_000
    print(f"  Costo: ~${cost:.4f} USD")
    if DRY:
        print(f"  DRY-RUN — Supabase no se actualizó")


if __name__ == "__main__":
    main()
