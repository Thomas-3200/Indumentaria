"""
Une las fotos de un producto duplicado en otro producto (el "original").

Caso de uso: Lucas mandó fotos extras hoy de un producto que ya estaba cargado
de hace varios días. El sistema crea un producto duplicado nuevo (porque la
agrupación incluye la fecha). Este script lo une al original sin perder fotos.

Uso:
    # Dry-run (recomendado primero, te muestra qué va a hacer)
    python flows/bot_telegram_mt/merge_photos.py \\
        --client stylo_fino \\
        --from <id_del_duplicado> \\
        --to <id_del_original> \\
        --dry-run

    # Aplicar de verdad
    python flows/bot_telegram_mt/merge_photos.py \\
        --client stylo_fino \\
        --from <id_del_duplicado> \\
        --to <id_del_original>

Qué hace:
  1. Lee tags y photos[] de ambos productos
  2. Mergea photos del FROM en el TO (sin duplicados, mantiene orden)
  3. PATCHea el TO en Supabase con la lista nueva
  4. Marca el FROM como active=false (no lo borra — queda para auditoría)

NO se borra el FROM. Si querés borrarlo después, hacelo desde el Supabase UI
después de confirmar que el TO quedó bien.
"""
from __future__ import annotations

import json
import sys
import urllib.request
import urllib.error
from pathlib import Path

sys.stdout.reconfigure(encoding='utf-8') if hasattr(sys.stdout, 'reconfigure') else None
sys.path.insert(0, str(Path(__file__).resolve().parent))
from client_config import load_client_config


def get_product(sb_url, headers, pid):
    url = f"{sb_url}/rest/v1/client_products?id=eq.{pid}&select=*"
    rows = json.loads(urllib.request.urlopen(
        urllib.request.Request(url, headers=headers), timeout=15).read())
    return rows[0] if rows else None


def parse_ai_meta(tags):
    """Devuelve (idx_del_tag_ai, meta_dict, photos_list)."""
    for i, t in enumerate(tags or []):
        if isinstance(t, str) and t.startswith('__ai__:'):
            try:
                meta = json.loads(t[len('__ai__:'):])
                photos = list(dict.fromkeys(meta.get('photos') or []))
                return i, meta, photos
            except Exception:
                pass
    return None, {}, []


def main():
    slug = "stylo_fino"
    src_id = dst_id = None
    dry = False
    for i, a in enumerate(sys.argv):
        if a == "--client" and i + 1 < len(sys.argv):
            slug = sys.argv[i + 1]
        elif a == "--from" and i + 1 < len(sys.argv):
            src_id = sys.argv[i + 1]
        elif a == "--to" and i + 1 < len(sys.argv):
            dst_id = sys.argv[i + 1]
        elif a == "--dry-run":
            dry = True

    if not src_id or not dst_id:
        print("ERROR: usar --from <id_duplicado> --to <id_original>")
        print(__doc__)
        sys.exit(2)

    cfg = load_client_config(slug)
    sb_url = cfg.supabase_url
    svc = cfg.supabase_service_role_key
    H_R = {"apikey": svc, "Authorization": f"Bearer {svc}"}
    H_W = {**H_R, "Content-Type": "application/json", "Prefer": "return=representation"}

    # Buscar ambos productos (puede recibir ID parcial — completarlos)
    def resolve_id(partial):
        url = f"{sb_url}/rest/v1/client_products?id=like.{partial}*&client_id=eq.{cfg.client_uuid}&select=id"
        rows = json.loads(urllib.request.urlopen(
            urllib.request.Request(url, headers=H_R), timeout=10).read())
        if not rows:
            return None
        if len(rows) > 1:
            print(f"⚠ '{partial}' matchea {len(rows)} productos. Usá el ID completo.")
            sys.exit(2)
        return rows[0]['id']

    if len(src_id) < 36: src_id = resolve_id(src_id) or src_id
    if len(dst_id) < 36: dst_id = resolve_id(dst_id) or dst_id

    src = get_product(sb_url, H_R, src_id)
    dst = get_product(sb_url, H_R, dst_id)
    if not src:
        print(f"ERROR: no encontré el producto FROM (id={src_id})")
        sys.exit(2)
    if not dst:
        print(f"ERROR: no encontré el producto TO (id={dst_id})")
        sys.exit(2)

    print(f"\n🔗 MERGE de fotos")
    print(f"   Cliente: {cfg.display_name}")
    print(f"   FROM:    {src['id'][:8]}  '{src['name']}'  active={src.get('active')}")
    print(f"   TO:      {dst['id'][:8]}  '{dst['name']}'  active={dst.get('active')}\n")

    _, src_meta, src_photos = parse_ai_meta(src.get('tags'))
    dst_idx, dst_meta, dst_photos = parse_ai_meta(dst.get('tags'))

    print(f"   Fotos FROM: {len(src_photos)}")
    print(f"   Fotos TO:   {len(dst_photos)}")

    # Mergear sin duplicados (preserva orden: TO existentes primero, luego nuevas del FROM)
    merged = list(dst_photos)
    nuevas = 0
    for p in src_photos:
        if p not in merged:
            merged.append(p)
            nuevas += 1

    print(f"   Nuevas a sumar al TO: {nuevas}")
    print(f"   Total después del merge: {len(merged)}\n")

    if nuevas == 0:
        print("Nada para mergear (TO ya tiene todas las fotos). Salida.")
        return

    # Construir nuevos tags del TO con photos actualizado
    new_meta = dict(dst_meta) if dst_meta else {}
    new_meta['photos'] = merged
    new_meta['primary_photo'] = merged[0]
    new_meta_tag = "__ai__:" + json.dumps(new_meta, ensure_ascii=False)

    new_tags = list(dst.get('tags') or [])
    if dst_idx is not None:
        new_tags[dst_idx] = new_meta_tag
    else:
        new_tags.append(new_meta_tag)

    print("Cambios a aplicar:")
    print(f"  TO ({dst_id[:8]}): tags actualizado con {len(merged)} fotos")
    print(f"  TO ({dst_id[:8]}): image_url se mantiene = {dst.get('image_url')[:60]}...")
    print(f"  FROM ({src_id[:8]}): active=true → active=false (NO se borra)\n")

    if dry:
        print("DRY-RUN — no se aplica nada.")
        return

    # PATCH TO
    body = json.dumps({"tags": new_tags}).encode("utf-8")
    req = urllib.request.Request(
        f"{sb_url}/rest/v1/client_products?id=eq.{dst_id}",
        data=body, headers=H_W, method="PATCH")
    try:
        urllib.request.urlopen(req, timeout=15).read()
        print(f"✓ TO actualizado: {len(merged)} fotos totales")
    except urllib.error.HTTPError as e:
        print(f"✗ ERROR PATCH TO: {e.code} {e.read().decode()[:200]}")
        sys.exit(1)

    # Deactivar FROM (no borrar)
    body = json.dumps({"active": False}).encode("utf-8")
    req = urllib.request.Request(
        f"{sb_url}/rest/v1/client_products?id=eq.{src_id}",
        data=body, headers={**H_W, "Prefer": "return=minimal"}, method="PATCH")
    try:
        urllib.request.urlopen(req, timeout=15).read()
        print(f"✓ FROM marcado como active=false (no eliminado)")
    except urllib.error.HTTPError as e:
        print(f"⚠ No pude desactivar FROM: {e.code}")

    print(f"\n✅ Merge listo. Verificá con:")
    print(f"   python flows/bot_telegram_mt/list_products.py --client {slug}")


if __name__ == "__main__":
    main()
