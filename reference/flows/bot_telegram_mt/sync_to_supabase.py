"""
Sync intake local → Supabase.

Para cada grupo detectado en product_groups.json:
  1. Sube las fotos del grupo al bucket público de Supabase Storage
  2. Inserta una fila en client_products con:
       - active=false  (significa "pendiente de taguear")
       - stock_status='pending_tag'
       - tags = { ai metadata + photos URLs + group_id }
  3. El form n8n lee estos rows y los muestra para completar.

Idempotente: si ya existe un product con tag.ai_group == group_id, lo SKIP.
"""
import sys, json, os, urllib.request, urllib.error, urllib.parse
from pathlib import Path

sys.stdout.reconfigure(encoding='utf-8') if hasattr(sys.stdout, 'reconfigure') else None

REPO_ROOT = Path(__file__).resolve().parents[2]
CLIENT_DIR = REPO_ROOT / "data" / "clients" / "stylo_fino"
GROUPS_FILE = CLIENT_DIR / "product_groups.json"
INBOX_DIR = CLIENT_DIR / "inbox"

# Load env
env = {}
for line in (REPO_ROOT / ".env").read_text(encoding="utf-8").splitlines():
    line = line.strip()
    if line and not line.startswith("#") and "=" in line:
        k, _, v = line.partition("=")
        env[k.strip()] = v.strip()

SB_URL = env["SUPABASE_URL"]
SVC = env["SUPABASE_SERVICE_ROLE_KEY"]
BUCKET = "stylo-fino-assets"
CLIENT_NAME = "Stylo Fino"

H = {"apikey": SVC, "Authorization": f"Bearer {SVC}",
     "Content-Type": "application/json", "Prefer": "return=representation"}

# Mapeo de categorías AI → slug de product_categories
# Lo que falte se crea on-the-fly
CATEGORY_MAP = {
    "remera": "remeras",
    "buzo": "buzos",
    "campera": "camperas",
    "pantalon": "pantalones",
    "accesorio": "accesorios",
    # las nuevas se crean si no existen:
    "chaleco": "chalecos",
    "short": "shorts",
    "conjunto": "conjuntos",
    "otro": "otros",
}


def sb_get(path):
    req = urllib.request.Request(f"{SB_URL}/rest/v1/{path}", headers=H)
    return json.loads(urllib.request.urlopen(req, timeout=15).read())


def sb_post(path, body):
    req = urllib.request.Request(
        f"{SB_URL}/rest/v1/{path}",
        data=json.dumps(body).encode("utf-8"),
        headers=H, method="POST",
    )
    try:
        return json.loads(urllib.request.urlopen(req, timeout=15).read())
    except urllib.error.HTTPError as e:
        err = e.read().decode()
        print(f"\n!! POST {path} FAIL {e.code}: {err}")
        print(f"   body keys: {list(body.keys()) if isinstance(body, dict) else body}")
        raise


def sb_patch(path, body):
    req = urllib.request.Request(
        f"{SB_URL}/rest/v1/{path}",
        data=json.dumps(body).encode("utf-8"),
        headers={**H, "Prefer": "return=representation"},
        method="PATCH",
    )
    return json.loads(urllib.request.urlopen(req, timeout=15).read())


def upload_photo(local_path: Path, object_key: str) -> str:
    """Sube y devuelve URL pública. Idempotente con x-upsert."""
    if not local_path.exists():
        return ""
    img_bytes = local_path.read_bytes()
    url = f"{SB_URL}/storage/v1/object/{BUCKET}/{object_key}"
    mime = "image/jpeg" if local_path.suffix.lower() in (".jpg", ".jpeg") else "image/png"
    req = urllib.request.Request(url, data=img_bytes, method="POST", headers={
        "apikey": SVC, "Authorization": f"Bearer {SVC}",
        "Content-Type": mime, "x-upsert": "true",
    })
    try:
        urllib.request.urlopen(req, timeout=30).read()
    except urllib.error.HTTPError as e:
        print(f"  ! Upload error {e.code}: {e.read().decode()[:200]}")
        return ""
    return f"{SB_URL}/storage/v1/object/public/{BUCKET}/{object_key}"


def ensure_category(client_id: str, slug: str, name: str) -> str:
    """Devuelve category_id, creándola si no existe."""
    rows = sb_get(f"product_categories?client_id=eq.{client_id}&slug=eq.{slug}&select=id")
    if rows:
        return rows[0]["id"]
    print(f"  + creando categoría: {name} ({slug})")
    new = sb_post("product_categories", {
        "client_id": client_id, "name": name, "slug": slug,
        "order_num": 99, "active": True,
    })
    return new[0]["id"]


