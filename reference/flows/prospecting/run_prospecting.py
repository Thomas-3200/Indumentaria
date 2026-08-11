"""
run_prospecting.py — Orquestador del flujo de búsqueda de prospectos.

Uso:
    python flows/prospecting/run_prospecting.py

Qué hace:
    1. Lee config desde .env (nicho, ciudad, cantidad, API key)
    2. Busca negocios via Google Places API
    3. Visita cada sitio web y extrae email de contacto
    4. Guarda resultados en data/input/leads.json
    5. Muestra resumen: encontrados / con email / sin email

Siguiente paso tras ejecutar:
    python flows/outreach_v1/run.py      → procesa y personaliza mensajes
    python flows/outreach_v1/send_emails.py → envía emails
"""

import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(ROOT))

try:
    from dotenv import load_dotenv
    load_dotenv(ROOT / ".env")
except ImportError:
    pass

from flows.prospecting.places_searcher  import buscar_negocios
from flows.prospecting.email_finder     import encontrar_email
from flows.prospecting.prospect_builder import construir_lead, filtrar_duplicados

# ── CONFIG DESDE .env ─────────────────────────────────────────────────────────

NICHO    = os.getenv("PROSPECTING_NICHO",    "inmobiliaria")
CIUDAD   = os.getenv("PROSPECTING_CIUDAD",   "Buenos Aires")
CANTIDAD = int(os.getenv("PROSPECTING_CANTIDAD", "20"))

LEADS_PATH = ROOT / "data" / "input" / "leads.json"


# ── HELPERS ───────────────────────────────────────────────────────────────────

def cargar_leads_existentes() -> list[dict]:
    try:
        with open(LEADS_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return []


def guardar_leads(leads: list[dict]) -> None:
    LEADS_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(LEADS_PATH, "w", encoding="utf-8") as f:
        json.dump(leads, f, ensure_ascii=False, indent=2)


# ── MAIN ──────────────────────────────────────────────────────────────────────

def main():
    print("\n" + "─" * 56)
    print("  STEPFLOW — Búsqueda de prospectos")
    print(f"  Nicho: {NICHO} · Ciudad: {CIUDAD} · Cantidad: {CANTIDAD}")
    print("─" * 56)

    # 1. Cargar leads existentes (para evitar duplicados)
    leads_existentes = cargar_leads_existentes()
    print(f"  Leads existentes en base: {len(leads_existentes)}")

    # 2. Buscar negocios en Google Places
    print(f"\n  Buscando negocios en Google Places...")
    try:
        negocios = buscar_negocios(NICHO, CIUDAD, CANTIDAD)
    except Exception as e:
        print(f"\n  ERROR al buscar en Google Places: {e}")
        print("  Verificá que GOOGLE_PLACES_API_KEY esté configurada en .env")
        return

    print(f"  Negocios encontrados: {len(negocios)}")

    # 3. Para cada negocio, buscar email y construir lead
    print(f"\n  Extrayendo emails de sitios web...")
    print("─" * 56)

    leads_nuevos    = []
    con_email       = 0
    sin_email       = 0
    sin_web         = 0

    for i, negocio in enumerate(negocios, 1):
        nombre  = negocio.get("nombre", "?")
        website = negocio.get("website", "")

        if not website:
            print(f"  [{i:02d}] {nombre:<35} sin web")
            sin_web += 1
            email = None
        else:
            email = encontrar_email(website)
            if email:
                print(f"  [{i:02d}] {nombre:<35} ✓ {email}")
                con_email += 1
            else:
                print(f"  [{i:02d}] {nombre:<35} – sin email ({website})")
                sin_email += 1

        lead = construir_lead(negocio, email, NICHO, CIUDAD)
        leads_nuevos.append(lead)

    # 4. Filtrar duplicados
    leads_sin_duplicados = filtrar_duplicados(leads_nuevos, leads_existentes)
    duplicados = len(leads_nuevos) - len(leads_sin_duplicados)

    # 5. Guardar
    leads_finales = leads_existentes + leads_sin_duplicados
    guardar_leads(leads_finales)

    # 6. Resumen
    print("─" * 56)
    print(f"  Encontrados       : {len(negocios)}")
    print(f"  Con email         : {con_email}")
    print(f"  Sin email         : {sin_email}")
    print(f"  Sin web           : {sin_web}")
    print(f"  Duplicados omit.  : {duplicados}")
    print(f"  Agregados a base  : {len(leads_sin_duplicados)}")
    print(f"  Total en base     : {len(leads_finales)}")
    print("─" * 56)
    print(f"\n  Guardado en: data/input/leads.json")
    print(f"\n  Próximo paso:")
    print(f"    python flows/outreach_v1/run.py")
    print(f"    python flows/outreach_v1/send_emails.py")
    print("─" * 56 + "\n")


if __name__ == "__main__":
    main()
