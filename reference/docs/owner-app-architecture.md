# STEPFlow — Owner App · Arquitectura
## Documento permanente · Versión 1.0

---

## 1. Propósito

`owner_app/` es el panel interno de operación de STEPFlow.

Es la vista que usa el equipo de STEPFlow para monitorear en tiempo real cómo está funcionando el sistema: cuántos prospectos están en pipeline, qué automatizaciones están activas, qué métricas de conversión se están obteniendo y dónde hay cuellos de botella.

No es una herramienta de venta. Es una herramienta de operación.

---

## 2. Distinción crítica con demo_app

| | `demo_app` | `owner_app` |
|---|---|---|
| **Para quién** | Prospecto externo | Equipo interno de STEPFlow |
| **Qué muestra** | Cómo se vería el negocio del prospecto con STEPFlow | Cómo está operando STEPFlow como negocio |
| **Datos** | Pipeline del prospecto (simulado) | Pipeline propio de STEPFlow (real/simulado) |
| **Objetivo** | Generar deseo de compra | Tomar decisiones operativas |
| **Tono visual** | Aspiracional, limpio, azul | Ejecutivo, denso, oscuro |

---

## 3. Usuarios

**Usuario principal:** founder / operador de STEPFlow
- Necesita ver el estado del negocio de un vistazo
- Toma decisiones sobre qué prospectos priorizar
- Monitorea si las automatizaciones están funcionando
- Controla métricas de conversión por semana

**Usuario secundario:** agente comercial de STEPFlow
- Consulta qué prospectos requieren acción manual
- Ve el historial de actividad del sistema
- Identifica cuellos de botella en el pipeline

---

## 4. Métricas que muestra

### KPIs principales (semana actual)
| Métrica | Descripción |
|---|---|
| Prospectos nuevos | Contactos que ingresaron al sistema esta semana |
| Contactados | Primer mensaje enviado |
| Respondieron | Tasa de respuesta general |
| Interesados | Respondieron con señal de interés real |
| Reuniones agendadas | Demos o calls confirmadas |
| Clientes cerrados | Conversiones finales |

### Métricas de automatización
- Estado de cada skill activa (activa / pausada / con alertas)
- Mensajes enviados en las últimas 24h
- Tasa de entrega
- Errores detectados

### Métricas de conversión
- Tasa de respuesta (objetivo: >25%)
- Tasa de conversión a reunión (objetivo: >8%)
- Tasa de cierre (objetivo: >20%)
- Costo estimado por cliente cerrado

---

## 5. Vistas del panel

### Vista 1 — KPI Cards
Cinco tarjetas superiores con los números más importantes de la semana. Incluyen comparación con la semana anterior y tendencia visual.

### Vista 2 — Pipeline comercial de STEPFlow
Kanban con los prospectos propios de STEPFlow en cada etapa:
Nuevo → Contactado → Respondió → Interesado → Reunión → Cerrado

### Vista 3 — Actividad reciente del sistema
Feed de eventos en tiempo real: mensajes enviados, respuestas recibidas, alertas del sistema, prospectos que avanzaron de etapa.

### Vista 4 — Prospecto destacado
Ficha detallada del prospecto con mayor prioridad en el momento. Incluye historial de interacciones y siguiente acción recomendada.

### Vista 5 — Estado de automatizaciones
Panel de control de las skills activas: cuántos mensajes enviaron, su tasa de respuesta, si están dentro de parámetros normales o generaron alertas.

---

## 6. Relación con STEPFlow V1

El `owner_app` consume datos del sistema STEPFlow:
- Los prospectos en el pipeline son los leads procesados por `flows/outreach_v1/`
- Las métricas de automatización reflejan el estado de las skills
- La actividad reciente es el log generado en `logs/outreach_log.json`

En V1, estos datos son simulados en `owner_dashboard.json`.
En V2, el panel se conecta directamente a la base de datos operativa.

---

## 7. Evolución futura

**V1 (actual):** panel estático con datos en JSON local. Funciona sin backend.

**V2:** panel conectado a Supabase. Los datos se actualizan en tiempo real desde el sistema operativo de STEPFlow.

**V3:** panel con alertas automáticas, notificaciones push y capacidad de ejecutar acciones directamente desde la interfaz (pausar una skill, aprobar un cambio de template, escalar un prospecto).

---

## 8. Cómo evoluciona la fuente de datos

```javascript
// V1 — datos embebidos
const DATA = { ... };

// V2 — Supabase
const { data } = await supabase.from('dashboard_view').select('*');

// V3 — WebSocket para actualizaciones en tiempo real
const channel = supabase.channel('pipeline').on('postgres_changes', ...);
```

La estructura HTML y CSS no cambia entre versiones. Solo cambia la fuente de datos.
