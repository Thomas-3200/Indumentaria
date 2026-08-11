"""
Re-agrupa las fotos del inbox usando una regla más estricta:
   categoría + color + MARCA  (no solo categoría + color)

Esto separa correctamente productos del mismo color pero distinta marca
(ej. campera negra Nike vs campera negra Adidas).

Lee los ai.json ya generados (no llama Claude de nuevo) y reescribe
product_groups.json desde cero.
"""
import sys, json
from pathlib import Path
from datetime import datetime, timezone

sys.stdout.reconfigure(encoding='utf-8') if hasattr(sys.stdout, 'reconfigure') else None

REPO_ROOT = Path(__file__).resolve().parents[2]
CLIENT_DIR = REPO_ROOT / "data" / "clients" / "stylo_fino"
INBOX_ROOT = CLIENT_DIR / "inbox"
GROUPS_FILE = CLIENT_DIR / "product_groups.json"


def norm(v):
    return str(v or "").strip().lower()


# Recorrer TODAS las subcarpetas de inbox (cada fecha)
photos_with_ai = []
all_ai = []
for date_dir in sorted(INBOX_ROOT.iterdir()):
    if not date_dir.is_dir():
        continue
    date_str = date_dir.name  # ej "2026-05-13"
    for f in date_dir.glob("*.ai.json"):
        try:
            msg_id = int(f.name.split("_")[0].replace("msg", ""))
        except (ValueError, IndexError):
            continue
        all_ai.append((date_str, msg_id, f))

# Ordenar por fecha + msg_id (cronológico)
all_ai.sort(key=lambda x: (x[0], x[1]))

for date_str, msg_id, f in all_ai:
    try:
        ai = json.loads(f.read_text(encoding="utf-8"))
    except Exception:
        continue
    if "_error" in ai:
        continue
    photo_jpg = f.parent / f.name.replace(".ai.json", ".jpg")
    if not photo_jpg.exists():
        continue
    photos_with_ai.append({
        "photo_ref": f"data/clients/stylo_fino/inbox/{date_str}/{photo_jpg.name}",
        "msg_id": msg_id,
        "date": date_str,
        "category": norm(ai.get("category")),
        "color": norm(ai.get("color_principal")),
        "brand": norm(ai.get("marca_visible")),
        "ai": ai,
    })

print(f"Fotos con AI válida: {len(photos_with_ai)}\n")

# Agrupar por (categoría, color, marca, FECHA)
# La fecha separa envíos distintos: si Lucas mandó chaleco Nike negro el 13-05
# y Leo manda otro chaleco Nike negro el 15-05, son productos distintos.
groups_map = {}
group_order = []
for p in photos_with_ai:
    key = (p["category"], p["color"], p["brand"], p["date"])
    if key not in groups_map:
        seq = len(group_order) + 1
        gid = f"PG-{seq:03d}"
        groups_map[key] = {
            "id": gid,
            "seq": seq,
            "category": p["category"],
            "color": p["color"],
            "brand": p["brand"],
            "date": p["date"],
            "first_photo_ts": f"{p['date']}T05:00:00Z",
            "last_photo_ts": f"{p['date']}T05:00:00Z",
            "photos": [],
            "tagged": False,
        }
        group_order.append(key)
    groups_map[key]["photos"].append(p["photo_ref"])

groups_list = [groups_map[k] for k in group_order]
state = {"groups": groups_list, "next_seq": len(groups_list) + 1}
GROUPS_FILE.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")

print(f"Grupos reconstruidos: {len(groups_list)}\n")
for g in groups_list:
    brand = f" / {g['brand']}" if g['brand'] else ""
    print(f"  {g['id']}: {g['category']} {g['color']}{brand}  ({len(g['photos'])} fotos)")
