# Ecosistema Amapola — Mapa Completo

**Versión:** 2.0
**Fecha:** 2026-04-26
**Status:** Producción
**Operador:** Paola (Amapola)
**Transporte de mensajería:** Telegram Bot API
**Bot:** [@PaolaMancusoAmapola2026_bot](https://t.me/PaolaMancusoAmapola2026_bot)

---

## Visión general

Amapola es un negocio físico de productos artesanales operado por una sola persona (Paola). El ecosistema Stepflow le automatiza tres cosas:

1. **Publicación programada** de posts a Instagram, Facebook y WhatsApp Estado
2. **Aprobación semanal** de los posts antes de que se publiquen
3. **Control de stock en tiempo real** desde Telegram + catálogo web

El sistema se diseña para que Paola **no tenga que aprender ninguna interfaz nueva** ni cambiar su rutina. Las únicas pantallas que ve son: WhatsApp (clientes), Telegram (sistema), y un link de catálogo guardado como acceso directo.

---

## Mapa de workflows

| Workflow ID | Nombre | Trigger | Función | Estado |
|-------------|--------|---------|---------|--------|
| `Sy2tLhA7YdqG6GUj` | Amapola — Envío Agenda Semanal | Cron domingo 18:00 | Manda a Paola los posts de la semana próxima vía Telegram | ON |
| `bikyBMqsj95FbS0O` | Amapola — Handler Aprobación de Paola | Webhook `/amapola-aprobacion` | Recibe respuestas de Paola desde Telegram (aprobaciones, cambios, comandos de stock) | ON |
| `28H02VLFJO28Lb9P` | Amapola — Auto Publicar Contenido v2 | Cron horario | Publica posts aprobados en IG/FB y notifica WA Estado a Paola via Telegram. Valida stock antes de publicar | ON |
| `6sc6Q9GeFVcskfAN` | Amapola — Catálogo Web | Webhook `/amapola-catalogo` | Sirve HTML con productos + botones que abren Telegram con comandos pre-armados | ON |
| `iQQXFEYRf5U9G46a` | Amapola — Image Proxy | Webhook | Proxy de imágenes para evitar problemas de hotlinking | ON |
| `RtkJl0wr7d2HoPtu` | Amapola — Actualizar Stock | (legacy) | Workflow viejo duplicado. Reemplazado por la rama de stock en `bikyBMqsj95FbS0O` | OFF |
| `D5vXYv1abyrfFMFq`, `QIy2xgi1RcF6PCMA` | Amapola — Publicar Contenido (v1) | (legacy) | Versiones anteriores del publicador | OFF |

---

## Flujo end-to-end

### Domingo 18:00 — Envío de agenda semanal

```
[Cron Sy2tLhA7YdqG6GUj]
       │
       ▼
Lee Notion calendario → posts cuya Fecha está entre +1 y +7 días
       │
       ▼
Formatea mensaje Markdown agrupando por día (lun/mar/mié...)
       │
       ▼
Envía Telegram a Paola → mensaje con la agenda completa + instrucciones
```

Mensaje que recibe Paola (ejemplo):

```
🌸 Amapola — Agenda 27/4 al 3/5

Lun 27/4
  📸 09:00 IG 🤖 _Pulsera dorada minimal..._
  📘 14:00 FB 🤖 _Pulsera dorada minimal..._

Mar 28/4
  📸 11:00 IG 🤖 _Collar plata cadena..._
  💚 18:00 WA Estado 📲 _Promo del finde..._
...

📊 5 automáticos 🤖 | 2 manuales 📲

¿Todo bien con los posts automáticos?

Respondé con:
  ✅ todo ok → apruebo todos
  ✏️ cambio lunes: [texto] → editás el caption
  ❌ cancelar lunes → cancelás ese post
```

### Lunes a sábado — Aprobación e interacciones

Paola responde por Telegram. El handler `bikyBMqsj95FbS0O` clasifica el mensaje:

| Mensaje de Paola | Intent detectado | Acción del sistema |
|------------------|------------------|---------------------|
| `todo ok` | `aprobar_todo` | PATCH a Notion: marca todos los posts pendientes como `Aprobado=true` |
| `cambio lunes: nuevo caption del lunes` | `cambio` | PATCH al post del lunes con el nuevo `Caption` |
| `cancelar lunes` | `cancelar` | Marca el post del lunes como cancelado |
| `vendi AMP-005` | (rama stock) | Descuenta 1 del stock catalogo |
| `vendi AMP-005 3` | (rama stock) | Descuenta 3 del stock |
| `sin stock AMP-005` | (rama stock) | Fija stock=0 + cancela posts futuros del producto |
| `stock AMP-005 5` | (rama stock) | Fija stock en valor absoluto |
| `/start vendi_AMP-005_2` | (rama stock) | Deep link del catálogo web → equivale a `vendi AMP-005 2` |
| `hola`, `gracias`, texto libre | `desconocido` | Termina silenciosamente |

Después de cada acción, el sistema responde a Paola con confirmación Telegram.

### Cada hora — Publicación automática

```
[Cron Trigger Hourly en 28H02VLFJO28Lb9P]
       │
       ▼
Lee Notion calendario → posts con Aprobado=true AND Fecha=hoy AND Publicado en vacío
       │
       ▼
Filtrar por Hora (compara Hora del post con la hora actual GMT-3)
       │
       ▼
Validar Stock del Producto ← MÓDULO DE VALIDACIÓN
   - Extrae código del producto desde Producto Asociado o Notas (regex)
   - Si no hay código → pasa sin validar
   - Si hay código → query catálogo: stockOk = activo && stock > 0
       │
       ▼
¿Stock OK?
   │
   ├── true ──→ Router Red Social ──→ FB / IG / Telegram (según campo)
   │
   └── false ─→ Cancelar Post en Notion
                (Estado=Cancelado, Motivo, Fecha, Stock al momento de validar)
                FIN — sin publicar nada
```

Por cada plataforma:
- **Facebook:** POST a graph.facebook.com con la imagen y caption
- **Instagram:** flujo de 7 pasos (descargar → subir a FB → obtener CDN URL → crear container → wait 5s → publicar → marcar publicado)
- **WhatsApp Estado:** envía la imagen con caption a Paola por Telegram con texto "📲 Estado WA para subir manualmente" (es ella quien lo sube al estado)

### Cuando Paola vende algo

```
[Paola tapea "Vendí 1" en el catálogo web]   o   [tipea "vendi AMP-005" al bot]
       │
       ▼
Telegram envía POST al webhook /amapola-aprobacion
       │
       ▼
Handler bikyBMqsj95FbS0O — rama stock
       │
       ▼
Stock — Procesar Todo:
   1. Query Notion catálogo por Código
   2. Calcular nuevo stock (stock - qty | 0 | qty)
   3. PATCH catálogo: actualizar Stock + Activo
   4. Si nuevo stock = 0:
      - Query calendario: posts futuros con la imagen del producto
      - PATCH cada post: marca Publicado en + Notas con "CANCELADO AUTO"
   5. sendMessage a Paola por Telegram con el resumen
       │
       ▼
Paola recibe en Telegram:
   ✅ Stock actualizado!

   🏷️ Pulsera Dorada
   📦 4 → 3 uds.
```

---

## Notion — Esquema de bases de datos

### DB Catálogo (`34c8503a-7d38-81c6-8e29-ed3d80014089`)

| Propiedad | Tipo | Uso |
|-----------|------|-----|
| `Código` | title | Identificador único (ej: `AMP-005`) |
| `Nombre` | rich_text | Nombre legible del producto |
| `Stock` | number | Stock actual (0 a N) |
| `Activo` | checkbox | true=publica, false=oculto |
| `Imagen` | url | URL imagen del producto |
| `Precio` | number | Precio de venta |
| `Descripción` | rich_text | Texto largo del producto |

### DB Calendario Editorial (`2768fd1adc8040eb9c72c1a478776818`)

| Propiedad | Tipo | Uso |
|-----------|------|-----|
| `Publicación` | title | Identificador del post |
| `Fecha` | date | Fecha de publicación programada |
| `Hora` | select | Hora del día (`09:00`, `14:00`...) |
| `Caption` | rich_text | Texto del post |
| `Hashtags` | rich_text | Tags |
| `URL Imagen` | url | Imagen a publicar |
| `URL Video` | url | Video opcional |
| `Red Social` | select | `Instagram`, `Facebook`, `WhatsApp Estado`, `Historia IG`, `Carrusel IG` |
| `Tipo` | select | Tipo de post |
| `Modo` | select | `Automatico` / `Manual` |
| `Aprobado por Paola` | checkbox | Si Paola dio OK |
| `Publicado en` | date | Fecha en que se publicó (vacío = pendiente) |
| `Estado` | status | Estado de gestión |
| `Notas` | rich_text | Notas + a veces código del producto (`📦 AMP-005 \| ...`) |
| `Semana` | rich_text | Identificador de semana |
| `Estado Publicación` | select | `Pendiente`, `Publicado`, `Cancelado` |
| `Motivo Cancelación` | rich_text | Razón si se canceló |
| `Fecha Cancelación` | date | Cuándo se canceló |
| `Producto Asociado` | rich_text | Código del producto (preferido sobre Notas) |
| `Stock al momento de validar` | number | Stock que tenía cuando se canceló |

---

## URLs útiles

| Recurso | URL |
|---------|-----|
| Catálogo web (Paola) | `https://n8n.agenciaiasm.online/webhook/amapola-catalogo` |
| Webhook inbound bot Telegram | `https://n8n.agenciaiasm.online/webhook/amapola-aprobacion` |
| Bot Telegram (link público) | `https://t.me/PaolaMancusoAmapola2026_bot` |
| n8n UI | `https://n8n.agenciaiasm.online` |
| Notion DB Catálogo | abrir Notion |
| Notion DB Calendario | abrir Notion |

---

## Credenciales y secretos

> **Pendiente v2.1:** mover a n8n Credentials / variables de entorno.

| Servicio | Token | Ubicación actual |
|----------|-------|------------------|
| Telegram Bot | `8282190301:AAH5wL...` | Hardcoded en Code nodes |
| Notion Integration | `ntn_357057487922a92m9...` | Hardcoded en Code nodes |
| Facebook Graph (FB Page) | `EAAKgunFN9JsBR...` | Config node de `28H02VLFJO28Lb9P` |
| Facebook Graph (IG) | (mismo token) | Config node |

---

## Operación día a día — punto de vista de Paola

**Domingo 18:00**
- Le llega un mensaje al bot con la agenda de la semana
- Lee, decide
- Responde `todo ok` (toma 2 segundos)
- Si quiere cambiar algo: `cambio lunes: nuevo texto del post`

**Lunes a sábado**
- Ve clientes
- Cuando vende algo, abre el acceso directo del catálogo (parece una app) en su pantalla principal
- Tapea el producto vendido y el botón `Vendí 1`
- Telegram se abre con el comando ya escrito → tapea enviar
- En 2 segundos recibe la confirmación

**Cualquier momento**
- Si quiere consultar stock, abre el catálogo y mira
- Si tiene reposición de stock: `stock AMP-005 10` al bot

**Si un producto se queda sin stock**
- El sistema cancela automáticamente los posts futuros que iban a publicar ese producto
- Le avisa por Telegram cuántos canceló
- Cuando reponga: `stock AMP-005 5` reactiva todo (nuevos posts pueden agendarse)

---

## Métricas y monitoreo (recomendado v2.1)

A futuro conviene agregar:

- Dashboard de salud del sistema (ejecuciones success vs error por workflow)
- Alertas si un workflow falla 3 veces seguidas (notificación al admin Stepflow)
- Tracking de delay entre venta y actualización de stock
- Reporte semanal automático: cuántos posts se publicaron, cuántos se cancelaron, ventas estimadas

---

## Changelog

**v2.0 — 2026-04-26**
- Migración completa WhatsApp Business API → Telegram Bot API
- Catálogo web visual servido por n8n con deep links al bot
- Workflow duplicado `RtkJl0wr7d2HoPtu` desactivado
- Validación de stock pre-publicación en `28H02VLFJO28Lb9P`
- 5 nuevos campos en Notion calendario (Estado/Motivo/Fecha Cancelación, Producto Asociado, Stock al momento de validar)
- Fix crítico de query Notion (faltaba `=` en interpolación de fecha del nodo `Obtener Posts de Hoy`)

**v1.0 — 2026-04-25**
- Sistema base con WhatsApp Business API
- Módulo de control de stock por API humana
- Aprobación semanal por WhatsApp
- Publicador horario IG/FB/WA
