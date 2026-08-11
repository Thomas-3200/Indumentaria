# Bot Telegram — Action Contract (Multi-Tenant)

> **Contrato inmutable** que TODOS los clientes de Stepflow comparten.
> Cuando onboardeás un cliente nuevo, NO se cambia código — solo se crea su `client_config.json` + bot de Telegram + entradas en `.env`.

---

## 1. Comandos estándar

Todos los bots del repo aceptan los mismos comandos:

| Comando | Quién lo usa | Acción |
|---|---|---|
| `/start`, `/ayuda`, `/help` | Cualquiera | Mensaje de bienvenida |
| `/venta` | Operator (Leo) | Inicia state machine 9 pasos para registrar venta |
| `/venta <nombre producto>` | Operator | Idem pero salta paso 1 |
| `/reply <mensaje cliente>` | Lead / Operator | Devuelve sugerencia GPT para responder DM/WA |
| `LISTO`, `ya`, `done`, `fin` | Lead | Cierra sesión de intake de fotos, dispara sync a Supabase |
| `/cancelar` | Operator | Aborta `/venta` en curso |

## 2. Callback data (botones)

| Prefijo | Formato | Acción del bot |
|---|---|---|
| `publicado:<ref>` | `publicado:SF-D01-P-PROD-IG` | Marca content_item.status=published, edita mensaje con ✅ verde |
| `skip:<ref>` | `skip:SF-D01-P-PROD-FB` | Marca content_item.status=skipped, edita mensaje con ⏭ |
| `regen:<ref>` | `regen:SF-D02-R-PROD` | Re-genera caption con GPT (futuro) |
| `venta_o:<value>` | `venta_o:INSTAGRAM_DM` | `/venta` step sale_origin |
| `venta_s:<value>` | `venta_s:LUCAS_STOCK` | `/venta` step stock_origin |
| `venta_m:<value>` | `venta_m:PROFIT_SPLIT_50_50` | `/venta` step settlement_model |
| `venta_c:YES\|NO` | `venta_c:YES` | `/venta` confirmar/cancelar |

Cualquier callback con prefijo desconocido devuelve "Acción no reconocida". Esto previene clicks accidentales o callbacks de versiones viejas.

## 3. Roles

| Rol | Responsabilidad | Stylo Fino | Cliente X |
|---|---|---|---|
| `LEAD` | Dueño del cliente, manda fotos de productos | Lucas | … |
| `OPERATOR` | "API humana" de Stepflow, publica y registra ventas | Leo | … |

El bot autoriza solo a estos 2 user IDs (de `client_config.json` + `.env`). Cualquier otro user_id es ignorado con log.

## 4. Estados de `sales` (Supabase)

| Status | Significado |
|---|---|
| `pending` | Recién creada, esperando liquidación |
| `reviewed` | Ya incluida en un settlement draft |
| `approved` | Settlement aprobado por los partners |
| `paid` | Pago hecho |
| `disputed` | Requiere revisión humana (margen <0, origin sospechoso, etc.) |

## 5. Estados de `content_items`

| Status | Significado |
|---|---|
| `scheduled` | Programado, no enviado a operator todavía |
| `sent_to_operator` | Bot ya le mandó el kit al operator |
| `published` | Operator tocó "✅ Listo" |
| `skipped` | Operator tocó "⏭ Saltar" |
| `needs_review` | Producto sin stock, error de caption, etc. |

---

## Cómo onboardear un cliente nuevo (multi-tenant)

### 1. Crear el bot en Telegram (5 min)
1. Hablar con [@BotFather](https://t.me/BotFather), crear bot, guardar **token**.
2. Setear nombre/foto del bot con identidad del cliente.

### 2. Crear el UUID del cliente en Supabase (2 min)
```sql
INSERT INTO clients (name, slug) VALUES ('Cliente Nuevo', 'cliente_nuevo')
RETURNING id;
-- copiar el UUID devuelto
```

### 3. Crear el config (5 min)
Copiar `clients/_template_client_config.json` → `clients/cliente_nuevo/client_config.json`.
Editar todos los campos marcados como ejemplo.

### 4. Agregar al `.env` (1 min)
```env
CLIENTE_NUEVO_TG_BOT_TOKEN=...
CLIENTE_NUEVO_TG_LEAD_USER_ID=...
CLIENTE_NUEVO_TG_OPERATOR_USER_ID=...
CLIENTE_NUEVO_WA_LINK=...  # opcional, si va en JSON queda allá
```

### 5. Validar el setup
```bash
python flows/bot_telegram_mt/client_config.py cliente_nuevo
```
Debe imprimir el config completo sin "MISSING" en TG bot token, lead, operator, supabase.

### 6. Arrancar
```bash
# Bot watch
python flows/bot_telegram_mt/fetch_intake.py --client cliente_nuevo --watch

# Agenda diaria
python flows/bot_telegram_mt/send_daily_agenda.py --client cliente_nuevo --date 2026-MM-DD

# Liquidación semanal
python flows/bot_telegram_mt/generate_weekly_settlement.py --client cliente_nuevo
```

### 7. (Pendiente) Workflow n8n genérico
El workflow `WF_StyloFino_Daily_Agenda_Leo.json` se va a generalizar a `WF_MT_Daily_Agenda.json` con parámetro `client_slug` como input. Mientras tanto, duplicar el JSON por cliente.

---

## Lo que NO está parametrizado todavía

| Archivo | Estado | Plan |
|---|---|---|
| `client_config.py` (loader) | ✅ multi-tenant | Listo |
| `client_config.json` (datos) | ✅ multi-tenant | Listo (Stylo Fino + template) |
| `venta_flow.py` | ✅ multi-tenant via TG["client_cfg"] | Listo |
| `send_daily_agenda.py` | ✅ multi-tenant via `--client` | Listo |
| `generate_weekly_settlement.py` | ✅ multi-tenant via `--client` | Listo |
| `fetch_intake.py` (bot principal) | ⚠ usa env vars `STYLO_FINO_*` hardcoded | Refactor pendiente (1300 líneas — se hace próximo turno con `--client` flag) |
| Workflow n8n | ⚠ tiene UUID + env vars Stylo Fino | Generalizar próximo turno |
| Folder `flows/bot_telegram_mt/` | ⚠ nombrado por cliente | Renombrar a `flows/bot_telegram_mt/` cuando todo esté MT |

**Próximo turno bloquea esto** — el refactor de `fetch_intake.py` requiere su propio chunk de testing porque es la pieza más grande y crítica del sistema.
