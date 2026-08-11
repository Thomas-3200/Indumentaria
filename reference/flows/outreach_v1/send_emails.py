"""
send_emails.py — Orquestador de envío de emails de outreach.

Uso:
    python flows/outreach_v1/send_emails.py

Qué hace:
    1. Lee leads procesados desde data/output/processed_leads.json
    2. Para cada lead con estado "ok" y email disponible:
       - Selecciona el template del nicho
       - Reemplaza variables ({{nombre}}, {{empresa}}, {{ciudad}})
       - Envía el email via Gmail
    3. Registra resultados en logs/email_log.json

Requisitos:
    - .env configurado con GMAIL_USER y GMAIL_APP_PASSWORD
    - Haber ejecutado run.py previamente para generar processed_leads.json
    - pip install python-dotenv
"""

import json
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).parent.parent.parent

from flows.outreach_v1.email_sender import enviar_email

PROCESSED_PATH  = ROOT / "data" / "output" / "processed_leads.json"
TEMPLATES_PATH  = ROOT / "templates" / "messages.json"
EMAIL_LOG_PATH  = ROOT / "logs" / "email_log.json"


# ── HELPERS ───────────────────────────────────────────────────────────────────

def cargar_json(path: Path) -> any:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def guardar_log(entradas: list) -> None:
    try:
        log_existente = cargar_json(EMAIL_LOG_PATH)
    except (FileNotFoundError, json.JSONDecodeError):
        log_existente = []

    log_existente.extend(entradas)

    EMAIL_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(EMAIL_LOG_PATH, "w", encoding="utf-8") as f:
        json.dump(log_existente, f, ensure_ascii=False, indent=2)


def aplicar_variables(texto: str, lead: dict) -> str:
    """Reemplaza {{variable}} con datos reales del lead."""
    datos = lead.get("datos_originales", {})
    reemplazos = {
        "{{nombre}}":  datos.get("nombre", ""),
        "{{empresa}}": datos.get("empresa", ""),
        "{{ciudad}}":  datos.get("ciudad", ""),
        "{{zona}}":    datos.get("ciudad", datos.get("zona", "tu zona")),
    }
    for placeholder, valor in reemplazos.items():
        texto = texto.replace(placeholder, valor)
    return texto


# ── MAIN ──────────────────────────────────────────────────────────────────────

def main():
    print("\n" + "─" * 52)
    print("  STEPFLOW — Envío de emails de outreach")
    print("─" * 52)

    # Cargar leads procesados
    if not PROCESSED_PATH.exists():
        print("ERROR: No existe data/output/processed_leads.json")
        print("Ejecutá primero: python flows/outreach_v1/run.py")
        return

    leads = cargar_json(PROCESSED_PATH)
    templates = cargar_json(TEMPLATES_PATH)

    enviados = 0
    errores  = 0
    saltados = 0
    log_entries = []

    for lead in leads:
        nombre  = lead.get("datos_originales", {}).get("nombre", "?")
        email   = lead.get("datos_originales", {}).get("email", "")
        nicho   = lead.get("nicho", "otro")
        estado  = lead.get("estado", "")

        # Saltar leads con error en el pipeline
        if estado != "ok":
            saltados += 1
            continue

        # Saltar si no tiene email
        if not email or "@" not in email:
            print(f"  [–] {nombre:<22} sin email — saltado")
            saltados += 1
            continue

        # Obtener template del nicho
        template_nicho = templates.get(nicho, templates.get("otro", {}))
        template       = template_nicho.get("primer_contacto", {})
        asunto_raw     = template.get("asunto", "StepFlow — para {{empresa}}")
        cuerpo_raw     = template.get("texto", "")

        asunto = aplicar_variables(asunto_raw, lead)
        cuerpo = aplicar_variables(cuerpo_raw, lead)

        # Enviar
        resultado = enviar_email(email, asunto, cuerpo)

        log_entries.append({
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "nombre":    nombre,
            "email":     email,
            "nicho":     nicho,
            "asunto":    asunto,
            "resultado": resultado
        })

        if resultado["ok"]:
            print(f"  [✓] {nombre:<22} → {email}")
            enviados += 1
        else:
            print(f"  [✗] {nombre:<22} ERROR: {resultado['error']}")
            errores += 1

    # Guardar log
    if log_entries:
        guardar_log(log_entries)

    # Resumen
    print("─" * 52)
    print(f"  Enviados : {enviados}")
    print(f"  Errores  : {errores}")
    print(f"  Saltados : {saltados}")
    print(f"  Log      → logs/email_log.json")
    print("─" * 52 + "\n")


if __name__ == "__main__":
    main()
