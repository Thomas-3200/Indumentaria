"""
email_finder.py — Extrae email de contacto desde el sitio web de un negocio.

Busca en homepage → /contacto → /contact → /nosotros → /about
Prioriza emails institucionales (info@, contacto@, ventas@)
"""

import re
import requests
from urllib.parse import urljoin, urlparse

TIMEOUT = 8

EMAIL_REGEX = re.compile(
    r"[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}"
)

# Emails a ignorar (falsos positivos comunes)
EMAILS_EXCLUIDOS = {
    "example.com", "domain.com", "correo.com", "email.com",
    "tumail.com", "usuario.com", "sentry.io", "wixpress.com",
}

# Rutas a probar si no hay email en homepage
RUTAS_CONTACTO = ["/contacto", "/contact", "/nosotros", "/about", "/quienes-somos"]

# Prefijos que indican email institucional (mayor prioridad)
PREFIJOS_PRIORITARIOS = ["info", "contacto", "ventas", "consultas", "hola", "admin"]


def encontrar_email(website: str) -> str | None:
    """
    Visita el sitio web y devuelve el mejor email de contacto encontrado.
    Retorna None si no encuentra nada.
    """
    if not website:
        return None

    if not website.startswith("http"):
        website = "https://" + website

    # Intentar homepage primero
    email = _extraer_email_de_url(website)
    if email:
        return email

    # Probar rutas de contacto
    base = _base_url(website)
    for ruta in RUTAS_CONTACTO:
        email = _extraer_email_de_url(urljoin(base, ruta))
        if email:
            return email

    return None


def _extraer_email_de_url(url: str) -> str | None:
    """Descarga la página y extrae el mejor email."""
    try:
        resp = requests.get(
            url,
            timeout=TIMEOUT,
            headers={"User-Agent": "Mozilla/5.0"},
            allow_redirects=True,
        )
        if resp.status_code != 200:
            return None
        return _mejor_email(resp.text)
    except Exception:
        return None


def _mejor_email(html: str) -> str | None:
    """Elige el mejor email del HTML según prioridad."""
    encontrados = EMAIL_REGEX.findall(html)

    validos = [
        e.lower() for e in encontrados
        if _es_valido(e)
    ]

    if not validos:
        return None

    # Priorizar emails institucionales
    for prefijo in PREFIJOS_PRIORITARIOS:
        for email in validos:
            if email.startswith(prefijo + "@"):
                return email

    return validos[0]


def _es_valido(email: str) -> bool:
    """Descarta falsos positivos."""
    email = email.lower()
    dominio = email.split("@")[-1] if "@" in email else ""

    if dominio in EMAILS_EXCLUIDOS:
        return False
    if any(ext in email for ext in [".png", ".jpg", ".jpeg", ".gif", ".svg", ".webp"]):
        return False
    if len(email) > 80:
        return False

    return True


def _base_url(url: str) -> str:
    parsed = urlparse(url)
    return f"{parsed.scheme}://{parsed.netloc}"
