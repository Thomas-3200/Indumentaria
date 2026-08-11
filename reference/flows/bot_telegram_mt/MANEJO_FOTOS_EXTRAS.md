# Cómo agregar más fotos a un producto existente

> Objetivo: tener 4+ fotos por producto para que la rotación funcione y los posts no se repitan visualmente.

## Flujo recomendado

### 1. Mandá las fotos al bot

Como siempre — Lucas manda 2-4 fotos extras del producto X al chat del bot. El bot las analiza con Claude Vision.

### 2. Escribí `LISTO`

El sync corre y crea **un producto duplicado** (porque la agrupación usa fecha). No te preocupes — lo vamos a unir.

### 3. Verificá qué se creó

```bash
python flows/bot_telegram_mt/list_products.py --client stylo_fino --duplicates
```

Vas a ver algo así:
```
⚠ chaleco / negro / Nike → 2 productos:
    - id=ae5810f7  fotos=1  'Chaleco Nike Negro Acolchado'  active=True
    - id=12345678  fotos=3  'Chaleco Nike Negro Acolchado'  active=True
```

El `id=ae5810f7` es el original (active, tagueado, con precio).
El `id=12345678` es el duplicado nuevo con las fotos extras.

### 4. Unilas con merge_photos

```bash
# Primero dry-run para verificar
python flows/bot_telegram_mt/merge_photos.py --client stylo_fino \
  --from 12345678 --to ae5810f7 --dry-run

# Si todo OK, aplicalo
python flows/bot_telegram_mt/merge_photos.py --client stylo_fino \
  --from 12345678 --to ae5810f7
```

Resultado:
- El producto original (`ae5810f7`) queda con **4 fotos** (1 propia + 3 nuevas)
- El duplicado (`12345678`) queda `active=False` (no se borra, solo se desactiva)
- La próxima vez que se mande la agenda, la rotación usa las 4 fotos distintas

### 5. Verificá el resultado

```bash
python flows/bot_telegram_mt/list_products.py --client stylo_fino
```

El original debería decir `4 fotos` ahora. Sin `⚠`.

---

## Estado actual del catálogo

Para ver cuántos productos tienen pocas fotos hoy:

```bash
python flows/bot_telegram_mt/list_products.py --client stylo_fino
```

| Indicador | Significado |
|---|---|
| `⚠ 1` | Solo 1 foto — la rotación va a mostrar warning al operador |
| `⚠ 2` | 2 fotos — alcanzan para post IG/FB diferentes, pero historia y estado repiten |
| `⚠ 3` | 3 fotos — historia repite con post pero estado y FB ya van con foto propia |
| ` 4+` | Rotación completa OK — cada publicación con foto distinta |

Meta: tener `4+` en todos los productos del calendario del sprint.

---

## Atajo: cargar muchas fotos de productos viejos en bloque

Si querés cargar fotos a varios productos viejos de una sola sesión:

1. Sentate con Lucas con los productos físicos y la cámara.
2. Fotear 2-4 ángulos de CADA producto que tenga `⚠`.
3. Mandar al bot **TODO en una sola sesión** del día (mismo día = mismo grupo de fecha).
4. Escribir `LISTO`. El sync crea productos duplicados de cada uno.
5. Listar con `--duplicates` y mergear uno por uno (mismo bash loop si querés).

Tiempo estimado: ~5 segundos por merge una vez que sabés los IDs.
