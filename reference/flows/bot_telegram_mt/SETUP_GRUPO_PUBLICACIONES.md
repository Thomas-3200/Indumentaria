# Setup grupo dedicado para publicaciones (multi-tenant)

> Por defecto el bot manda las publicaciones al chat 1-a-1 con el operador. Eso
> mezcla todo (intake de fotos, `/venta`, `/reply`, kits diarios).
>
> Crear un **grupo dedicado** separa el flujo de publicación del resto.
> Opcional pero recomendado.

## Cómo crear el grupo

### 1. Crear el grupo en Telegram (1 min)

1. En tu cliente Telegram → **Nuevo grupo**.
2. Nombre sugerido: `Stylo Fino · Publicaciones diarias` (cambialo por cliente).
3. Agregar miembros:
   - El **bot del cliente** (ej. `@indumentariastylofino_bot`)
   - El **operador** (Leo, o el que publique)
   - (Opcional) El **lead** (Lucas) si quiere ver el flujo

### 2. Hacer al bot administrador (30 seg)

Esto es obligatorio para que el bot pueda enviar mensajes en el grupo.

1. En el grupo recién creado → tocar el nombre del grupo arriba.
2. Editar grupo → Administradores → Agregar admin.
3. Elegir el bot.
4. Permisos: dejar todo lo básico activo. Lo crítico es **Enviar mensajes** y
   **Editar sus propios mensajes** (para que los botones "✅ Listo" funcionen).
5. Guardar.

### 3. Descubrir el chat_id del grupo (1 min)

1. **Apagar el bot watch** temporalmente (cerrar la ventana o `Ctrl+C`).
   Si no lo apagás, el bot consume las actualizaciones y este helper no las verá.
2. En el grupo, escribir cualquier mensaje (ej `/start` o `test`).
3. Correr el helper:
   ```bash
   python flows/bot_telegram_mt/get_group_chat_id.py --client stylo_fino
   ```
4. El script lista los grupos donde vio actividad reciente. Vas a ver algo así:
   ```
   ✓ GRUPO  chat_id=-1001234567890  type=supergroup  título='Stylo Fino · Publicaciones diarias'
   ```
5. Copiar el `chat_id` (es un número **negativo**, empieza con `-100`).

### 4. Agregar al `.env` (30 seg)

```env
STYLO_FINO_TG_PUBLISH_CHAT_ID=-1001234567890
```

Cambiá el prefix por el del cliente (`<SLUG>_TG_PUBLISH_CHAT_ID`).

### 5. Reiniciar el bot watch (10 seg)

Volver a abrir `run_bot_watch.bat`. El bot vuelve a escuchar.

### 6. Verificar (30 seg)

```bash
python flows/bot_telegram_mt/client_config.py stylo_fino
```

Debería decir:
```
TG publish:     -1001234567890
```

### 7. Probar (1 min)

```bash
python flows/bot_telegram_mt/send_daily_agenda.py --client stylo_fino --date 2026-MM-DD
```

El script imprime al inicio:
```
Destino: grupo dedicado (chat_id=-1001234567890)
```

Y los mensajes llegan al **grupo**, no al chat 1-a-1.

---

## Comportamiento esperado

| Acción | Dónde llega |
|---|---|
| Kit diario (POST IG/FB, HISTORIA, ESTADO) | **Grupo dedicado** |
| Callbacks "✅ Listo / ⏭ Saltar" | Procesados desde el grupo, edita el mensaje ahí |
| `/venta` desde el operador | Chat 1-a-1 con el bot (no en el grupo) |
| `/reply <msg>` desde lead | Chat 1-a-1 con el bot |
| Intake de fotos del lead | Chat 1-a-1 con el bot |

El bot distingue por el `chat.id` del mensaje. Las acciones administrativas
(venta, reply, intake) siguen siendo 1-a-1 — solo los kits de publicación
van al grupo.

---

## Si querés volver al modo 1-a-1

Borrar la línea `<SLUG>_TG_PUBLISH_CHAT_ID` del `.env` y reiniciar el bot.
Vuelve a mandar todo al chat con el operador (default legacy).

---

## Para clientes nuevos

Mismo flujo: el `client_config.json` del cliente nuevo ya tiene reservado el
campo `telegram.publish_chat_id_env` con el nombre del env var que va a leer.

Si nunca cargás `<SLUG>_TG_PUBLISH_CHAT_ID` en el `.env`, el cliente nuevo
funciona en modo 1-a-1 por default. Activar el grupo es opcional por cliente.
