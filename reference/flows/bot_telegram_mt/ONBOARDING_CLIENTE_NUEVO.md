# Onboarding de un cliente nuevo al bot Telegram

> Replicable. No se toca código. Solo config + .env + arrancar.

## Tiempo total: 15 minutos

---

## 0. Pre-requisitos

- UUID del cliente ya creado en Supabase tabla `clients`
- Cliente acepta que Stepflow opere su Telegram bot
- Definidos los 2 roles: **Lead** (dueño) + **Operator** (operador Stepflow)

---

## 1. Crear el bot en Telegram (5 min)

1. Abrir Telegram → buscar `@BotFather` → `/start`.
2. `/newbot` → nombre + username. Guardar el **token** que devuelve.
3. (Opcional) `/setdescription`, `/setuserpic` con la marca del cliente.

## 2. Capturar los Telegram user_id (3 min)

1. Pedirle al **Lead** que mande `/start` al bot.
2. Pedirle al **Operator** que mande `/start` al bot.
3. Hacer una corrida en blanco del bot sin filtros para ver los IDs:
   ```bash
   python flows/bot_telegram_mt/fetch_intake.py --client <slug>
   ```
   El bot imprime los `from.id` que vio en esa corrida. Anotalos.

## 3. Crear `client_config.json` (2 min)

```bash
cp clients/_template_client_config.json clients/<slug>/client_config.json
```

Editar los campos:
```json
{
  "slug": "<slug_minusculas_con_underscores>",
  "display_name": "Nombre Comercial",
  "vertical": "indumentaria_masculina | comida | etc",
  "client_uuid": "<UUID Supabase>",
  "env_prefix": "<SLUG_EN_MAYUSCULAS>",
  "telegram": {
    "bot_username": "<bot_username>",
    "lead_role_name": "<Nombre Lead>",
    "operator_role_name": "<Nombre Operator>"
  },
  ...
}
```

## 4. Agregar al `.env` (2 min)

```env
# Cliente nuevo: <slug>
<SLUG>_TG_BOT_TOKEN=<token de BotFather>
<SLUG>_TG_LEAD_USER_ID=<id del lead>
<SLUG>_TG_OPERATOR_USER_ID=<id del operator>
<SLUG>_WA_LINK=https://wa.me/549XXXX...  # opcional si va en JSON
<SLUG>_FORM_URL=https://n8n.../webhook/<slug>-tag  # opcional
```

## 5. Validar config (30 seg)

```bash
python flows/bot_telegram_mt/client_config.py <slug>
```

Verificar que NO diga "MISSING" en:
- TG bot token
- TG lead
- TG operator
- Supabase URL

## 6. Arrancar el bot (2 min)

### Modo one-shot (test)
```bash
python flows/bot_telegram_mt/fetch_intake.py --client <slug>
```
El cliente Lead manda `/start` → debe recibir el mensaje de bienvenida con el `<display_name>` del cliente.

### Modo watch (producción)
```bash
python flows/bot_telegram_mt/fetch_intake.py --client <slug> --watch
```

## 7. Scheduling (1 min)

### Agenda diaria
```bash
python flows/bot_telegram_mt/send_daily_agenda.py --client <slug> --date YYYY-MM-DD
```

### Liquidación semanal
```bash
python flows/bot_telegram_mt/generate_weekly_settlement.py --client <slug>
```

Agendar ambos en cron / Task Scheduler / n8n.

---

## Validar con el cliente

1. Cliente Lead: `/start` → debe recibir welcome con su nombre comercial
2. Cliente Operator: `/venta` → debe iniciar el flow 9 pasos
3. Cliente Lead: `/reply Hola querría info` → debe devolver sugerencia GPT
4. Cliente Lead: mandar 1 foto → debe procesarla con Claude Vision
5. Cliente Lead: escribir `LISTO` → debe cerrar sesión + sync a Supabase

Si los 5 pasos OK → cliente está en producción.

---

## Lo que comparten TODOS los clientes (Action Contract inmutable)

Ver `BOT_ACTION_CONTRACT.md` en este mismo directorio.

- Comandos: `/start /ayuda /venta /reply LISTO /cancelar`
- Callback prefixes: `publicado: skip: regen: venta_o: venta_s: venta_m: venta_c:`
- Roles: `LEAD` + `OPERATOR`
- Sales statuses: `pending reviewed approved paid disputed`
- Content statuses: `scheduled sent_to_operator published skipped needs_review`

Esto NO cambia entre clientes. Lo único que cambia es la identidad del cliente (slug, UUID, env vars, display name).
