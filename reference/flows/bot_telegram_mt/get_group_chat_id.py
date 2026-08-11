"""
Helper para descubrir el chat_id de un grupo de Telegram donde está agregado el bot.

Uso:
    1. Crear un grupo en Telegram.
    2. Agregar al bot del cliente como administrador (con permisos: enviar mensajes,
       editar mensajes propios, leer mensajes).
    3. Mandar un mensaje cualquiera en el grupo (ej "/start" o "test").
    4. Correr este script:
         python flows/bot_telegram_mt/get_group_chat_id.py --client <slug>
    5. El script lista los grupos donde el bot vio mensajes recientes.
       Copiar el chat_id (será un número NEGATIVO, ej: -1001234567890)
       y pegarlo al .env como:
         <SLUG>_TG_PUBLISH_CHAT_ID=-1001234567890

IMPORTANTE: Telegram solo devuelve actualizaciones de los últimos ~24 hs.
            Si el grupo está vacío de actividad reciente, mandá un mensaje
            nuevo justo antes de correr este script.

IMPORTANTE 2: Si el bot está en modo watch en otra ventana, las actualizaciones
              YA fueron consumidas por ese proceso. Tenés que apagar el bot
              temporalmente, mandar un mensaje en el grupo, correr este script,
              y volver a prender el bot. O usar --reset-offset para forzar
              que el bot re-lea desde el último offset guardado.
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


def main():
    # Parse args
    slug = "stylo_fino"
    for i, a in enumerate(sys.argv):
        if a == "--client" and i + 1 < len(sys.argv):
            slug = sys.argv[i + 1]

    cfg = load_client_config(slug)
    if not cfg.tg_bot_token:
        print(f"ERROR: {cfg.env_prefix}_TG_BOT_TOKEN no configurado en .env")
        sys.exit(2)

    print(f"\n🔍 Buscando grupos donde está el bot @{cfg.tg_bot_username or '(?)'}")
    print(f"   Cliente: {cfg.display_name} ({cfg.slug})\n")

    # getUpdates sin consumir (offset=0 trae las últimas, pero hay que evitar
    # competir con el bot en watch). Usar offset=-100 para traer las últimas 100.
    url = f"https://api.telegram.org/bot{cfg.tg_bot_token}/getUpdates?offset=-100&limit=100"
    try:
        resp = json.loads(urllib.request.urlopen(url, timeout=15).read())
    except urllib.error.HTTPError as e:
        print(f"ERROR HTTP {e.code}: {e.read().decode()[:200]}")
        sys.exit(1)

    if not resp.get("ok"):
        print(f"ERROR Telegram: {resp}")
        sys.exit(1)

    updates = resp.get("result", [])
    if not updates:
        print("⚠ Sin actualizaciones recientes en el bot.")
        print("   Mandá un mensaje cualquiera en el grupo y volvé a correr.")
        return

    # Recolectar chats únicos
    seen_chats = {}
    for upd in updates:
        msg = upd.get("message") or upd.get("edited_message") or {}
        chat = msg.get("chat", {})
        if not chat:
            continue
        cid = chat.get("id")
        ctype = chat.get("type", "?")
        title = chat.get("title") or chat.get("username") or chat.get("first_name", "(sin título)")
        if cid not in seen_chats:
            seen_chats[cid] = {"type": ctype, "title": title, "samples": []}
        last_msg = msg.get("text") or msg.get("caption") or "(media sin texto)"
        seen_chats[cid]["samples"].append(last_msg[:50])

    if not seen_chats:
        print("⚠ Sin chats encontrados en las actualizaciones recientes.")
        return

    print(f"Chats encontrados ({len(seen_chats)}):\n")
    for cid, info in seen_chats.items():
        is_group = info["type"] in ("group", "supergroup")
        marker = "✓ GRUPO" if is_group else "  (1-a-1)"
        print(f"{marker}  chat_id={cid:>20}  type={info['type']:<12} título='{info['title']}'")
        for s in info["samples"][:2]:
            print(f"           último msg: {s}")
        print()

    groups = [(cid, info) for cid, info in seen_chats.items() if info["type"] in ("group", "supergroup")]
    if groups:
        print(f"\n💡 Para usar el primer grupo como destino de publicaciones, agregá al .env:")
        for cid, info in groups:
            print(f"   {cfg.env_prefix}_TG_PUBLISH_CHAT_ID={cid}    # {info['title']}")
        print("\nDespués reiniciá el bot watch y volvé a correr send_daily_agenda.")
    else:
        print("⚠ No hay grupos en las actualizaciones recientes — solo chats 1-a-1.")
        print("   Asegurate de:")
        print("   1) Haber creado un grupo en Telegram")
        print("   2) Haber agregado el bot como admin (con permiso de enviar mensajes)")
        print("   3) Haber mandado al menos 1 mensaje en el grupo justo antes de correr esto")


if __name__ == "__main__":
    main()
