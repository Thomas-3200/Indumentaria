# Módulo: Control de Stock por API Humana

**Versión:** 2.0
**Fecha:** 2026-04-26
**Status:** Producción — Amapola
**Workflow ID:** `bikyBMqsj95FbS0O`
**Workflow name:** `Amapola — Handler Aprobación de Paola`
**Transporte:** Telegram Bot API
**Bot username:** `PaolaMancusoAmapola2026_bot`

---

## Descripción

Este módulo permite actualizar el stock del catálogo de productos directamente desde Telegram, sin formularios, sin paneles y sin acceso a ningún sistema externo. Paola (responsable de ventas en Amapola) envía un mensaje al bot con un comando simple — o tapea un botón en el catálogo web —, y el sistema actualiza el stock en Notion, le confirma el resultado por Telegram y, si el stock llega a cero, cancela automáticamente las publicaciones futuras asociadas a ese producto.

**Problema que resuelve:** el stock físico se actualiza en el momento de la venta, en persona o por chat, y existe un desfase constante entre la realidad del depósito y lo que Notion registra. Este módulo cierra ese desfase sin requerir que el operador cambie de contexto o aprenda a usar ninguna interfaz.

**Por qué Telegram y no WhatsApp:** Telegram Bot API no tiene la restricción de la ventana de 24h, no requiere plantillas pre-aprobadas, soporta archivos hasta 2GB y tiene riesgo de baneo prácticamente nulo en uso normal. Para comunicación interna sistema↔operador es la mejor opción técnica. WhatsApp queda libre para que Paola lo use con clientes finales.

**Para quién:** operadores de ventas con acceso al bot. En producción: Paola, su `chat_id` queda registrado al hacer `/start` con el bot.

---

## Diagrama de flujo

```
Telegram / Bot API
         |
         v
[1] Webhook — Respuesta de Paola
    POST https://n8n.agenciaiasm.online/webhook/amapola-aprobacion
    Payload: $json.body.message  (formato Telegram)
         |
         v
[2] Responder 200 OK
    respondToWebhook v1 — respuesta HTTP inmediata al proveedor
         |
         v
[3] Detectar Tipo Mensaje
    code v2
    - extrae texto desde body.message.text
    - soporta deep links: /start vendi_AMP-005_1 → "vendi AMP-005 1"
    - normaliza acentos (vendí → vendi, vendió → vendio)
    - evalúa regex para detectar comandos de stock
    - outputs: __is_stock (boolean), __text (string), __from (string), __chat_id (string)
         |
         v
[4] ¿Es comando de stock?
    if v2 — evalúa __is_stock
         |
    true |                    | false
         v                    v
[5] Parsear Comando Stock   [rama aprobación — abajo]
    code v2
    - extrae: action, codigo, qty, from, chat_id
         |
         v
[6] Stock — Procesar Todo
    code v2
    - consulta Notion catálogo por Código
    - calcula nuevo stock
    - actualiza propiedad Stock + Activo en Notion
    - si stock = 0: consulta calendario, cancela posts programados
    - envía mensaje Telegram de confirmación al chat_id
         |
         v
    Mensaje Telegram de confirmación
    (o silencio si el producto no existe)
```

**Rama aprobación (cuando no es comando de stock):**

```
[5'] Parsear Intención de Paola
     - clasifica: 'todo ok' → aprobar_todo
                  'cambio lunes: ...' → cambio
                  'cancelar lunes' → cancelar
                  resto → desconocido / skip
         |
         v
[6'] ¿Intención válida?
     if v1 — filtra desconocido y skip
         |
         v
[7'] Switch — Tipo de Respuesta
     - aprobar_todo → Marcar Todos como Aprobados (PATCH Notion)
     - cambio       → Guardar Cambio en Notion (PATCH Notion)
         |
         v
[8'] Confirmar a Paola
     code v2 — sendMessage a Telegram con resumen de la acción
```

---

## Tabla de comandos

