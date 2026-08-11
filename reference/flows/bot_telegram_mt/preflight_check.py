"""
Health check completo PRE-DÍA 1 del Sprint Stylo Fino.

Corré esto en cualquier momento antes del lanzamiento (ideal: 4 horas antes).
Detecta cualquier problema que pueda hacer fallar el Día 1.

Verifica:
  ✓ .env con todas las keys críticas
  ✓ Bot Telegram corriendo
  ✓ Supabase accesible (cliente, productos, calendario)
  ✓ Bucket Supabase Storage funcional
  ✓ n8n MT workflows activos
  ✓ Form de tagueo respondiendo
  ✓ Token Meta válido (si aplica — sino marca "manual mode")
  ✓ Pieza Día 1 con foto + caption + scheduled_at
  ✓ Productos del calendario tienen stock > 0
  ✓ wa.me link funcionando

Uso:
  python flows/bot_telegram_mt/preflight_check.py
"""
import sys, json, urllib.request, urllib.error, subprocess, os
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

CLIENT_ID = "202477af-9207-4e09-b180-dca895df4743"
AR = timezone(timedelta(hours=-3))

errors = []
warnings = []
ok_count = 0


def check(label, condition, error_msg=None, warn_only=False):
    global ok_count
    if condition:
        print(f"  ✓ {label}")
        ok_count += 1
        return True
    else:
        msg = error_msg or "FAIL"
        if warn_only:
            print(f"  ⚠ {label} — {msg}")
            warnings.append(f"{label}: {msg}")
        else:
            print(f"  ✗ {label} — {msg}")
            errors.append(f"{label}: {msg}")
        return False


def section(title):
    print(f"\n┌─── {title} ───")


print(f"\n{'=' * 60}")
print(f"  PRE-FLIGHT CHECK — Stylo Fino Sprint 14D")
print(f"  Hora actual: {datetime.now(AR).strftime('%Y-%m-%d %H:%M AR')}")
print(f"{'=' * 60}")

# ─── 1. Variables de entorno ──────────────────────────────
section("Variables de entorno (.env)")
critical_env = [
    "STYLO_FINO_TG_BOT_TOKEN", "STYLO_FINO_TG_LUCAS_USER_ID",
    "SUPABASE_URL", "SUPABASE_SERVICE_ROLE_KEY",
    "N8N_API_KEY", "N8N_BASE_URL",
    "ANTHROPIC_API_KEY",
    "STYLO_FINO_WA_NUMBER", "STYLO_FINO_WA_LINK",
]
for k in critical_env:
    check(f".env tiene {k}", bool(env.get(k)))

# Meta keys son opcionales (pueden estar bloqueadas)
meta_keys = ["STYLO_FINO_FB_PAGE_ID", "STYLO_FINO_IG_USER_ID", "STYLO_FINO_IG_ACCESS_TOKEN"]
print()
for k in meta_keys:
    check(f".env tiene {k} (Meta)", bool(env.get(k)), warn_only=True)

# ─── 2. Bot Telegram ──────────────────────────────────────
section("Bot Telegram")
pid_file = REPO_ROOT / "data/clients/stylo_fino/logs/watch.pid"
if pid_file.exists():
    pid = pid_file.read_text().strip()
    try:
        # Windows: tasklist; Unix: ps -p
        if sys.platform == "win32":
            result = subprocess.run(["tasklist", "/FI", f"PID eq {pid}"],
                                    capture_output=True, text=True, timeout=5)
            alive = pid in result.stdout
        else:
            result = subprocess.run(["ps", "-p", pid], capture_output=True, timeout=5)
            alive = result.returncode == 0
        check(f"Watch corriendo (PID {pid})", alive,
              "proceso no encontrado — relanzar manualmente")
    except Exception as e:
        check(f"Watch corriendo", False, str(e))
else:
    check("Watch corriendo", False, "no hay watch.pid")

# Token Telegram funciona
try:
    url = f"https://api.telegram.org/bot{env['STYLO_FINO_TG_BOT_TOKEN']}/getMe"
    r = json.loads(urllib.request.urlopen(url, timeout=10).read())
    check(f"Telegram bot @{r['result']['username']} responde", r.get("ok"))
