"""
pipeline.py — Orquesta el procesamiento completo de un lead.

Flujo:
    lead (dict)
        → classifier   → nicho
        → prioritizer  → score, tier
        → message_generator → mensaje personalizado
        → resultado (dict)
"""

from datetime import datetime
from flows.outreach_v1.classifier import clasificar
from flows.outreach_v1.prioritizer import priorizar
from flows.outreach_v1.message_generator import generar_mensaje


def procesar_lead(lead: dict) -> dict:
    lead_id = lead.get("id", "sin_id")
    timestamp = datetime.utcnow().isoformat() + "Z"

    try:
        nicho = clasificar(lead)
        prioridad = priorizar(lead, nicho)
        mensaje = generar_mensaje(lead, nicho)

        resultado = {
            "lead_id": lead_id,
            "procesado_en": timestamp,
            "estado": "ok",
            "datos_originales": lead,
            "nicho": nicho,
            "score": prioridad["score"],
            "tier": prioridad["tier"],
            "detalle_score": prioridad["detalle_score"],
            "mensaje_generado": mensaje["texto"],
            "template_version": mensaje["template_version"],
            "error": None
        }

    except Exception as e:
        resultado = {
            "lead_id": lead_id,
            "procesado_en": timestamp,
            "estado": "error",
            "datos_originales": lead,
            "nicho": None,
            "score": None,
            "tier": None,
            "detalle_score": None,
            "mensaje_generado": None,
            "template_version": None,
            "error": str(e)
        }

    return resultado


def procesar_lote(leads: list[dict]) -> tuple[list[dict], dict]:
    resultados = []
    resumen = {"total": 0, "ok": 0, "errores": 0, "por_tier": {"A": 0, "B": 0, "C": 0}}

    for lead in leads:
        resultado = procesar_lead(lead)
        resultados.append(resultado)

        resumen["total"] += 1
        if resultado["estado"] == "ok":
            resumen["ok"] += 1
            resumen["por_tier"][resultado["tier"]] += 1
        else:
            resumen["errores"] += 1

    return resultados, resumen