| Comando | Acción | Variable `action` | Resultado en Notion |
|---------|--------|-------------------|---------------------|
| `vendi AMP-005` | Descontar 1 unidad del stock actual | `venta` | Stock = stock_actual - 1 |
| `vendi AMP-005 3` | Descontar N unidades del stock actual | `venta` | Stock = stock_actual - 3 |
| `sin stock AMP-005` | Fijar stock en cero | `sin_stock` | Stock = 0, Activo = false |
| `stock AMP-005 3` | Fijar stock en un valor absoluto | `set_stock` | Stock = 3 |
| `/start vendi_AMP-005_1` | Equivalente a `vendi AMP-005 1` (deep link del catálogo web) | `venta` | Stock = stock_actual - 1 |
| `/start sin_stock_AMP-005` | Equivalente a `sin stock AMP-005` (deep link) | `sin_stock` | Stock = 0 |

---

## Variantes aceptadas del mismo comando

El nodo `Detectar Tipo Mensaje` normaliza el texto antes de aplicar el regex. Las siguientes variantes son equivalentes:

| Variante recibida | Normalizada internamente | Interpretada como |
|-------------------|--------------------------|-------------------|
| `vendí AMP-005` | `vendi AMP-005` | `action=venta, qty=1` |
| `vendido AMP-005` | `vendido AMP-005` | `action=venta, qty=1` |
| `se vendio AMP-005` | `se vendio AMP-005` | `action=venta, qty=1` |
| `se vendió AMP-005` | `se vendio AMP-005` | `action=venta, qty=1` |
| `VENDI AMP-005` | `vendi AMP-005` | `action=venta, qty=1` |
| `vendi  AMP-005` (espacios extra) | `vendi AMP-005` | `action=venta, qty=1` |
| `Vendí AMP-005 3` | `vendi AMP-005 3` | `action=venta, qty=3` |
| `Sin Stock AMP-005` | `sin stock AMP-005` | `action=sin_stock, qty=0` |
| `Stock AMP-005 3` | `stock AMP-005 3` | `action=set_stock, qty=3` |
| `/start vendi_AMP-005_3` | `vendi AMP-005 3` | `action=venta, qty=3` (deep link) |

La normalización aplica `toLowerCase()` + reemplazo de vocales acentuadas + colapso de espacios. Para deep links, el `_` se reemplaza por espacio antes del regex.

---

## Catálogo web visual

**URL:** `https://n8n.agenciaiasm.online/webhook/amapola-catalogo`
**Workflow:** `6sc6Q9GeFVcskfAN` (Amapola - Catalogo Web)

Página HTML mobile-first que Paola guarda como acceso directo en su pantalla principal. Muestra todos los productos activos con imagen, nombre, código y stock actual. Cada producto tiene tres botones (`Vendí 1`, `Vendí 2`, `Vendí 3+`) que abren Telegram con el deep link correspondiente. Paola solo tapea enviar.

La página se renderiza en vivo desde Notion en cada GET — cero caché — así que el stock que ve siempre es el actual.

---

## Comportamiento ante errores

**Producto no existe en el catálogo**

El nodo `Stock — Procesar Todo` consulta Notion filtrando por `Código` (title). Si no hay resultados, retorna `{ error: "AMP-XXX no encontrado en catálogo", ok: false }` y la ejecución termina sin enviar nada al chat. El error queda en logs de n8n.

**Stock ya en cero al intentar venta**

El nodo aplica `Math.max(0, stock - qty)`. Si el resultado es negativo, queda en 0 (no en negativo). Se envía igualmente el mensaje de confirmación con el stock resultante.

**Mensaje desconocido o texto libre**

El nodo `Detectar Tipo Mensaje` evalúa `__is_stock = false`. La rama de aprobación clasifica como `desconocido` o `skip` y termina silenciosamente. No hay efecto en stock ni catálogo.

**Mensaje de chat_id no autorizado**

En la versión 2.0 el sistema **no valida chat_id estrictamente** porque el bot es privado y solo accesible vía link. Cualquier chat que escriba al bot pasa. Si más adelante se quiere restringir a Paola exclusivamente, agregar en `Detectar Tipo Mensaje`:

