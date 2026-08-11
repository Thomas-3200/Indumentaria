# Para retomar mañana

Dia 1 completo: VPS + Docker + n8n + Postgres (2 bases: n8n y sistema_indumentaria) + schema Drizzle (8 tablas) + backup automatico probado + repo en GitHub.

## Proximo paso: portar logica de agentes
Todo el codigo de referencia de Stepflow-v1 (que ya funciona en produccion para otro cliente) esta copiado en /reference:
- reference/flows/bot_telegram_mt -> logica del bot de Telegram (intake de productos, ventas, aprobacion de contenido) a portear como agente "Agustina" (mensajeria) sobre el nuevo schema Drizzle
- reference/flows/outreach_v1 y reference/flows/prospecting -> motor de prospeccion/outreach
- reference/lib -> clientes de Supabase y n8n (adaptar a Drizzle/Postgres propio en vez de Supabase)
- reference/docs -> arquitectura completa documentada (Jordan Core, Stepflow Studio, stock control)

## Pendiente de Lucas/Leo
- Token del bot de Telegram (@BotFather)
- Claves de Supabase (si se decide seguir usandolo para algo, o migrar todo a la Postgres propia)

## Server
IP: 187.127.15.158 | n8n: http://187.127.15.158:5678 | repo app: /opt/sistema-indumentaria | repo Stepflow (referencia): /opt/stepflow_v1
