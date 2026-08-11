"""
run.py — Punto de entrada del flujo Outreach Engine V1.

Uso:
    python flows/outreach_v1/run.py

Qué hace:
    1. Lee leads desde data/input/leads.json
    2. Ejecuta el pipeline completo por cada lead
    3. Guarda resultados en data/output/processed_leads.json
    4. Registra la ejecución en logs/outreach_log.json
"""

import json
import sys
from datetime import datetime
from pathlib import Path

# Permitir imports desde la raíz del proyecto
ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(ROOT))

from flows.outreach_v1.pipeline import procesar_lote

# ── RUTAS ─────────────────────────────────────────────────────────────────────
INPUT_PATH  = ROOT / "data" / "input"  / "leads.json"
OUTPUT_PATH = ROOT / "data" / "output" / "processed_leads.json"
LOG_PATH    = ROOT / "logs"            / "outreach_log.json"


def leer_leads() -> list[dict]:
    with open(INPUT_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def guardar_resultados(resultados: list[dict]) -> None:
    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        json.dump(resultados, f, ensure_ascii=False, indent=2)


def registrar_log(resumen: dict) -> None:
    try:
        with open(LOG_PATH, "r", encoding="utf-8") as f:
            logs = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        logs = []

    logs.append({
        "timestamp": datetime.utcnow().isoformat() + "Z",
        "resumen": resumen
    })

    with open(LOG_PATH, "w", encoding="utf-8") as f:
        json.dump(logs, f, ensure_ascii=False, indent=2)


def imprimir_resumen(resumen: dict, resultados: list[dict]) -> None:
    print("\n" + "─" * 48)
    print("  OUTREACH ENGINE V1 — Resultado")
    print("─" * 48)
    print(f"  Total procesados : {resumen['total']}")
    print(f"  Exitosos         : {resumen['ok']}")
    print(f"  Errores          : {resumen['errores']}")
    print(f"  Tier A           : {resumen['por_tier']['A']}")
    print(f"  Tier B           : {resumen['por_tier']['B']}")
    print(f"  Tier C           : {resumen['por_tier']['C']}")
    print("─" * 48)

    for r in resultados:
        if r["estado"] == "ok":
            print(f"  [{r['tier']}] {r['datos_originales'].get('nombre', '?'):<22} "
                  f"nicho={r['nicho']:<18} score={r['score']}")
        else:
            print(f"  [!] {r['datos_originales'].get('nombre', '?'):<22} ERROR: {r['error']}")

    print("─" * 48)
    print(f"  Resultados → {OUTPUT_PATH.relative_to(ROOT)}")
    print(f"  Log        → {LOG_PATH.relative_to(ROOT)}")
    print("─" * 48 + "\n")


def main():
    print("\nIniciando Outreach Engine V1...")

    leads = leer_leads()
    print(f"Leads cargados: {len(leads)}")

    resultados, resumen = procesar_lote(leads)

    guardar_resultados(resultados)
    registrar_log(resumen)
    imprimir_resumen(resumen, resultados)


if __name__ == "__main__":
    main()
