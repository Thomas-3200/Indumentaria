"""
Asigna productos tagueados a las 14 piezas del calendario del sprint.

Para cada pieza del calendario:
  - Si la pieza NECESITA producto (categoría=producto/lifestyle): elige el mejor producto
    según el slot, su categoría y si está tagueado (active=true).
  - Si la pieza NO necesita producto (social_proof, BTS): la deja sin product_id.
  - Setea content_items.file_url con la primera foto del producto seleccionado.

Política de asignación:
  - Día 1, 3, 5, 6, 8, 12, 14: producto destacado (camperas, chalecos, conjuntos)
  - Día 4 (lifestyle reel): combo (mejor si Nike o Adidas con varias fotos)
  - Día 10 (carrusel combo): conjunto
  - Día 11 (lifestyle): producto con foto en contexto
  - Día 2, 7, 9, 13: NO requieren producto (social proof, BTS, top 3)

Uso:
  python flows/bot_telegram_mt/assign_products_to_calendar.py --dry-run
  python flows/bot_telegram_mt/assign_products_to_calendar.py
"""
import sys, json, urllib.request, urllib.error, urllib.parse, re
from pathlib import Path

sys.stdout.reconfigure(encoding='utf-8') if hasattr(sys.stdout, 'reconfigure') else None

DRY = '--dry-run' in sys.argv

REPO_ROOT = Path(__file__).resolve().parents[2]
env = {}
for line in (REPO_ROOT / ".env").read_text(encoding="utf-8").splitlines():
    line = line.strip()
    if line and not line.startswith("#") and "=" in line:
        k, _, v = line.partition("=")
        env[k.strip()] = v.strip()

SB_URL = env["SUPABASE_URL"]
SVC = env["SUPABASE_SERVICE_ROLE_KEY"]
H = {"apikey": SVC, "Authorization": f"Bearer {SVC}",
     "Content-Type": "application/json", "Prefer": "return=representation"}
CLIENT_ID = "202477af-9207-4e09-b180-dca895df4743"


def sb_get(path):
    req = urllib.request.Request(f"{SB_URL}/rest/v1/{path}", headers=H)
    return json.loads(urllib.request.urlopen(req, timeout=15).read())


def sb_patch(path, body):
    req = urllib.request.Request(
        f"{SB_URL}/rest/v1/{path}",
        data=json.dumps(body).encode("utf-8"),
        headers={**H, "Prefer": "return=minimal"}, method="PATCH",
    )
    urllib.request.urlopen(req, timeout=15).read()


# ─────────────────────────────────────────────
# Reglas por pieza del calendario
# ─────────────────────────────────────────────
# (content_id_prefix, requiere_producto, categorías_preferidas, criterios extra)
RULES = {
    "SF-D01": {"requiere": True, "preferida": ["chalecos", "camperas", "conjuntos"], "nota": "PROD GANCHO 1 — el más vendible"},
    "SF-D02": {"requiere": False, "nota": "Social proof — no requiere producto específico"},
    "SF-D03": {"requiere": True, "preferida": ["conjuntos"], "nota": "Carrusel — preferir conjunto con varias fotos"},
    "SF-D04": {"requiere": True, "preferida": ["camperas", "pantalones"], "min_fotos": 2, "nota": "Reel lifestyle — prenda con varias fotos para transitions"},
    "SF-D05": {"requiere": True, "preferida": ["buzos", "camperas"], "nota": "Nuevo ingreso"},
    "SF-D06": {"requiere": True, "preferida": ["camperas"], "min_fotos": 2, "nota": "Reel — prenda con buen movimiento"},
    "SF-D07": {"requiere": False, "nota": "Cierre semana 1 — mix mejores fotos"},
    "SF-D08": {"requiere": True, "preferida": ["chalecos"], "evitar_color": "negro", "nota": "Reel — chaleco color distintivo"},
    "SF-D09": {"requiere": False, "nota": "BTS — video del local, no producto"},
    "SF-D10": {"requiere": True, "preferida": ["conjuntos"], "nota": "Carrusel combo"},
    "SF-D11": {"requiere": True, "preferida": ["remeras", "camperas"], "nota": "Lifestyle"},
    "SF-D12": {"requiere": True, "preferida": ["pantalones", "chalecos"], "min_fotos": 2, "nota": "Reel high turnover"},
    "SF-D13": {"requiere": False, "nota": "Top 3 más vendidos — usa fotos de los ganadores"},
    "SF-D14": {"requiere": True, "preferida": ["camperas", "chalecos"], "nota": "Cierre — color llamativo"},
}


def parse_metadata_from_tags(tags):
    """Extrae el __ai__ JSON de los tags del producto."""
    for t in (tags or []):
        if isinstance(t, str) and t.startswith("__ai__:"):
            try:
                return json.loads(t.slice(7) if False else t[7:])
            except Exception:
                pass
    return {}


