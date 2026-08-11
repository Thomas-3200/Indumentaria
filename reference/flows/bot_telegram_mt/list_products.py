"""
Lista los productos de un cliente con cantidad de fotos.

Uso:
    python flows/bot_telegram_mt/list_products.py --client stylo_fino
    python flows/bot_telegram_mt/list_products.py --client stylo_fino --duplicates

Sirve para:
  - Ver qué productos tienen pocas fotos (rotación se rompe)
  - Detectar duplicados (mismo nombre o muy similares) creados por mandar fotos
    extras en distintos días.
"""
from __future__ import annotations

import json
import sys
import urllib.request
import urllib.parse
from pathlib import Path
from collections import defaultdict

sys.stdout.reconfigure(encoding='utf-8') if hasattr(sys.stdout, 'reconfigure') else None
sys.path.insert(0, str(Path(__file__).resolve().parent))
from client_config import load_client_config


def extract_photos(tags):
    if not tags:
        return []
    for t in tags:
        if isinstance(t, str) and t.startswith('__ai__:'):
            try:
                meta = json.loads(t[len('__ai__:'):])
                return list(dict.fromkeys(meta.get('photos') or []))  # uniq orden
            except Exception:
                pass
    return []


def extract_brand_color(tags):
    brand = color = ""
    for t in tags or []:
        if isinstance(t, str):
            if t.startswith('brand:'): brand = t[6:]
            elif t.startswith('color:'): color = t[6:]
    return brand, color


def main():
    slug = "stylo_fino"
    show_duplicates = False
    for i, a in enumerate(sys.argv):
        if a == "--client" and i + 1 < len(sys.argv):
            slug = sys.argv[i + 1]
        elif a in ("--duplicates", "--dups"):
            show_duplicates = True

    cfg = load_client_config(slug)
    if not cfg.supabase_url or not cfg.supabase_service_role_key:
        print("ERROR: Supabase no configurado.")
        sys.exit(2)

    H = {"apikey": cfg.supabase_service_role_key,
         "Authorization": f"Bearer {cfg.supabase_service_role_key}"}
    url = (f"{cfg.supabase_url}/rest/v1/client_products"
           f"?client_id=eq.{cfg.client_uuid}"
           f"&select=id,name,tags,image_url,active,price"
           f"&order=name.asc")
    rows = json.loads(urllib.request.urlopen(
        urllib.request.Request(url, headers=H), timeout=15).read())

    print(f"\n📦 Productos de {cfg.display_name} ({len(rows)} totales)\n")

    # Header
    print(f"{'ID':10} {'Fotos':>5} {'Active':>6} {'Precio':>8} | {'Producto':40} | brand/color")
    print("-" * 110)

    for p in rows:
        photos = extract_photos(p.get('tags'))
        brand, color = extract_brand_color(p.get('tags'))
        n_photos = len(photos)
        active = "✓" if p.get('active') else "·"
        price = f"${p.get('price', 0):,}" if p.get('price') else "-"
        marker = "⚠" if n_photos < 4 else " "
        name = p['name'][:38]
        print(f"{p['id'][:8]:10} {marker}{n_photos:>4} {active:>6} {price:>8} | {name:<40} | {brand}/{color}")

    print()
    multi = [p for p in rows if len(extract_photos(p.get('tags'))) >= 4]
    one = [p for p in rows if len(extract_photos(p.get('tags'))) == 1]
    print(f"  Con 4+ fotos (rotación completa OK): {len(multi)}")
    print(f"  Con solo 1 foto (warning al operador):  {len(one)}")
    print(f"  Total:                                    {len(rows)}")

    if show_duplicates:
        print(f"\n🔍 Detectando posibles duplicados (mismo brand+color+category)...\n")
        groups = defaultdict(list)
        for p in rows:
            brand, color = extract_brand_color(p.get('tags'))
            # Categoría desde el name (primer palabra)
            cat = p['name'].split()[0].lower() if p['name'] else "?"
            key = (cat, color, brand)
            groups[key].append(p)
        dups = {k: v for k, v in groups.items() if len(v) > 1}
        if not dups:
            print("  Sin duplicados detectados.")
        else:
            for (cat, color, brand), prods in dups.items():
                print(f"  ⚠ {cat} / {color} / {brand} → {len(prods)} productos:")
                for p in prods:
                    n = len(extract_photos(p.get('tags')))
                    print(f"      - id={p['id'][:8]}  fotos={n}  '{p['name']}'  active={p.get('active')}")
            print(f"\n💡 Para unir las fotos de un duplicado en el original:")
            print(f"   python flows/bot_telegram_mt/merge_photos.py --client {slug} "
                  f"--from <id_duplicado> --to <id_original>")


if __name__ == "__main__":
    main()
