"""
prospect_builder.py — Construye registros de prospectos desde datos de Google Places.

Genera entradas compatibles con data/input/leads.json
"""

from datetime import date


def construir_lead(negocio: dict, email: str | None, nicho: str, ciudad: str) -> dict:
    """
    Construye un registro de lead desde los datos de Google Places.

    Args:
        negocio: dict con nombre, direccion, website, place_id
        email:   email encontrado (o None)
        nicho:   clasificación del negocio
        ciudad:  ciudad de búsqueda

    Returns:
        dict compatible con data/input/leads.json
    """
    return {
        "nombre":                "",           # se completa manualmente después
        "empresa":               negocio.get("nombre", ""),
        "email":                 email or "",
        "ciudad":                ciudad,
        "industria_declarada":   nicho,
        "canal_origen":          "prospecting",
        "web":                   negocio.get("website", ""),
        "notas":                 f"Encontrado via Google Places. Dirección: {negocio.get('direccion', '')}",
        "fuente":                "google_places",
        "fecha_captura":         date.today().isoformat(),
        "place_id":              negocio.get("place_id", ""),
    }


def filtrar_duplicados(leads_nuevos: list[dict], leads_existentes: list[dict]) -> list[dict]:
    """
    Evita agregar prospectos que ya están en la base.
    Compara por nombre de empresa y email.
    """
    empresas_existentes = {
        l.get("empresa", "").lower().strip()
        for l in leads_existentes
        if l.get("empresa")
    }
    emails_existentes = {
        l.get("email", "").lower().strip()
        for l in leads_existentes
        if l.get("email")
    }

    nuevos = []
    for lead in leads_nuevos:
        empresa = lead.get("empresa", "").lower().strip()
        email   = lead.get("email", "").lower().strip()

        if empresa in empresas_existentes:
            continue
        if email and email in emails_existentes:
            continue

        nuevos.append(lead)

    return nuevos