def main():
    # 1. Cargar productos (todos, tagueados o no)
    products = sb_get(f"client_products?client_id=eq.{CLIENT_ID}&select=id,name,description,image_url,price,category_id,stock_status,tags,active&order=name.asc")

    # 2. Cargar categorías para mapear category_id → slug
    cats = sb_get(f"product_categories?client_id=eq.{CLIENT_ID}&select=id,slug,name")
    cat_slug_by_id = {c["id"]: c["slug"] for c in cats}

    # 3. Cargar piezas del calendario
    items = sb_get(f"content_items?client_id=eq.{CLIENT_ID}&select=id,description,scheduled_at,file_url&order=scheduled_at.asc")

    # 4. Construir índice de productos enriquecido
    product_pool = []
    for p in products:
        meta = parse_metadata_from_tags(p.get("tags", []))
        # Buscar si tiene flag de "ya publicado" (no usar en el calendario)
        already_published = any(
            isinstance(t, str) and t.startswith("use_in_sprint:false")
            for t in (p.get("tags") or [])
        )
        if already_published:
            continue
        slug = cat_slug_by_id.get(p["category_id"], "")
        product_pool.append({
            "id": p["id"],
            "name": p["name"],
            "image_url": p["image_url"],
            "price": p.get("price", 0),
            "slug": slug,
            "category": meta.get("ai_category", ""),
            "color": meta.get("ai_color", ""),
            "brand": meta.get("ai_brand", ""),
            "photos": meta.get("photos", []),
            "n_photos": len(meta.get("photos", [])),
            "tagueado": p.get("active", False),
            "stock_status": p.get("stock_status"),
        })

    print(f"Productos elegibles: {len(product_pool)}")
    print(f"Tagueados: {sum(1 for p in product_pool if p['tagueado'])}")
    print(f"Pendientes: {sum(1 for p in product_pool if not p['tagueado'])}\n")

    # 5. Asignar productos a piezas
    used_product_ids = set()
    assignments = []

    for item in items:
        cid_match = re.search(r"(SF-D\d+)", item.get("description", ""))
        if not cid_match:
            continue
        cid = cid_match.group(1)
        rule = RULES.get(cid)
        if not rule:
            continue

        if not rule["requiere"]:
            assignments.append({
                "item_id": item["id"], "cid": cid, "product": None,
                "nota": rule["nota"],
            })
            continue

        # Filtrar pool por reglas
        candidates = []
        for p in product_pool:
            if p["id"] in used_product_ids:
                continue
            # Filtro por slug categoría
            if rule.get("preferida") and p["slug"] not in rule["preferida"]:
                continue
            # Filtro por mínimo de fotos
            if rule.get("min_fotos") and p["n_photos"] < rule["min_fotos"]:
                continue
            # Filtro por color a evitar
            if rule.get("evitar_color") and p["color"] == rule["evitar_color"]:
                continue
            candidates.append(p)

        if not candidates:
            # Relajamos: cualquier producto no usado
            candidates = [p for p in product_pool if p["id"] not in used_product_ids]

        if not candidates:
            assignments.append({"item_id": item["id"], "cid": cid, "product": None,
                                "nota": "⚠ sin producto disponible"})
            continue

        # Score: priorizar tagueados, después por más fotos, después marca top
        TOP_BRANDS = {"nike", "adidas", "the north face", "puma"}
        def score(p):
            return (
                1 if p["tagueado"] else 0,    # +1 si tagueado
                p["n_photos"],                 # +1 por foto extra
                1 if p["brand"] in TOP_BRANDS else 0,  # +1 si marca top
            )
        candidates.sort(key=score, reverse=True)
        chosen = candidates[0]
        used_product_ids.add(chosen["id"])
        assignments.append({
            "item_id": item["id"], "cid": cid, "product": chosen, "nota": rule["nota"],
        })

    # 6. Mostrar plan
    print(f"{'Pieza':<8} {'Producto asignado':<45} {'Cat':<11} {'Marca':<14} {'Fotos':>5}  Nota")
    print("─" * 130)
    for a in assignments:
        if a["product"]:
            p = a["product"]
            tag = "✓" if p["tagueado"] else "⏳"
            print(f"{a['cid']:<8} {tag} {p['name'][:42]:<43} {p['slug']:<11} {p['brand']:<14} {p['n_photos']:>5}  {a['nota']}")
        else:
            print(f"{a['cid']:<8} —                                              —          —              —     {a['nota']}")

    # 7. Aplicar
    if DRY:
        print("\nDRY-RUN — no se modificó Supabase")
        return

    print("\nAplicando en Supabase...")
    for a in assignments:
        if a["product"]:
            sb_patch(f"content_items?id=eq.{a['item_id']}", {
                "file_url": a["product"]["image_url"],
            })
    print(f"  ✓ {sum(1 for a in assignments if a['product'])} piezas actualizadas")


if __name__ == "__main__":
    main()
