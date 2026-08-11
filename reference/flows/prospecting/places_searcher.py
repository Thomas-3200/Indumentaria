"""
places_searcher.py — Busca negocios usando Google Places API.

Dado un nicho y ciudad, devuelve una lista de negocios con nombre,
dirección y sitio web oficial.
"""

import os
import time
import requests
from pathlib import Path

try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).parent.parent.parent / ".env")
except ImportError:
    pass

API_KEY = os.getenv("GOOGLE_PLACES_API_KEY", "")

BASE_URL_SEARCH  = "https://maps.googleapis.com/maps/api/place/textsearch/json"
BASE_URL_DETAILS = "https://maps.googleapis.com/maps/api/place/details/json"

NICHO_QUERY = {
    "inmobiliaria":      "inmobiliaria",
    "salud":             "clinica medica centro de salud",
    "servicios_locales": "empresa de servicios",
    "educacion":         "academia instituto educativo",
    "gastronomia":       "restaurante bar",
    "automotriz":        "concesionaria automotriz",
    "otro":              "empresa",
}


def buscar_negocios(nicho: str, ciudad: str, cantidad: int = 20) -> list[dict]:
    """
    Busca negocios en Google Places y devuelve lista con nombre + website.

    Returns:
        Lista de dicts: {nombre, direccion, place_id, website}
    """
    if not API_KEY:
        raise ValueError("GOOGLE_PLACES_API_KEY no configurada en .env")

    query_nicho = NICHO_QUERY.get(nicho, nicho)
    query       = f"{query_nicho} en {ciudad}"

    print(f"  Buscando: '{query}'...")

    negocios   = []
    next_token = None

    while len(negocios) < cantidad:
        params = {"query": query, "language": "es", "key": API_KEY}
        if next_token:
            params["pagetoken"] = next_token
            time.sleep(2)  # Google requiere delay entre paginaciones

        resp = requests.get(BASE_URL_SEARCH, params=params, timeout=10)
        resp.raise_for_status()
        data = resp.json()

        if data.get("status") not in ("OK", "ZERO_RESULTS"):
            raise RuntimeError(f"Google Places API error: {data.get('status')} — {data.get('error_message', '')}")

        for lugar in data.get("results", []):
            if len(negocios) >= cantidad:
                break

            detalles = _obtener_detalles(lugar["place_id"])
            website  = detalles.get("website", "")

            negocios.append({
                "nombre":    lugar.get("name", ""),
                "direccion": lugar.get("formatted_address", ""),
                "place_id":  lugar["place_id"],
                "website":   website,
            })

        next_token = data.get("next_page_token")
        if not next_token:
            break

    return negocios


def _obtener_detalles(place_id: str) -> dict:
    """Obtiene website de un negocio via Place Details API."""
    params = {
        "place_id": place_id,
        "fields":   "website,formatted_phone_number",
        "key":      API_KEY,
    }
    try:
        resp = requests.get(BASE_URL_DETAILS, params=params, timeout=8)
        resp.raise_for_status()
        return resp.json().get("result", {})
    except Exception:
        return {}