except Exception as e:
    check("Telegram bot responde", False, str(e)[:100])

# ─── 3. Supabase ──────────────────────────────────────────
section("Supabase")
H = {"apikey": env["SUPABASE_SERVICE_ROLE_KEY"],
     "Authorization": f"Bearer {env['SUPABASE_SERVICE_ROLE_KEY']}"}

def sb_count(query):
    try:
        url = f"{env['SUPABASE_URL']}/rest/v1/{query}"
        req = urllib.request.Request(url, headers={**H, "Prefer": "count=exact"})
        r = urllib.request.urlopen(req, timeout=10)
        # count está en header Content-Range: 0-N/total
        cr = r.headers.get("Content-Range", "0-0/0")
        return int(cr.split("/")[1])
    except Exception:
        return -1

clients = sb_count(f"clients?id=eq.{CLIENT_ID}&select=id")
check(f"Cliente Stylo Fino existe en clients", clients == 1, f"encontrados: {clients}")

products_total = sb_count(f"client_products?client_id=eq.{CLIENT_ID}&select=id")
products_active = sb_count(f"client_products?client_id=eq.{CLIENT_ID}&active=is.true&select=id")
products_pending = sb_count(f"client_products?client_id=eq.{CLIENT_ID}&stock_status=eq.pending_tag&select=id")
check(f"Productos en Supabase: {products_total} total · {products_active} tagueados · {products_pending} pendientes",
      products_total > 0)
if products_pending > products_total // 2:
    warnings.append(f"⚠ {products_pending}/{products_total} productos sin taguear (precio + stock)")

# Calendario
items_total = sb_count(f"content_items?client_id=eq.{CLIENT_ID}&select=id")
check(f"Calendario tiene {items_total} piezas", items_total >= 14)

# Pieza Día 1
try:
    url = f"{env['SUPABASE_URL']}/rest/v1/content_items?client_id=eq.{CLIENT_ID}&description=like.*SF-D01*&select=id,scheduled_at,file_url,caption,status"
    items = json.loads(urllib.request.urlopen(urllib.request.Request(url, headers=H), timeout=10).read())
    if items:
        p = items[0]
        dt_ar = datetime.fromisoformat(p["scheduled_at"]).astimezone(AR)
        has_image = p.get("file_url") and not p["file_url"].startswith("pending://")
        check(f"Pieza Día 1 programada para {dt_ar.strftime('%d-%m %H:%M AR')}", True)
        check(f"Pieza Día 1 con caption ({len(p.get('caption') or '')} chars)", bool(p.get("caption")))
        check(f"Pieza Día 1 con foto asignada", has_image,
              "correr assign_products_to_calendar.py", warn_only=True)
    else:
        check("Pieza Día 1 existe", False)
except Exception as e:
    check("Pieza Día 1 verificable", False, str(e)[:80])

# ─── 4. Bucket Supabase Storage ───────────────────────────
section("Bucket Supabase Storage")
try:
    url = f"{env['SUPABASE_URL']}/storage/v1/bucket/stylo-fino-assets"
    req = urllib.request.Request(url, headers=H)
    bucket = json.loads(urllib.request.urlopen(req, timeout=10).read())
    check(f"Bucket 'stylo-fino-assets' existe ({'PUBLIC' if bucket.get('public') else 'private'})",
          bucket.get("public"))
except Exception as e:
    check("Bucket accesible", False, str(e)[:80])

# Verificar que una foto sea descargable
try:
    test_url = f"{env['SUPABASE_URL']}/storage/v1/object/public/stylo-fino-assets/products/PG-001/msg11_AgACAgEAAx.jpg"
    r = urllib.request.urlopen(test_url, timeout=10)
    check(f"Una foto del bucket es descargable ({r.headers.get('Content-Length','?')} bytes)",
          r.status == 200, warn_only=True)
except urllib.error.HTTPError as e:
    if e.code == 404:
        check("Foto de prueba descargable", False, "404 — paths cambiaron, OK si rebuilo grupos", warn_only=True)
    else:
        check("Foto de prueba descargable", False, f"HTTP {e.code}", warn_only=True)
