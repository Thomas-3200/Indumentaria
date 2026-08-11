"""
prioritizer.py — Asigna score (0-100) y Tier (A/B/C) a cada lead.

Criterios basados en JORDAN_CORE.md:
- Canal de origen
- Completitud de datos
- Nicho detectado
- Señal de interés en notas
"""

# Puntajes por canal de origen
PUNTAJE_CANAL = {
    "inbound_formulario": 35,   # Mostró interés activo
    "prospecting": 20,          # Contacto proactivo con perfil definido
    "lista_propia": 10          # Base propia, sin señal activa
}

# Nichos base del sistema STEPFlow V1
PUNTAJE_NICHO = {
    "inmobiliaria":      15,
    "salud":             15,
    "gastronomia":       15,
    "servicios_locales": 12,
    "educacion":         12,
    "automotriz":        12,
    "otro":               0
}

# Palabras que indican señal de interés en las notas
KEYWORDS_INTERES = [
    "interesado", "consulto", "consulté", "quiere", "necesita",
    "buscando", "problema", "pierde", "pierden", "demora", "urgente"
]


def _puntaje_datos_completos(lead: dict) -> int:
    """Hasta 20 puntos por completitud de datos."""
    campos = ["nombre", "empresa", "telefono", "email", "ciudad", "cargo"]
    completos = sum(1 for c in campos if lead.get(c, "").strip())
    return round((completos / len(campos)) * 20)


def _puntaje_señal_notas(lead: dict) -> int:
    """Hasta 15 puntos si las notas contienen señales de interés."""
    notas = lead.get("notas", "").lower()
    for palabra in KEYWORDS_INTERES:
        if palabra in notas:
            return 15
    return 0


def _asignar_tier(score: int) -> str:
    if score >= 60:
        return "A"
    elif score >= 35:
        return "B"
    else:
        return "C"


def priorizar(lead: dict, nicho: str) -> dict:
    canal = lead.get("canal_origen", "lista_propia")

    score_canal = PUNTAJE_CANAL.get(canal, 10)
    score_nicho = PUNTAJE_NICHO.get(nicho, 0)
    score_datos = _puntaje_datos_completos(lead)
    score_notas = _puntaje_señal_notas(lead)

    score_total = min(score_canal + score_nicho + score_datos + score_notas, 100)
    tier = _asignar_tier(score_total)

    return {
        "score": score_total,
        "tier": tier,
        "detalle_score": {
            "canal": score_canal,
            "nicho": score_nicho,
            "datos_completos": score_datos,
            "señal_notas": score_notas
        }
    }
