# StepFlow Studio — Arquitectura de Integración con el Ecosistema STEPFlow

> **Propósito:** Este documento muestra cómo StepFlow Studio encaja como módulo especializado dentro del ecosistema STEPFlow. Studio es invocado por Jordan Core — no es un módulo paralelo ni independiente.

---

## Visión del ecosistema completo

```
┌─────────────────────────────────────────────────────────────────────┐
│                        STEPFLOW ECOSYSTEM                           │
│                                                                     │
│  ┌─────────────────────────────────────────────────────────────┐   │
│  │                      JORDAN CORE                            │   │
│  │   (JORDAN_CORE.md — cerebro central del sistema)           │   │
│  │                                                             │   │
│  │   • Gestión de leads y pipeline de ventas                  │   │
│  │   • Atención al cliente 24/7 por WhatsApp                  │   │
│  │   • Calificación y seguimiento de prospectos               │   │
│  │   • Detección de necesidades de contenido                  │   │
│  └──────────────┬────────────────┬───────────────────────────┘   │
│                 │                │                                  │
│                 │ invoca         │ consume outputs                  │
│                 │                │                                  │
│  ┌──────────────▼──────┐  ┌─────▼──────────────────────────┐     │
│  │  STEPFLOW STUDIO    │  │         AGUSTINA               │     │
│  │  (este módulo)      │  │  (agente de ventas por email)  │     │
│  │                     │  │                                │     │
│  │  Producción         │  │  • Responde emails de         │     │
│  │  audiovisual        │  │    prospectos                 │     │
│  │  digital con IA     │  │  • Puede usar piezas          │     │
│  │                     │  │    generadas por Studio       │     │
│  │  ← modo A: new      │  │    como adjuntos o            │     │
│  │    production       │  │    material de cierre         │     │
│  │  ← modo B: existing │  │                                │     │
│  │    assets optim.    │  │  NO coordina Studio           │     │
│  └─────────────────────┘  └────────────────────────────────┘     │
│                                                                     │
└─────────────────────────────────────────────────────────────────────┘
```

---

## Arquitectura interna de StepFlow Studio

```
Jordan Core
    │
    │  studio_input (JSON)
    ▼
Jordan Studio Orchestrator
    │
    │  clasifica input_type
    │
    ├──── [modo A: new_production] ────────────────────────────────►
    │           │
    │      Marketing Strategist
    │           │
    │      Creative Director
    │      (genera también publishing_copy_lite en MVP)
    │           │
    │      AI Production Supervisor
    │      (decide herramientas, detecta necesidad de grabación)
    │           │
    │      [pausa manual si human_assets_needed: true]
    │           │
    │      Format Adapter
    │           │
    │      Publishing Copywriter Lite
    │           │
    │      Advertising QA
    │
    └──── [modo B: existing_assets_optimization] ──────────────────►
                │
           AI Asset Enhancement Supervisor
           (audita activos, clasifica A/B/C/D)
                │
           [pausa si human_review_required: true]
                │
           Format Adapter
                │
           Publishing Copywriter Lite
                │
           Advertising QA
                │
    ◄───────────────────────────────────────────────────────────────
    production_plan / asset_optimization_plan
    devuelto a Jordan Core
```

---

## Flujo de datos

### Entrada (Jordan Core → Studio)

```json
// Jordan Core detecta necesidad de producción audiovisual y envía:
{
  "client_id": "string",
  "input_type": "new_production | existing_assets_optimization",
  "product_or_service": "string",
  "objective": "string",
  "channels": ["array"],
  "budget_level": "free | low_cost | mid_cost | premium | enterprise",
  "assets": [...]   // solo para modo B
}
```

### Salida (Studio → Jordan Core)

```json
// Studio devuelve a Jordan Core:
{
  "selected_flow": "string",
  "production_plan": {...},           // modo A
  "asset_optimization_plan": {...},   // modo B
  "recommended_tools": {...},
  "formats_to_generate": [...],
  "approval_required": true,
  "next_step": "string"
}
```

---

## Separación de responsabilidades

