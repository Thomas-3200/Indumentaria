# STEPFlow — Arquitectura del Frontend de Demo
## Versión 1.0 · Documento permanente

---

## 1. Propósito del frontend demo

`demo_app/` es una demo visual interactiva diseñada para mostrar a prospectos cómo se vería STEPFlow aplicado a su negocio específico.

No es una aplicación funcional. Es una herramienta de ventas.

Su objetivo es que el prospecto, al verla, sienta que ya tiene el sistema funcionando y quiera dar el siguiente paso.

---

## 2. Objetivo comercial

| Objetivo | Cómo lo logra la demo |
|---|---|
| Generar deseo | Muestra el panel como si el negocio del prospecto ya estuviera organizado |
| Reducir fricción | No requiere registro, instalación ni explicación técnica |
| Personalizar la propuesta | Cada demo se adapta al nombre, rubro y datos del prospecto |
| Acelerar la decisión | El prospecto ve el valor antes de la reunión de cierre |

La demo se envía como link antes o después de una reunión inicial. Reemplaza presentaciones genéricas con algo concreto y personalizado.

---

## 3. Tipos de usuarios

**Usuario principal:** el prospecto que recibe el link.
- No es técnico
- Tiene entre 30 segundos y 3 minutos de atención
- Necesita entender de inmediato qué resuelve STEPFlow en su negocio

**Usuario secundario:** el equipo de STEPFlow que personaliza la demo.
- Modifica solo `demo_company.json`
- No necesita tocar código

---

## 4. Estructura visual

```
┌──────────────────────────────────────────────────────┐
│  HEADER — nombre empresa · rubro · ciudad · STEPFlow │
├──────────────────────────────────────────────────────┤
│  MÉTRICAS — 5 cards: leads · contactados · interés   │
│             · demos · cierres                        │
├──────────────────────────────────────────────────────┤
│  PIPELINE — 6 columnas tipo Kanban con leads         │
├──────────────────────────────────────────────────────┤
│  ACTIVIDAD RECIENTE       │  FICHA DE LEAD           │
│  (feed de eventos)        │  (tarjeta detallada)     │
├──────────────────────────────────────────────────────┤
│  CÓMO TRABAJARÍA STEPFLOW EN TU NEGOCIO              │
│  (sección explicativa con íconos)                    │
└──────────────────────────────────────────────────────┘
```

---

## 5. Secciones principales

### Header
Identifica al prospecto desde el primer segundo. Muestra el nombre de su empresa, rubro y ciudad. Incluye el badge de STEPFlow como sistema que está operando.

### Métricas
Cinco indicadores clave presentados como cards numéricas. Los números son simulados pero realistas para el rubro del prospecto. Generan la sensación de que el sistema ya está produciendo resultados.

### Pipeline
Vista tipo Kanban con columnas: Nuevo → Contactado → Respondió → Interesado → Demo → Cerrado.
Cada columna tiene leads reales del prospecto o similares a su industria.

### Actividad reciente
Feed cronológico de eventos del sistema: mensajes enviados, respuestas recibidas, demos sugeridas, seguimientos pendientes. Da sensación de actividad en tiempo real.

### Ficha de lead
Tarjeta expandida de un lead real o ficticio del nicho del prospecto. Muestra nombre, empresa, fuente, prioridad, mensaje generado por Jordan y siguiente acción recomendada.

### Cómo trabajaría STEPFlow
Sección explicativa con cuatro pasos: Captación → Automatización → Seguimiento → Conversión. Texto adaptado al rubro del prospecto. Cierra con llamada a la acción.

---

## 6. Cómo se personaliza para cada prospecto

Toda la personalización ocurre en un único archivo:

```
demo_app/data/demo_company.json
```

**Campos personalizables:**

```json
{
  "nombre_empresa": "Inmobiliaria Del Sur",
  "rubro": "Inmobiliaria",
  "ciudad": "Buenos Aires",
  "color_principal": "#2563eb",
  "metricas": { ... },
  "pipeline": { ... },
  "actividad": [ ... ],
  "lead_destacado": { ... },
  "textos": { ... }
}
```

Para crear una demo para un nuevo prospecto:
1. Duplicar `demo_company.json`
2. Editar los campos con los datos del prospecto
3. Apuntar `script.js` al nuevo archivo (o renombrarlo)
4. Abrir `index.html` en el navegador

Tiempo estimado de personalización: **5 a 10 minutos**.

---

## 7. Qué datos son simulados

| Dato | Simulado | Criterio de simulación |
|---|---|---|
| Métricas numéricas | Sí | Realistas para el rubro y tamaño del negocio |
| Leads en pipeline | Sí | Nombres y empresas plausibles del nicho |
| Actividad reciente | Sí | Eventos coherentes con el flujo de STEPFlow |
| Mensajes generados | Sí | Basados en templates reales del sistema |
| Nombre de empresa | No | Dato real del prospecto |
| Rubro y ciudad | No | Dato real del prospecto |

---

## 8. Evolución futura

**V1 (actual):** demo estática, datos en JSON local, sin backend.

**V2:** demo generada automáticamente desde el pipeline real de STEPFlow. El sistema extrae los datos del prospecto del CRM y genera la demo personalizada en segundos.

**V3:** demo en vivo con datos reales. El prospecto ve su pipeline real operando en STEPFlow. Se convierte en el panel de control definitivo.

---

## 9. Relación con STEPFlow V1

La demo no es parte del sistema operativo de STEPFlow. Es una herramienta de ventas que vive en `demo_app/` de forma independiente.

Comparte la filosofía del sistema:
- Sin complejidad innecesaria
- Orientada a resultados (conversión del prospecto)
- Modular y personalizable
- Preparada para escalar

---

## 10. Conexión futura a backend real

Cuando STEPFlow tenga backend funcional (Supabase + n8n), `script.js` puede reemplazar la carga del JSON local por una llamada a la API:

```javascript
// V1 — local
const data = await fetch('./data/demo_company.json').then(r => r.json());

// V2 — backend real
const data = await fetch('https://api.stepflow.io/demo/prospecto-id').then(r => r.json());
```

La estructura HTML y CSS no cambia. Solo cambia la fuente de datos.
