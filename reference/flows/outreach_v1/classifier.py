"""
classifier.py — Detecta el nicho de un lead.

Orden de detección:
1. industria_declarada (si viene en el lead)
2. palabras clave en nombre de empresa
3. palabras clave en notas
4. fallback → "generico"
"""

KEYWORDS = {
    "inmobiliaria": [
        "inmobiliaria", "propiedades", "bienes raices", "bienes raíces",
        "inmuebles", "real estate", "realty"
    ],
    "salud": [
        "clinica", "clínica", "salud", "medico", "médico", "hospital",
        "farmacia", "bienestar", "wellness", "nutricion", "nutrición",
        "odontologia", "odontología", "fisioterapia"
    ],
    "b2b": [
        "tech", "software", "soluciones", "consulting", "consultora",
        "servicios empresariales", "b2b", "srl", "sa", "technologies",
        "sistemas", "desarrollo", "agencia"
    ],
    "educacion": [
        "academia", "colegio", "escuela", "instituto", "universidad",
        "educacion", "educación", "capacitacion", "capacitación",
        "cursos", "formacion", "formación", "training"
    ],
    "gastronomia": [
        "restaurant", "restaurante", "resto", "bar", "cafeteria", "cafetería",
        "panaderia", "panadería", "catering", "comida", "gastronomia",
        "gastronómia", "pizza", "sushi", "grill"
    ],
    "retail": [
        "tienda", "local", "shop", "store", "boutique", "comercio",
        "venta", "retail", "moda", "ropa", "indumentaria", "ferreteria",
        "ferretería", "supermercado"
    ]
}

INDUSTRIA_MAP = {
    "inmobiliaria": "inmobiliaria",
    "salud": "salud",
    "b2b": "b2b",
    "tech": "b2b",
    "educacion": "educacion",
    "educación": "educacion",
    "gastronomia": "gastronomia",
    "gastronómia": "gastronomia",
    "retail": "retail",
    "comercio": "retail"
}


def _buscar_en_texto(texto: str) -> str | None:
    texto_lower = texto.lower()
    for nicho, palabras in KEYWORDS.items():
        for palabra in palabras:
            if palabra in texto_lower:
                return nicho
    return None


def clasificar(lead: dict) -> str:
    # 1. Industria declarada explícitamente
    industria = lead.get("industria_declarada", "").strip().lower()
    if industria and industria in INDUSTRIA_MAP:
        return INDUSTRIA_MAP[industria]

    # 2. Nombre de empresa
    empresa = lead.get("empresa", "")
    nicho = _buscar_en_texto(empresa)
    if nicho:
        return nicho

    # 3. Notas
    notas = lead.get("notas", "")
    nicho = _buscar_en_texto(notas)
    if nicho:
        return nicho

    # 4. Fallback
    return "generico"