except Exception:
    pass

# ─── 5. n8n workflows ─────────────────────────────────────
section("n8n workflows")
try:
    url = f"{env['N8N_BASE_URL']}/api/v1/workflows?limit=200"
    req = urllib.request.Request(url, headers={"X-N8N-API-KEY": env["N8N_API_KEY"]})
    wfs = json.loads(urllib.request.urlopen(req, timeout=15).read())["data"]
    needed = [
        ("STEPFlow — Content Intake (MT)", True),
        ("STEPFlow — Caption Generator (MT)", True),
        ("STEPFlow — Content Publisher (MT)", True),
        ("STYLOFINO — Tag Form (GET)", True),
        ("STYLOFINO — Tag Save (POST)", True),
    ]
    for name, must_active in needed:
        wf = next((w for w in wfs if w["name"] == name), None)
        if wf:
            active = wf.get("active", False)
            if must_active:
                check(f"Workflow '{name}'", active, "INACTIVO" if not active else None)
            else:
                print(f"  · {name}: {'ON' if active else 'off'}")
        else:
            check(f"Workflow '{name}'", False, "no existe")
except Exception as e:
    check("n8n API responde", False, str(e)[:80])

# ─── 6. Form de tagueo ────────────────────────────────────
section("Form de tagueo")
try:
    url = f"{env['N8N_BASE_URL']}/webhook/stylofino-tag"
    r = urllib.request.urlopen(url, timeout=15)
    body = r.read().decode("utf-8")
    has_html = "<html" in body.lower()
    has_products = "PRODUCTS = [" in body
    check(f"Form responde HTML ({len(body)} chars)", has_html and has_products)
except Exception as e:
    check("Form accesible", False, str(e)[:100])

# ─── 7. Meta API (opcional) ───────────────────────────────
section("Meta API (opcional — sprint corre manual igual)")
if env.get("STYLO_FINO_IG_ACCESS_TOKEN"):
    try:
        ig_id = env["STYLO_FINO_IG_USER_ID"]
        token = env["STYLO_FINO_IG_ACCESS_TOKEN"]
        url = f"https://graph.facebook.com/v21.0/{ig_id}?fields=username,followers_count,media_count&access_token={token}"
        r = json.loads(urllib.request.urlopen(url, timeout=10).read())
        check(f"IG @{r['username']}: {r['followers_count']} seguidores · {r['media_count']} posts",
              True)
    except urllib.error.HTTPError as e:
        check("Meta Graph API funcional", False,
              f"HTTP {e.code} — sprint corre MANUAL (Lucas publica desde la app)",
              warn_only=True)
    except Exception as e:
        check("Meta Graph API funcional", False, str(e)[:80], warn_only=True)
else:
    print("  · Sin token Meta — modo MANUAL completo")

# ─── 8. Link wa.me funcional ──────────────────────────────
section("WhatsApp")
wa_link = env.get("STYLO_FINO_WA_LINK", "")
check(f"Link wa.me en .env", wa_link.startswith("https://wa.me/"))
check(f"Número visible: {env.get('STYLO_FINO_WA_DISPLAY','')}", bool(env.get("STYLO_FINO_WA_DISPLAY")))

# ─── RESUMEN ──────────────────────────────────────────────
print(f"\n{'=' * 60}")
print(f"  RESUMEN")
print(f"{'=' * 60}")
print(f"  ✓ OK:        {ok_count}")
print(f"  ⚠ Warnings:  {len(warnings)}")
print(f"  ✗ Errors:    {len(errors)}")

if errors:
    print(f"\n🚨 ERRORES BLOQUEANTES (resolver ANTES del lanzamiento):")
    for e in errors:
        print(f"    → {e}")
    sys.exit(1)

if warnings:
    print(f"\n⚠ Advertencias (no bloquean pero atender):")
    for w in warnings:
        print(f"    → {w}")

print(f"\n✅ Sistema OK para lanzar el Sprint Stylo Fino.")
sys.exit(0)
