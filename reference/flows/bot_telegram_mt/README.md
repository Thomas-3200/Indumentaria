# Stylo Fino — Telegram Intake

Polling del bot **@indumentariastylofino_bot**.
Baja fotos/videos/datos que mande Lucas y los guarda en `data/clients/stylo_fino/`.
El bot le responde a Lucas en el chat (confirmaciones / ayuda / errores), así él sabe que lo que mandó llegó.

## Scripts

| Script | Para qué |
|---|---|
| `setup_check.py` | Valida `.env`, conectividad con Telegram, directorios. Corré esto antes de arrancar. |
| `fetch_intake.py` | Baja mensajes. Dos modos: one-shot o `--watch`. |

## Requisitos

- Python 3.9+
- `.env` en la raíz del repo con `STYLO_FINO_TG_BOT_TOKEN` cargado.
- Sin dependencias externas — solo `urllib` de la stdlib.

## Setup check (corré esto primero)

```bash
python flows/bot_telegram_mt/setup_check.py
```

Verifica:
- `.env` existe y está en `.gitignore`.
- Token válido contra `getMe` de Telegram.
- Username del bot coincide con `.env`.
- Directorios `data/clients/stylo_fino/{products,inbox}/` existen.
- Estado de `STYLO_FINO_TG_LUCAS_USER_ID` y `STYLO_FINO_TG_APPROVAL_CHAT_ID` (informativo).

Exit 0 si está listo, 1 si falta algo crítico.

## Modo one-shot (corrida puntual)

```bash
python flows/bot_telegram_mt/fetch_intake.py
```

Baja todo lo nuevo desde el último offset y sale. Útil para correr 2-3 veces al día.

## Modo watch (recomendado durante el sprint)

```bash
python flows/bot_telegram_mt/fetch_intake.py --watch
```

Long polling continuo (timeout 25s por request). Lo dejás abierto en una terminal y procesa mensajes en tiempo real (~1s de latencia). `Ctrl+C` para salir.

Es lo que vas a querer correr cuando le digas a Lucas "mandame los productos ahora".

### Sin respuestas (debug)

```bash
python flows/bot_telegram_mt/fetch_intake.py --watch --no-replies
```

Procesa pero no le responde nada a Lucas. Para probar el parser sin "ensuciar" el chat del bot.

## Qué le responde el bot a Lucas

| Lucas manda | Bot responde |
|---|---|
| `/start` o `/ayuda` | Mensaje de bienvenida con el formato completo de `PRODUCTO` y comandos de stock. |
| Bloque `PRODUCTO` válido | "Producto cargado ✅" con código, precio, stock total, talles. |
| `Vendido CODE talle X cantidad N` | "Anotado: venta de CODE talle X xN." |
| `Sin stock CODE` | "Marcado SIN STOCK." |
| `Stock CODE talle X N` | "Stock seteado." |
| `Agregar stock CODE talle X N` | "Stock sumado." |
| Foto sin código previo | "Recibí la foto pero no mandaste el bloque PRODUCTO todavía." |
| Texto que no entiende | "No entendí, mandá /ayuda." |

## Primera corrida (Día 0)

1. ✅ Token cargado en `.env`.
2. ✅ Bot configurado en Telegram (comandos `/start`/`/ayuda` + descripción).
3. ⏳ Lucas le manda `/start` al bot por primera vez.
4. ⏳ Vos corrés `python flows/bot_telegram_mt/fetch_intake.py --watch`.
5. ⏳ Cuando Lucas escriba, el script imprime su `user_id`. Copialo a `.env` → `STYLO_FINO_TG_LUCAS_USER_ID=`.
6. ⏳ Reiniciá el watch. Ahora solo acepta mensajes de Lucas.

## Archivos generados

```
data/clients/stylo_fino/
├── .last_update_id          ← offset de Telegram (se incrementa solo)
├── intake_log.jsonl         ← log append-only (1 línea por mensaje)
├── products/
│   └── <code>/
│       ├── meta.json
│       └── msg<id>_*.jpg
└── inbox/
    └── <YYYY-MM-DD>/
        └── msg<id>.{json,jpg,mp4}   ← cosas que no se pudieron clasificar
```

## Mapeo a Fase 2 (n8n)

Este script corresponde al workflow `01_dtc_product_intake_whatsapp` del módulo DTC del spec original (pero usando Telegram en lugar de WhatsApp Cloud).

| Acá (Fase 1) | Allá (Fase 2) |
|---|---|
| `fetch_intake.py --watch` | Telegram Trigger nativo en n8n |
| Parser Python | Code node `parse_product_message.js` |
| `meta.json` por producto | Tabla Supabase `products` |
| Fotos en disco | Bucket Supabase Storage |
| `intake_log.jsonl` | Tabla `intake_events` |
| Respuestas hardcodeadas | Prompt `whatsapp_reply_agent.md` + LLM |
