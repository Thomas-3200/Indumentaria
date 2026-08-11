"""
message_generator.py — Genera el primer mensaje personalizado para un lead.

Proceso:
1. Carga templates desde templates/messages.json
2. Selecciona el template según el nicho detectado
3. Reemplaza variables dinámicas con datos del lead
4. Si falta una variable, usa el valor genérico definido en FALLBACKS
"""

import json
import re
from pathlib import Path

TEMPLATES_PATH = Path(__file__).parent.parent.parent / "templates" / "messages.json"

# Valores de reemplazo cuando el dato no está disponible en el lead
FALLBACKS = {
    "nombre":   "te",
    "empresa":  "tu empresa",
    "zona":     "tu zona",
    "ciudad":   "tu ciudad",
    "cargo":    "tu equipo"
}


def _cargar_templates() -> dict:
    with open(TEMPLATES_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def _reemplazar_variables(texto: str, lead: dict) -> str:
    """Reemplaza {{variable}} con el dato del lead o el fallback correspondiente."""
    variables = re.findall(r"\{\{(\w+)\}\}", texto)
    for var in variables:
        valor = lead.get(var, "").strip()
        if not valor:
            valor = FALLBACKS.get(var, var)
        texto = texto.replace(f"{{{{{var}}}}}", valor)
    return texto


def generar_mensaje(lead: dict, nicho: str) -> dict:
    templates = _cargar_templates()

    # Usar template del nicho o fallback a "otro"
    template_nicho = templates.get(nicho) or templates.get("otro")
    template = template_nicho["primer_contacto"]

    mensaje = _reemplazar_variables(template["texto"], lead)

    return {
        "texto": mensaje,
        "nicho_usado": nicho,
        "template_version": template["version"]
    }
