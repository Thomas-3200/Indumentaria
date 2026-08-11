"""
Stylo Fino — Setup Check

Valida que el intake esté listo para recibir a Lucas.
No descarga nada. Solo chequea.

Uso:
    python flows/bot_telegram_mt/setup_check.py
"""

from __future__ import annotations

import json
import sys
import urllib.request
import urllib.error
from pathlib import Path

# Forzar UTF-8 en consola Windows (Python 3.7+)
try:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except Exception:
    pass

REPO_ROOT = Path(__file__).resolve().parents[2]


def load_env(env_path: Path) -> dict[str, str]:
    env: dict[str, str] = {}
    if not env_path.exists():
        return env
    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, _, v = line.partition("=")
        env[k.strip()] = v.strip()
    return env


def check(label: str, ok: bool, detail: str = "") -> bool:
    mark = "OK  " if ok else "FAIL"
    line = f"[{mark}] {label}"
    if detail:
        line += f" — {detail}"
    print(line)
    return ok


def main() -> int:
    print("Stylo Fino — Intake setup check\n")
    all_ok = True

    # 1. .env presente
    env_file = REPO_ROOT / ".env"
    if not check(".env existe", env_file.exists(), str(env_file)):
        print("\nFalta crear .env. Copialo desde .env.example y completá el token.")
        return 1
    env = load_env(env_file)

    # 2. .env en gitignore
    gi = REPO_ROOT / ".gitignore"
    gi_has_env = gi.exists() and ".env" in gi.read_text(encoding="utf-8").splitlines()
    check(".env en .gitignore", gi_has_env)
    all_ok &= gi_has_env

    # 3. Token presente
    token = env.get("STYLO_FINO_TG_BOT_TOKEN", "")
    has_token = bool(token) and ":" in token
    check("STYLO_FINO_TG_BOT_TOKEN cargado", has_token,
          f"len={len(token)}" if token else "vacío")
    all_ok &= has_token
    if not has_token:
        return 1

    # 4. Token válido contra Telegram
    try:
        resp = urllib.request.urlopen(
            f"https://api.telegram.org/bot{token}/getMe", timeout=15
        ).read().decode()
        data = json.loads(resp)
        bot_ok = data.get("ok") and data["result"]["is_bot"]
        username = data["result"].get("username", "?")
        check("getMe responde OK", bot_ok, f"@{username}")
        all_ok &= bool(bot_ok)
        # Verificar que coincide con el username configurado
        configured = env.get("STYLO_FINO_TG_BOT_USERNAME", "")
        if configured:
            match = configured.lstrip("@") == username
            check("username coincide con .env", match,
                  f"{configured} vs @{username}")
            all_ok &= match
    except (urllib.error.HTTPError, urllib.error.URLError) as e:
        check("getMe responde OK", False, str(e))
        all_ok = False

    # 5. Lucas user_id (informativo, no bloqueante para el setup)
    lucas = env.get("STYLO_FINO_TG_LUCAS_USER_ID", "")
    lucas_ok = bool(lucas) and lucas.isdigit()
    detail = lucas if lucas_ok else (
        "vacío — el bot va a aceptar a CUALQUIER usuario hasta que cargues el ID de Lucas"
    )
    check("STYLO_FINO_TG_LUCAS_USER_ID configurado", lucas_ok, detail)

    # 6. Approval chat_id
    approval = env.get("STYLO_FINO_TG_APPROVAL_CHAT_ID", "")
    if not approval:
        check("STYLO_FINO_TG_APPROVAL_CHAT_ID configurado", False,
              "vacío — todavía no hay grupo de aprobaciones")
    else:
        check("STYLO_FINO_TG_APPROVAL_CHAT_ID configurado", True, approval)

    # 7. Directorios
    client_dir = REPO_ROOT / "data" / "clients" / "stylo_fino"
    for sub in ("products", "inbox"):
        p = client_dir / sub
        check(f"data/clients/stylo_fino/{sub}/ existe", p.exists(), str(p))
        all_ok &= p.exists()

    # 8. Log
    log_file = client_dir / "intake_log.jsonl"
    print(f"[INFO] intake_log.jsonl: "
          f"{'existe (' + str(log_file.stat().st_size) + ' bytes)' if log_file.exists() else 'vacío todavía'}")

    # 9. Offset
    offset_file = client_dir / ".last_update_id"
    if offset_file.exists():
        print(f"[INFO] último update_id procesado: {offset_file.read_text().strip()}")
    else:
        print("[INFO] sin offset (primera corrida pendiente)")

    print()
    print(f"Lucas user_id: {'configurado' if lucas_ok else 'PENDIENTE (lo cargás después de su 1er mensaje)'}")
    print(f"Approval chat: {'configurado' if approval else 'PENDIENTE (lo cargás después de crear el grupo)'}")
    print()
    if all_ok:
        print("[READY] Setup minimo OK. Podes correr el intake:")
        print("   python flows/bot_telegram_mt/fetch_intake.py --watch")
        return 0
    else:
        print("[BLOCK] Hay items obligatorios sin completar. Mira los FAIL de arriba.")
        return 1


if __name__ == "__main__":
    sys.exit(main())
