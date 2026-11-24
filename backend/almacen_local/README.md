# Journal local de ventas (issue #14)

Cada venta se confirma escribiéndose aquí, no en BigQuery. Es lo que
hace que capturar una venta tome milisegundos y siga funcionando sin
internet — ver #55.

```
Enter → escribir_venta() → ventas-2026-08-31.jsonl (fsync)
                                  │
                                  ▼  en segundo plano (#15)
                             BigQuery
```

## Formato

Un archivo `.jsonl` por día de calendario, en `datos_locales/journal/`
(configurable con el parámetro `carpeta` de cada función — usado en los
tests para no tocar nunca la carpeta real).

Dos tipos de línea, append-only — nunca se reescribe nada, se agrega
una línea nueva que complementa a la anterior:

```json
{"evento": "venta", "id": "...", "total": 20.0, "lineas": [...], ...}
{"evento": "confirmacion", "id": "...", "confirmado_en": "2026-08-31T20:01:00+00:00"}
```

El estado de una venta (`pendiente` / `enviada`) se **calcula** al leer
— nunca se guarda como campo mutable. Es el mismo principio append-only
que usamos para `venta`/`cierre` en BigQuery (#8), aplicado aquí mismo.

## Funciones

| Función | Uso |
|---|---|
| `escribir_venta(datos)` | Confirma una venta. Lo llama la pantalla de venta (#20/#22) |
| `leer_dia(fecha)` | Ventas del día, con su estado calculado. Fuente para "ventas del día en curso" — no toca BigQuery |
| `leer_pendientes(fecha)` | Solo lo que falta subir. Lo usa el sincronizador (#15) |
| `marcar_confirmada(id, fecha)` | Lo llama #15 tras un insert exitoso a BigQuery |
| `reconstruir_desde(inicio, fin)` | Varios días de una vez — recuperar backlog tras una caída larga |

## Compartido con el repositorio de BigQuery

`escribir_venta` arma la fila con
[`acceso_datos.modelos_venta.construir_venta`](../acceso_datos/modelos_venta.py),
el mismo helper que usa `acceso_datos.repositorios.ventas.insertar()`.
Así las dos rutas de escritura (local y BigQuery) nunca pueden divergir
en qué campos lleva una venta o cómo se normalizan las líneas.

## Requisito de infraestructura

El journal debe vivir en **disco local**, nunca en una unidad de red ni
en una carpeta sincronizada por Drive/Dropbox:

- `fsync` sobre una unidad de red puede tardar segundos en vez de
  milisegundos — rompe el criterio de "menos de 100ms por venta".
- Un sincronizador de archivos puede copiar el `.jsonl` a medio
  escribir y corromperlo — mismo riesgo que se documentó para SQLite en
  una versión anterior del plan; aplica igual aquí.

## Comando de auditoría

```bash
cd backend
python -m almacen_local.reconstruir --dia 2026-08-31
python -m almacen_local.reconstruir --desde 2026-08-01 --hasta 2026-08-31
```

Muestra el total del período y cuántas ventas siguen sin subir a
BigQuery, leyendo únicamente del journal local.

## Sincronización a BigQuery (issue #15)

`sincronizador.py` es el otro lado del journal: un hilo daemon que
corre dentro del mismo proceso de Flask/Waitress (arranca en
`main.py`, sólo cuando corre como proceso principal — nunca al
importar el módulo, para no disparar hilos durante los tests) y en
bucle:

1. Revisa hoy y hasta 30 días atrás (`journal.leer_pendientes`).
2. Sube lo pendiente a BigQuery (`insertar_filas`, streaming).
3. Marca cada venta como confirmada (`journal.marcar_confirmada`).
4. Duerme, con backoff exponencial si algo falló (5s → 10s → 20s...
   hasta un tope de 60s).

**Nunca bloquea una venta** — corre en su propio hilo, separado del
que atiende las peticiones HTTP. Si falla un día completo (típicamente:
sin internet), corta el ciclo ahí mismo en vez de intentar los 29 días
restantes con el mismo error.

**Estado persistido**: la marca de tiempo de la última sincronización
exitosa se guarda en `estado_sincronizacion.json`, junto al journal —
sobrevive a un reinicio del proceso, para que el indicador de "hace
cuánto no sincroniza" (pendiente, UI) no se resetee a "nunca" con sólo
reiniciar la app.

> El issue original proponía "elegir destino: Drive, S3, GCS o
> Backblaze B2" — eso aplicaba cuando SQLite era la base local y el
> journal era un respaldo aparte. Con BigQuery como base (#7/#8), el
> destino ya está decidido: es BigQuery mismo, no un almacén de
> archivos adicional.

## Lo que este módulo NO hace

No expone un endpoint HTTP para consultar el estado de sincronización
desde el frontend — `Sincronizador.estado()` existe como función
Python, lista para que un endpoint futuro la use, pero ese endpoint no
se construyó en este issue.