| Módulo | Responsabilidad | Lo que NO hace |
|--------|----------------|---------------|
| **Jordan Core** | Gestión de ventas, leads, WhatsApp, pipeline CRM | No produce contenido audiovisual |
| **Jordan Studio Orchestrator** | Coordinación del flujo de producción audiovisual | No gestiona leads ni pipeline de ventas |
| **Agustina** | Ventas por email, respuesta a prospectos | No invoca ni coordina Studio |
| **Studio (agentes)** | Producción, mejora, QA de piezas audiovisuales | No tocan JORDAN_CORE.md ni workflows existentes |

---

## Integraciones planificadas (no implementadas en V1)

### Fase 2 — Supabase

```
Studio ──► supabase.studio_projects (estado del proyecto)
       ──► supabase.studio_assets (activos recibidos)
       ──► supabase.studio_qa_results (resultados de QA)
       ──► supabase.studio_generated_outputs (piezas finales)
```

### Fase 3 — n8n

```
n8n webhook ──► Jordan Studio Orchestrator (invocación automática)
            ──► approval_flow node (esperando aprobación del cliente)
            ──► WhatsApp callback ──► estado: approved | rejected
            ──► calendar editorial node ──► publicación automática
```

### Fase 3 — WhatsApp / Telegram (aprobaciones del cliente)

```
Staff de Stepflow
    │
    │  envía preview por WhatsApp/Telegram al cliente
    │
    ▼
Cliente responde (SÍ / NO / cambios)
    │
    ▼
Staff actualiza estado en sistema
    │  estado: approved | rejected | needs_rework
    ▼
Flujo continúa automáticamente
```

### Fase 5 — Client Self-Service (futuro)

```
Cliente (por WhatsApp o formulario)
    │
    │  envía brief directamente
    ▼
Jordan Core detecta intent de producción
    │
    │  invoca Studio automáticamente
    ▼
Studio procesa y devuelve preview
    │
    │  client_safe_instruction vía WhatsApp al cliente
    ▼
Cliente aprueba/rechaza directamente
    │
    ▼
Publicación automática si aprobado
```

---

## Separación de datos

Studio opera dentro del modelo de separación de datos existente de STEPFlow:

- Cada registro en Supabase lleva `client_id` para separación multi-tenant
- Los assets de clientes se almacenan en rutas aisladas por cliente
- Los proyectos de Studio no comparten datos entre clientes
- Las skills internas (nanobanana, reel-generator, etc.) no almacenan datos del cliente

---

## Convenciones de integración

| Convención | Detalle |
|-----------|---------|
| ID de proyectos | `studio_{client_id}_{timestamp}` |
| ID de activos | `asset_{client_id}_{sequence}` |
| Estados | inglés snake_case (coherente con schemas) |
| Logs | en `logs/studio/` (cuando se implemente) |
| Configuración | en `clients/{client_id}/studio_config.json` (futura) |

---

## Diagrama de aditividad

```
Ecosistema STEPFlow ANTES de Studio:

Jordan Core ──► WhatsApp ──► leads ──► ventas
Jordan Core ──► Agustina ──► email ──► seguimiento

Ecosistema STEPFlow DESPUÉS de agregar Studio:

Jordan Core ──► WhatsApp ──► leads ──► ventas
Jordan Core ──► Agustina ──► email ──► seguimiento
Jordan Core ──► Studio ──► contenido audiovisual ──► más conversiones
                   │
                   └──► Agustina puede usar outputs de Studio
```

Studio agrega valor al ecosistema sin modificar ningún flujo existente.

---

## Documentación relacionada

| Documento | Contenido |
|-----------|-----------|
| `modules/stepflow_studio/README.md` | Overview del módulo |
| `modules/stepflow_studio/PRE_IMPLEMENTATION_PLAN.md` | Plan técnico completo |
| `modules/stepflow_studio/agents/jordan_studio.md` | Punto de entrada del módulo |
| `modules/stepflow_studio/flows/` | Flujos de operación detallados |
| `modules/stepflow_studio/matrices/` | Matrices de decisión |
| `JORDAN_CORE.md` | Cerebro central del sistema (no modificar) |
| `docs/stepflow_production_v1.md` | Arquitectura de producción existente |
