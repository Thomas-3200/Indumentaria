# STEPFlow V1 - Skill Routing

## OBJETIVO

Definir cómo Claude Code debe seleccionar y utilizar las skills dentro del sistema StepFlow.

Este archivo elimina ambigüedad y mejora la eficiencia.

---

## REGLA GENERAL

Antes de ejecutar cualquier tarea:

1. Analizar la intención de la tarea
2. Buscar si existe una skill aplicable en /skills/
3. Usar la skill más específica
4. Evitar duplicar lógica ya existente

---

## MAPEO DE TAREAS → SKILLS

### CAPTACIÓN Y PRIMER CONTACTO
Usar: outreach-engine

Aplicar cuando:
- se trabaje con leads
- se envíen primeros mensajes
- se clasifiquen nichos

---

### GESTIÓN DE DATOS Y CRM
Usar: crm-database

Aplicar cuando:
- se guarden contactos
- se registren mensajes
- se actualicen estados

---

### CREACIÓN Y MEJORA DE MENSAJES
Usar: message-optimizer

Aplicar cuando:
- se generen mensajes
- se optimice copy
- se hagan variantes A/B

---

### DEMOS
Usar: demo-builder

Aplicar cuando:
- se necesite mostrar sistema
- se adapte a un nicho específico

---

### CIERRE DE VENTAS
Usar: sales-closer

Aplicar cuando:
- haya interés del lead
- se ofrezca demo
- se prepare cierre o pago

---

### BÚSQUEDA INTERNA
Usar: librarian

Aplicar cuando:
- se necesite contexto
- se busquen archivos
- se consulten decisiones previas

---

### SEGURIDAD
Usar: security-guard

Aplicar cuando:
- se trabajen credenciales
- se usen APIs
- se manejen datos sensibles

---

### VALIDACIÓN Y QA
Usar: qa-review

Aplicar cuando:
- se termine una tarea
- se valide lógica
- se revisen errores

---

## REGLA DE PRIORIDAD

Si varias skills aplican:

1. usar la más específica
2. si hay duda → usar librarian primero
3. luego ejecutar la skill adecuada

---

## REGLA DE CONTROL

Nunca:

- ignorar skills existentes
- duplicar funcionalidades
- crear lógica paralela innecesaria

---

## OBJETIVO FINAL

Que cada acción dentro de StepFlow:

- tenga claridad
- use la herramienta correcta
- mantenga coherencia del sistema

