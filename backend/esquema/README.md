# Esquema de datos (issue #8)

Definición del esquema sobre BigQuery. Vive en código (`tablas.py`) en vez
de en un diagrama aparte, para que no se desactualice.

## Archivos

- **`tablas.py`** — las seis tablas del dataset `lapape`, como
  `DefinicionTabla` (nombre, columnas, partición y clustering).
  Independiente del proyecto de GCP; no requiere credenciales para
  importarse.
- **`crear_dataset.py`** — script idempotente que crea el dataset y las
  tablas si no existen. Seguro de correr las veces que haga falta.

## Ejecutar `crear_dataset.py`

Ya se corrió contra `mi-proyecto-gcp` el 2026-09-01: el dataset
`lapape` y sus seis tablas existen. #1
(revocar la llave expuesta en GCP IAM y emitir una nueva) y
#2 (purgar el historial
de git y forzar el push) están resueltos.

Para correrlo en otra máquina o proyecto: copia `backend/.env.example` a
`backend/.env`, llena `GOOGLE_APPLICATION_CREDENTIALS` (o
`GCP_SERVICE_ACCOUNT_JSON`) con la llave, y corre:

```bash
cd backend
python -m esquema.crear_dataset
```

Es idempotente: si el dataset y las tablas ya existen, no cambia nada.

> **#26** — la tabla `venta` ganó tres columnas `NULLABLE`
> (`motivo_cancelacion STRING`, `cancelada_por STRING`,
> `cancelada_en TIMESTAMP`) para la auditoría de cancelaciones. Ya se
> aplicaron a `mi-proyecto-gcp.lapape.venta` el 2026-09-01 con:
>
> ```sql
> ALTER TABLE `lapape.venta`
>   ADD COLUMN IF NOT EXISTS motivo_cancelacion STRING,
>   ADD COLUMN IF NOT EXISTS cancelada_por STRING,
>   ADD COLUMN IF NOT EXISTS cancelada_en TIMESTAMP;
> ```
>
> Las filas anteriores quedan en `NULL`. `crear_dataset.py` ya las incluye
> para instalaciones nuevas.

## Migrar el catálogo legado (#9)

Una vez creado el dataset, `esquema/migrar_catalogo.py` copia
`nuevas_tablas.catalogos` a `lapape.producto` y convierte la columna
`cantidad` del legado en movimientos `inventario_inicial` (el stock ya no
es una columna). Ya se corrió el 2026-09-01. No es idempotente —
aborta si `lapape.producto` ya tiene filas salvo `--forzar`; tiene
`--dry-run`.

```bash
cd backend
python -m esquema.migrar_catalogo --dry-run
```

## Decisiones de diseño

**Solo se registra la venta.** `venta` y `cierre` son las únicas fuentes
de verdad; día/semana/mes/año son consultas agregadas sobre ellas, nunca
tablas con totales propios que puedan desincronizarse.

**`venta` es una sola fila con líneas anidadas.** `lineas` es un
`REPEATED RECORD`: la venta completa (y todas sus líneas) se escribe de
una vez, sin joins. `producto_id` va en `NULL` en la captura rápida por
categoría y se llena al vender detallado — la migración a venta detallada
(#21) no requiere migrar datos, solo empezar a llenar ese campo.

**El stock no es una columna.** Es `SUM(cantidad)` de
`movimiento_inventario` agrupado por producto, materializado en una vista
(#31). Vender inserta un movimiento, nunca actualiza `producto`. Evita
por completo las cuotas de DML de BigQuery en el camino caliente.

**Todo append-only.** `venta`, `movimiento_inventario` y `cierre` solo
reciben inserts. Cancelaciones (#26) y correcciones de cierres cerrados
(#54) son filas nuevas que revierten, nunca `UPDATE`/`DELETE`. Solo
`producto` y `servicio` admiten `UPDATE` (precio, nombre), y son de baja
frecuencia — caben sin problema en la cuota de DML.

**El precio se congela en la línea** (`precio_unitario`,
`costo_unitario`). Los reportes nunca deben releer el precio actual del
catálogo, o subir precios reescribiría ventas pasadas.

**Recargas** guardan `subtotal` (el monto transferido) y
`monto_comision` (la ganancia real) por separado — ver #24.

**BigQuery no aplica restricciones.** PK, FK y unicidad son
responsabilidad del código (#7, #11), no de la base. En particular:
`usuario.nombre`, `producto.codigo_barras` (si no es nulo) y
(`cierre.tipo`, `cierre.fecha_inicio`) deben validarse como únicos antes
de insertar.

**Partición y clustering**

| Tabla | Partición | Clustering |
|---|---|---|
| `venta` | día, por `fecha_hora` | `estado`, `metodo_pago` |
| `movimiento_inventario` | día, por `fecha` | `producto_id`, `tipo` |
| `cierre` | día, por `fecha_inicio` | — |

> Corrección sobre el issue original: ahí se proponía
> `CLUSTER BY categoria` en `venta`. No es posible — `categoria` vive
> dentro de `lineas`, que es `REPEATED`, y BigQuery solo permite
> clusterizar por columnas de nivel superior. Se sustituyó por `estado` y
> `metodo_pago`, que sí sirven para el camino caliente real (separar
> ventas activas de canceladas, agrupar por método de pago en el corte
> de caja).

## Deliberadamente fuera de este esquema

`proveedor` y `compra` — llegan con #28, cuando se implementen las
entradas de mercancía. No hacían falta para v0.1 y agregarlas ahora
habría sido alcance de más.