def main():
    # 1. Lookup CLIENT_ID
    clients = sb_get(f"clients?name=eq.{urllib.parse.quote(CLIENT_NAME)}&select=id")
    if not clients:
        print(f"ERROR: cliente '{CLIENT_NAME}' no existe."); sys.exit(1)
    client_id = clients[0]["id"]
    print(f"CLIENT_ID = {client_id}\n")

    # 2. Lookup productos ya sincronizados (idempotencia)
    existing = sb_get(f"client_products?client_id=eq.{client_id}&select=id,tags")
    existing_groups = set()
    for p in existing:
        tags = p.get("tags") or []
        if isinstance(tags, list):
            for t in tags:
                if isinstance(t, str) and t.startswith("group:"):
                    existing_groups.add(t.split(":", 1)[1])
    print(f"Productos ya sincronizados: {len(existing_groups)}")

    # 3. Cargar grupos
    state = json.loads(GROUPS_FILE.read_text(encoding="utf-8"))
    groups = state["groups"]
    print(f"Grupos en local: {len(groups)}\n")

    created = 0
    skipped = 0
    for g in groups:
        gid = g["id"]
        if gid in existing_groups:
            print(f"  - SKIP {gid} (ya sincronizado)")
            skipped += 1
            continue

        # 4. Subir todas las fotos del grupo
        photo_urls = []
        first_ai = None
        for photo_ref in g["photos"]:
            local_path = REPO_ROOT / photo_ref
            if not local_path.exists():
                continue
            object_key = f"products/{gid}/{local_path.name}"
            url = upload_photo(local_path, object_key)
            if url:
                photo_urls.append(url)
                # Leer el AI metadata de la primera foto
                if first_ai is None:
                    ai_path = local_path.with_suffix(".ai.json")
                    if ai_path.exists():
                        first_ai = json.loads(ai_path.read_text(encoding="utf-8"))

        if not photo_urls:
            print(f"  ! {gid} sin fotos subibles — skip")
            continue

        # 5. Resolver categoría
        ai_cat = (first_ai or {}).get("category", "otro").lower()
        cat_slug = CATEGORY_MAP.get(ai_cat, "otros")
        cat_name = cat_slug.capitalize().rstrip("s") if cat_slug != "accesorios" else "Accesorios"
        if cat_slug == "chalecos": cat_name = "Chalecos"
        elif cat_slug == "shorts": cat_name = "Shorts"
        elif cat_slug == "conjuntos": cat_name = "Conjuntos"
        elif cat_slug == "otros": cat_name = "Otros"
        elif cat_slug == "remeras": cat_name = "Remeras"
        elif cat_slug == "buzos": cat_name = "Buzos"
        elif cat_slug == "camperas": cat_name = "Camperas"
        elif cat_slug == "pantalones": cat_name = "Pantalones"
        category_id = ensure_category(client_id, cat_slug, cat_name)

        # 6. Construir tags con todo el AI metadata
        ai_color = (first_ai or {}).get("color_principal", g["color"])
        ai_brand = (first_ai or {}).get("marca_visible") or g.get("brand") or ""
        ai_name = (first_ai or {}).get("nombre_sugerido", f"{ai_cat} {ai_color}").strip()
        ai_code = (first_ai or {}).get("codigo_sugerido", "")
        ai_desc = (first_ai or {}).get("descripcion", "")
        ai_style = (first_ai or {}).get("estilo", "")
        ai_extra_colors = (first_ai or {}).get("colores_extra", [])

        # tags es un array de strings en Supabase. Encodeamos metadata como
        # un único elemento prefix "__ai__:" + JSON serializado.
        metadata = {
            "ai_group": gid,
            "ai_category": ai_cat,
            "ai_color": ai_color,
            "ai_extra_colors": ai_extra_colors,
            "ai_brand": ai_brand,
            "ai_style": ai_style,
            "ai_code_suggested": ai_code,
            "ai_description": ai_desc,
            "photos": photo_urls,
            "primary_photo": photo_urls[0],
            "telegram_msg_ids": [int(Path(p).name.split("_")[0].replace("msg", "")) for p in g["photos"] if "msg" in Path(p).name],
            "tagged": False,
            "tag_status": "pending",
        }
        tags_array = [
            "__ai__:" + json.dumps(metadata, ensure_ascii=False),
            f"group:{gid}",
            f"category:{ai_cat}",
            f"color:{ai_color}",
        ]
        if ai_brand:
            tags_array.append(f"brand:{ai_brand}")

        # 7. Insertar producto pendiente
        new = sb_post("client_products", {
            "client_id": client_id,
            "name": ai_name,
            "description": ai_desc,
            "price": 0,                        # placeholder hasta que el form lo complete
            "image_url": photo_urls[0],
            "category_id": category_id,
            "keywords": [ai_cat, ai_color] + ([ai_brand] if ai_brand else []),
            "stock_status": "pending_tag",
            "active": False,                   # pending_tag — el form lo va a activar al guardar
            "tags": tags_array,
        })
        if new:
            print(f"  ✓ {gid}: {ai_name} ({len(photo_urls)} fotos) → product_id={new[0]['id'][:8]}")
            created += 1

    print(f"\n=== RESUMEN ===")
    print(f"Creados: {created}")
    print(f"Saltados (ya existían): {skipped}")
    print(f"Total productos pendientes en Supabase: {created + skipped}")


if __name__ == "__main__":
    main()
