"""
Regenera los captions de las 14 piezas del sprint usando GPT-4o.
Tono: rioplatense, masculino urbano, sin precio, CTA a WhatsApp.
Idempotente: solo actualiza si el caption nuevo difiere significativamente.
"""
import sys, json, urllib.request, urllib.error, re
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

SYSTEM_PROMPT = """Sos copywriter de marca para Stylo Fino, indumentaria masculina urbana en Avellaneda, Argentina. Vendés Nike, Adidas, Puma, The North Face. Cuenta nueva en Instagram (@indumentariastylofino).

REGLAS CRÍTICAS:
1. NUNCA pongas precio. Si hace falta, "consultá por WhatsApp".
2. NUNCA inventes detalles técnicos. Solo decí lo que SÉ del producto (nombre, color, marca, categoría). NO menciones: "impermeable", "tecnología térmica", "tela respirable", "capucha desmontable" (a menos que esté EXPLÍCITO en la descripción técnica que te paso).
3. NUNCA empieces con 🔥. Variá: sin emoji, o usá 🖤 / 👕 / 💪 / 👀 / ⚫ alternados.
4. NUNCA repitas "Talles disponibles: S · M · L · XL" textual. Variá:
   - "S a XL"
   - "Stock en S, M, L, XL"
   - "Hay todos los talles"
   - O mencionalo solo si es relevante (no en social_proof o BTS)
5. Tono: rioplatense neutro, urbano, masculino, directo. Sin "boludo", sin "che hermano". Profesional con calle.
6. PROHIBIDO: "lujo", "premium", "ofertón", "liquidamos", "exclusivo", "calidad premium", "aliada", "buscabas".
7. Largo: 2-4 líneas. Conciso. Cero relleno.
8. HOOK al inicio: frase corta y llamativa (5-10 palabras). NUNCA "Hola comunidad", "¡Arrancamos con todo!", "¡No te lo podés perder!".
9. CTA al final con WhatsApp + 👇. Variá:
   - "Pedí precio y stock por WA 👇"
   - "Talles por WhatsApp 👇"
   - "Mandá CATÁLOGO por WA 👇"
   - "Escribime para más info 👇"
   - "DM o WhatsApp para precios 👇"
10. MÁXIMO 1 emoji por caption (en hook o CTA, no ambos).
11. NO uses hashtags dentro del caption (van separados).
12. Si es social_proof / BTS / lifestyle: NO menciones producto específico ni talles. Hablá de la marca / experiencia.

Devolvés SOLO el caption final, sin markdown, sin comillas, sin explicaciones."""


def gpt_caption(producto_info, pieza_info):
    """Llama GPT-4o-mini con contexto y devuelve caption."""
    user_prompt = f"""Generá el caption para esta publicación:

DATOS DE LA PIEZA:
- Día del sprint: {pieza_info['day']}
- Tipo: {pieza_info['type']} (feed/reel/carrusel)
- Categoría: {pieza_info['category']} (producto/social_proof/lifestyle/bts)
- Hook conceptual sugerido (orientativo, podés cambiarlo): {pieza_info.get('hook', '-')}

DATOS DEL PRODUCTO ASIGNADO:
- Nombre: {producto_info.get('name', 'sin producto específico')}
- Categoría: {producto_info.get('category', '-')}
- Color: {producto_info.get('color', '-')}
- Marca: {producto_info.get('brand', '-')}
- Talles: {producto_info.get('talles', 'S, M, L, XL')}
- Descripción técnica: {producto_info.get('description', '-')[:200]}

Generá un caption seguro Meta-friendly, sin precio, con hook + información clave + CTA WhatsApp."""

    payload = json.dumps({
        "model": "gpt-4o-mini",
        "max_tokens": 250,
        "temperature": 0.85,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt},
        ]
    }).encode('utf-8')

    req = urllib.request.Request("https://api.openai.com/v1/chat/completions",
        data=payload,
        headers={'Authorization': f'Bearer {OPENAI_KEY}', 'Content-Type': 'application/json'})
    try:
        r = json.loads(urllib.request.urlopen(req, timeout=30).read())
        text = r['choices'][0]['message']['content'].strip()
        # Limpiar: quitar comillas envolventes si las agregó
        if text.startswith('"') and text.endswith('"'):
            text = text[1:-1]
        return text, r.get('usage', {})
    except urllib.error.HTTPError as e:
        return None, {'_error': e.read().decode()[:200]}


def main():
    # 1. Traer las 14 piezas + producto asignado
    items_url = f"{SB_URL}/rest/v1/content_items?client_id=eq.{CLIENT_ID}&select=id,description,scheduled_at,post_type,caption,hashtags,file_url&order=scheduled_at.asc"
    items = json.loads(urllib.request.urlopen(urllib.request.Request(items_url, headers=H), timeout=15).read())
    print(f"Piezas a procesar: {len(items)}\n")

    total_in = 0
    total_out = 0

    for it in items:
        cid = re.search(r'(SF-D\d+-\S+)', it['description']).group(1) if re.search(r'(SF-D\d+-\S+)', it['description']) else '?'
        day = re.search(r'D(\d+)', cid).group(1) if re.search(r'D(\d+)', cid) else '?'
        cat_short = cid.split('-')[-1] if '-' in cid else '?'
        category = {'PROD':'producto','SP':'social_proof','LIFE':'lifestyle','BTS':'bts'}.get(cat_short, cat_short)

        # Buscar producto si tiene file_url
        producto_info = {}
        if it.get('file_url') and not it['file_url'].startswith('pending://'):
            url = f"{SB_URL}/rest/v1/client_products?client_id=eq.{CLIENT_ID}&image_url=eq.{urllib.parse.quote(it['file_url'])}&select=name,description,tags"
            try:
                prods = json.loads(urllib.request.urlopen(urllib.request.Request(url, headers=H), timeout=10).read())
                if prods:
                    p = prods[0]
                    producto_info['name'] = p['name']
                    producto_info['description'] = p.get('description', '')
                    # Extraer marca/color/talles de tags
                    for t in (p.get('tags') or []):
                        if isinstance(t, str):
                            if t.startswith('color:'): producto_info['color'] = t[6:]
                            elif t.startswith('brand:'): producto_info['brand'] = t[6:]
                            elif t.startswith('stock_by_size:'):
                                try:
                                    sbs = json.loads(t[14:])
                                    producto_info['talles'] = ", ".join(sbs.keys())
                                except: pass
            except Exception:
                pass

        pieza_info = {
            'day': day,
            'type': it['post_type'],
            'category': category,
            'hook': it.get('caption', '').split('\n')[0][:80] if it.get('caption') else None,
        }

        # Generar
        new_caption, usage = gpt_caption(producto_info, pieza_info)
        if not new_caption:
            print(f"  ✗ {cid}: {usage.get('_error','?')[:80]}")
            continue
        total_in += usage.get('prompt_tokens', 0)
        total_out += usage.get('completion_tokens', 0)

        print(f"\n=== {cid} (día {day}, {category}, {it['post_type']}) ===")
        if producto_info.get('name'):
            print(f"  Producto: {producto_info['name']}")
        print(f"  ───")
        for line in new_caption.split('\n'):
            print(f"  {line}")
        print(f"  ───")

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
        print(f"  DRY-RUN — no se actualizó Supabase")


if __name__ == "__main__":
    import urllib.parse
    main()
