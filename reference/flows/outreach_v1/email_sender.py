"""
email_sender.py — Envío de emails de outreach via Gmail SMTP.

Requisitos:
    pip install python-dotenv

Uso:
    Importar y llamar a enviar_email() desde send_emails.py
    O ejecutar directamente para test: python flows/outreach_v1/email_sender.py
"""

import smtplib
import os
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from pathlib import Path

# Cargar .env si existe
try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).parent.parent.parent / ".env")
except ImportError:
    pass  # Si no está dotenv, lee directo de variables de entorno del sistema

GMAIL_USER         = os.getenv("GMAIL_USER", "")
GMAIL_APP_PASSWORD = os.getenv("GMAIL_APP_PASSWORD", "")


def enviar_email(destinatario_email: str, asunto: str, cuerpo: str) -> dict:
    """
    Envía un email via Gmail SMTP.

    Returns:
        {"ok": True} o {"ok": False, "error": "..."}
    """
    if not GMAIL_USER or not GMAIL_APP_PASSWORD:
        return {"ok": False, "error": "Credenciales de Gmail no configuradas en .env"}

    if not destinatario_email or "@" not in destinatario_email:
        return {"ok": False, "error": f"Email inválido: {destinatario_email}"}

    try:
        msg = MIMEMultipart()
        msg["From"]    = GMAIL_USER
        msg["To"]      = destinatario_email
        msg["Subject"] = asunto

        msg.attach(MIMEText(cuerpo, "plain", "utf-8"))

        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
            server.login(GMAIL_USER, GMAIL_APP_PASSWORD)
            server.send_message(msg)

        return {"ok": True}

    except smtplib.SMTPAuthenticationError:
        return {"ok": False, "error": "Autenticación fallida — verificá el App Password en .env"}
    except smtplib.SMTPRecipientsRefused:
        return {"ok": False, "error": f"Email rechazado por el servidor: {destinatario_email}"}
    except Exception as e:
        return {"ok": False, "error": str(e)}


# ── TEST DE ENVÍO ──────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print("\nTest de envío de email — StepFlow")
    print("─" * 40)

    if not GMAIL_USER:
        print("ERROR: GMAIL_USER no configurado en .env")
        print("Copiá .env.example como .env y completá los datos.")
    else:
        resultado = enviar_email(
            destinatario_email=GMAIL_USER,  # se manda a vos mismo como test
            asunto="Test StepFlow — email funcionando",
            cuerpo="Si recibís este mensaje, el sistema de envío está funcionando correctamente.\n\n— StepFlow"
        )
        if resultado["ok"]:
            print(f"✓ Email enviado correctamente a {GMAIL_USER}")
        else:
            print(f"✗ Error: {resultado['error']}")
    print("─" * 40 + "\n")