```javascript
const PAOLA = 'XXXXXXXXX';  // chat_id de Paola
if (from && from !== PAOLA) {
  return [{ json: { skip: true, reason: 'chat no autorizado' } }];
}
```

---

## Conexión con publicaciones futuras

Cuando una operación de stock produce `stock = 0`, el nodo `Stock — Procesar Todo` ejecuta una segunda consulta al calendario editorial (Notion DB `2768fd1adc8040eb9c72c1a478776818`) con los siguientes filtros:

- `Fecha` >= fecha actual (hoy)
- `Publicado en` vacío (post aún no publicado)
- `URL Imagen` contiene el valor del campo `Imagen` del producto en el catálogo

Por cada post que cumpla los filtros, el nodo actualiza `Notas` con texto de cancelación y marca `Publicado en` con la fecha actual (lo saca del pool de publicación). El mensaje de confirmación incluye el conteo de posts cancelados.

> **Nota:** además de esta cancelación reactiva (al vender), existe una validación proactiva en el workflow de publicación `28H02VLFJO28Lb9P` (nodo `Validar Stock del Producto`) que revisa el stock al momento de publicar cada post — doble red de seguridad.

---

## Reglas de seguridad

- El bot es accesible solo por link (`https://t.me/PaolaMancusoAmapola2026_bot`). No es público ni indexado.
- No hay contraseñas, PINs ni comandos de autenticación en el flujo.
- No hay panel de administración expuesto. La única interfaz son los mensajes al bot + el catálogo web HTML.
- Las credenciales (token Telegram, integration token Notion) están embebidas en los Code nodes en v2.0. La migración a n8n Credentials / variables de entorno es la próxima mejora recomendada para facilitar la rotación sin tocar código.
- El webhook de inbound tiene un `webhookId` UUID generado al activar el workflow. Telegram firma el payload con HTTPS pero no requiere validación HMAC adicional para este caso de uso (un solo bot, un solo destinatario).

> **Deuda técnica v2.1:** (a) mover tokens a n8n Credentials / env vars, (b) agregar validación de `chat_id` para hardening multi-tenant, (c) agregar callback queries para botones inline en mensajes outbound.

---

## IDs técnicos

| Recurso | ID / Valor | Nota |
|---------|------------|------|
| Workflow handler n8n | `bikyBMqsj95FbS0O` | Reemplazar por ID del workflow del cliente |
| Workflow catálogo web | `6sc6Q9GeFVcskfAN` | Reemplazar por slug del cliente |
| Webhook path inbound | `/webhook/amapola-aprobacion` | URL final: `https://n8n.agenciaiasm.online/webhook/amapola-aprobacion` |
| Webhook path catálogo | `/webhook/amapola-catalogo` | URL final: `https://n8n.agenciaiasm.online/webhook/amapola-catalogo` |
| Bot Telegram username | `PaolaMancusoAmapola2026_bot` | Reemplazar por bot del cliente |
| Bot Telegram token | `8282190301:AAH5wL...` | En n8n Code nodes (mover a credentials en v2.1) |
| Notion — Catálogo | `34c8503a-7d38-81c6-8e29-ed3d80014089` | Reemplazar por DB del cliente |
| Notion — Calendario | `2768fd1adc8040eb9c72c1a478776818` | Reemplazar por DB del cliente |
| Host n8n | `n8n.agenciaiasm.online` | Reemplazar por host n8n del cliente si es instancia dedicada |

---

## Guía de adaptación para nuevo cliente

Pasos para replicar este módulo en un cliente nuevo:

1. Crear un bot nuevo en BotFather (`/newbot`), elegir nombre y username, anotar el token.
2. Configurar el webhook del bot apuntando al webhook de inbound del cliente: `setWebhook` con `url=https://[host]/webhook/[slug]-aprobacion`.
3. Crear copia del workflow `bikyBMqsj95FbS0O` en la instancia n8n del cliente (o en la compartida con path diferente).
4. Crear copia del workflow `6sc6Q9GeFVcskfAN` (catálogo web). Cambiar el `BOT_USERNAME` en el Code node por el username del nuevo bot.
5. Actualizar el path del webhook al slug del cliente: `/webhook/[nombre-cliente]-aprobacion` y `/webhook/[nombre-cliente]-catalogo`.
6. En los Code nodes, reemplazar el token de Telegram por el del bot del cliente.
7. Crear la Notion DB de catálogo con propiedades requeridas: `Código` (title), `Nombre` (text), `Stock` (number), `Activo` (checkbox), `Imagen` (url), `Precio` (number), `Descripción` (text).
8. Crear la Notion DB de calendario editorial con propiedades: `Fecha` (date), `URL Imagen` (url), `Publicado en` (date), `Notas` (rich_text), `Estado Publicación` (select), `Motivo Cancelación` (rich_text), `Fecha Cancelación` (date), `Producto Asociado` (rich_text), `Stock al momento de validar` (number).
9. En los Code nodes, reemplazar los IDs de Notion por los del cliente.
10. Cargar el catálogo inicial en Notion con códigos exactos.
11. El operador hace `/start` con el bot. Capturar su `chat_id` desde el primer ejecución del webhook.
12. Hacer una prueba completa con los 4 comandos principales sobre un producto de prueba antes de activar en producción.

---

## Tabla de test cases

| Comando enviado | Acción esperada | Nodo final ejecutado | Resultado |
|-----------------|-----------------|----------------------|-----------|
| `vendi AMP-005` | Descontar 1 unidad | Stock — Procesar Todo | Stock reducido en 1, confirmación Telegram enviada |
| `vendí AMP-005` | Descontar 1 unidad (variante con tilde) | Stock — Procesar Todo | Igual — normalización OK |
| `vendido AMP-005` | Descontar 1 unidad (variante texto) | Stock — Procesar Todo | Stock reducido en 1, confirmación Telegram enviada |
| `se vendio AMP-005` | Descontar 1 unidad (variante sin tilde) | Stock — Procesar Todo | Stock reducido en 1, confirmación Telegram enviada |
| `sin stock AMP-005` | Fijar stock en 0 | Stock — Procesar Todo | Stock = 0, posts futuros cancelados, confirmación Telegram con conteo |
| `stock AMP-005 2` | Fijar stock en 2 | Stock — Procesar Todo | Stock = 2, confirmación Telegram |
| `/start vendi_AMP-005_3` | Deep link desde catálogo: vender 3 unidades | Stock — Procesar Todo | Stock reducido en 3, confirmación Telegram |
| `hola` | Ninguna — texto libre | ¿Intención válida? (skip) | Sin efecto. Termina silenciosamente. |
| `gracias` | Ninguna — texto libre | ¿Intención válida? (skip) | Sin efecto. Termina silenciosamente. |
| `todo ok` | Aprobación de posts | Confirmar a Paola | Marca Aprobado=true en posts de la semana, envía confirmación Telegram |
| `cambio lunes: nuevo caption` | Modificar post del lunes | Confirmar a Paola | PATCH al post del lunes con el nuevo Caption, envía confirmación |
| `cancelar lunes` | Cancelar post del lunes | (rama cancelar) | Marca el post como cancelado |

---

## Changelog

**v2.0 — 2026-04-26**
- Migración de WhatsApp Business API a Telegram Bot API
- Catálogo web visual con deep links al bot
- Soporte para `/start` con parámetros (deep links)
- Eliminación de validación estricta de chat_id (bot es privado por link)
- Renombrado: `WA Notificar Paola` → `TG Notificar Paola`, `Enviar WhatsApp a Paola` → `Enviar Telegram a Paola`

**v1.0 — 2026-04-25**
- Versión inicial con WhatsApp Business API
- Comandos: `vendi`, `sin stock`, `stock N`
- Cancelación automática de posts futuros cuando stock = 0
- Documentación + 9 test cases pasados
