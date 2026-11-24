"""
Definicion del esquema de datos sobre BigQuery. Ver issue #8.

Principios de diseno (no repetir en cada tabla, quedan aqui una vez):

  - Solo se registra la venta. Dia/semana/mes/anio son consultas agregadas
    sobre `venta` y `cierre`, nunca tablas propias que dupliquen el total.

  - Todo el camino caliente es append-only (venta, movimiento_inventario,
    cierre). BigQuery cobra en cuotas de DML por UPDATE/DELETE y es lento
    para eso; insertar siempre evita el problema de raiz.

  - El stock NO es una columna. Es la suma de `movimiento_inventario` por
    producto. Vender no actualiza `producto`, inserta un movimiento.

  - BigQuery declara PK/FK pero no las hace cumplir: son informativas para
    quien lea el esquema, no una garantia. La unicidad y la integridad
    referencial se validan en el codigo (ver #7, #11), no en la base.

  - El precio se congela en cada linea de venta (`precio_unitario`). Los
    reportes nunca deben volver a leer el precio del catalogo.
"""

from dataclasses import dataclass, field

from google.cloud import bigquery

from utilidades import sucursal


# Dataset de ESTA sucursal, desde BQ_DATASET en backend\.env (ver
# utilidades/sucursal.py). En produccion, si falta, truena aqui mismo --
# antes de que exista la app o cualquier hilo que escriba a BigQuery.
DATASET = sucursal.resolver_dataset()

# El dataset legado ("nuevas_tablas") se conserva sin tocar. #9 (catalogo)
# y #10 (ventas historicas de `cuentas` -> `venta` con origen='migracion')
# ya se migraron y validaron el 2026-09-01. El legado queda solo como
# respaldo hasta que #34 reescriba los reportes contra el esquema nuevo.


@dataclass
class DefinicionTabla:
    """Definicion de una tabla independiente del proyecto de GCP.

    crear_dataset.py arma el bigquery.Table real (que si necesita el
    project id) a partir de esto, ya con las credenciales resueltas.
    """

    nombre: str
    schema: list
    particion_por: str | None = None
    cluster_por: list = field(default_factory=list)


# --------------------------------------------------------------- usuario
TABLA_USUARIO = DefinicionTabla(
    nombre="usuario",
    schema=[
        bigquery.SchemaField("id", "STRING", mode="REQUIRED"),
        bigquery.SchemaField("nombre", "STRING", mode="REQUIRED"),
        bigquery.SchemaField("password_hash", "STRING", mode="REQUIRED"),
        # 'dueno' | 'empleado' -- ver #46
        bigquery.SchemaField("rol", "STRING", mode="REQUIRED"),
        bigquery.SchemaField("activo", "BOOL", mode="REQUIRED"),
        bigquery.SchemaField("creado_en", "TIMESTAMP", mode="REQUIRED"),
    ],
)
# Sin stock ni precio historico: password_hash se llena en #3 (bcrypt).
# 'nombre' deberia ser unico -- se valida en el codigo (BigQuery no lo hace).


# -------------------------------------------------------- usuario_foto
# Foto de perfil de cada usuario del POS. Tabla aparte y en el dataset
# nuevo a proposito: la tabla de credenciales (`nuevas_tablas.login`) es
# legada y el proyecto evita hacerle ALTER (ver autentificacion/
# credenciales.py). `usuario_id` es el id de esa tabla legada. Una fila
# por usuario -- la subida hace upsert (UPDATE si ya hay foto, INSERT si
# no); el volumen es de unos pocos usuarios, no es camino caliente.
TABLA_USUARIO_FOTO = DefinicionTabla(
    nombre="usuario_foto",
    schema=[
        bigquery.SchemaField("usuario_id", "STRING", mode="REQUIRED"),
        bigquery.SchemaField("foto_url", "STRING", mode="REQUIRED"),
        bigquery.SchemaField("actualizado_en", "TIMESTAMP", mode="REQUIRED"),
    ],
)


# --------------------------------------------------------- usuario_rol
# Rol de cada usuario del POS. Igual que usuario_foto: tabla aparte en el
# dataset nuevo para no tocar la tabla legada de credenciales.
# `usuario_id` es el id de `nuevas_tablas.login`. Un usuario sin fila aqui
# se trata como 'empleado' (el minimo). 'dueno' ve Ventas y Corte.
TABLA_USUARIO_ROL = DefinicionTabla(
    nombre="usuario_rol",
    schema=[
        bigquery.SchemaField("usuario_id", "STRING", mode="REQUIRED"),
        # 'dueno' | 'empleado'
        bigquery.SchemaField("rol", "STRING", mode="REQUIRED"),
        bigquery.SchemaField("actualizado_en", "TIMESTAMP", mode="REQUIRED"),
    ],
)


# -------------------------------------------------------------- producto
TABLA_PRODUCTO = DefinicionTabla(
    nombre="producto",
    schema=[
        bigquery.SchemaField("id", "STRING", mode="REQUIRED"),
        # Ninguno de los dos es obligatorio: no todo trae codigo de fabrica.
        bigquery.SchemaField("codigo_barras", "STRING", mode="NULLABLE"),
        bigquery.SchemaField("codigo_interno", "STRING", mode="NULLABLE"),
        bigquery.SchemaField("nombre", "STRING", mode="REQUIRED"),
        bigquery.SchemaField("categoria", "STRING", mode="REQUIRED"),
        bigquery.SchemaField("marca", "STRING", mode="NULLABLE"),
        bigquery.SchemaField("descripcion", "STRING", mode="NULLABLE"),
        bigquery.SchemaField("imagen", "STRING", mode="NULLABLE"),
        bigquery.SchemaField("precio", "NUMERIC", mode="REQUIRED"),
        # Se alimenta desde las compras (#28); nulo hasta la primera compra.
        bigquery.SchemaField("costo", "NUMERIC", mode="NULLABLE"),
        bigquery.SchemaField("stock_minimo", "NUMERIC", mode="NULLABLE"),
        bigquery.SchemaField("activo", "BOOL", mode="REQUIRED"),
        bigquery.SchemaField("creado_en", "TIMESTAMP", mode="REQUIRED"),
        bigquery.SchemaField("actualizado_en", "TIMESTAMP", mode="REQUIRED"),
    ],
)
# NOTA: no hay columna 'stock'. El stock actual es
#   SELECT producto_id, SUM(cantidad) FROM movimiento_inventario GROUP BY producto_id
# materializado en una vista (ver #31). codigo_barras deberia ser unico
# cuando no es nulo -- se valida en el codigo.


# ------------------------------------------------------------- categoria
# Lista canonica y fija de categorias de producto. Antes la lista se
# derivaba con SELECT DISTINCT sobre `producto` (typos y duplicados
# entraban solos); ahora el formulario de alta/edicion solo ofrece estas.
# 'orden' conserva el orden con el que se sembro la lista (ver
# esquema/sembrar_categorias.py); el selector la muestra en ese orden.
TABLA_CATEGORIA = DefinicionTabla(
    nombre="categoria",
    schema=[
        # id = el propio nombre (unico, estable, legible). No hay UUID:
        # la tabla es un catalogo fijo administrado por script, no por UI.
        bigquery.SchemaField("id", "STRING", mode="REQUIRED"),
        bigquery.SchemaField("nombre", "STRING", mode="REQUIRED"),
        bigquery.SchemaField("orden", "INT64", mode="REQUIRED"),
        bigquery.SchemaField("activo", "BOOL", mode="REQUIRED"),
        bigquery.SchemaField("creado_en", "TIMESTAMP", mode="REQUIRED"),
    ],
)


# -------------------------------------------------------------- servicio
TABLA_SERVICIO = DefinicionTabla(
    nombre="servicio",
    schema=[
        bigquery.SchemaField("id", "STRING", mode="REQUIRED"),
        bigquery.SchemaField("nombre", "STRING", mode="REQUIRED"),
        # 'hoja' | 'documento' | 'servicio' -- copia B/N, color, impresion,
        # escaneo, descarga de documento web, engargolado (#22).
        bigquery.SchemaField("unidad", "STRING", mode="REQUIRED"),
        bigquery.SchemaField("precio", "NUMERIC", mode="REQUIRED"),
        bigquery.SchemaField("activo", "BOOL", mode="REQUIRED"),
        bigquery.SchemaField("creado_en", "TIMESTAMP", mode="REQUIRED"),
        bigquery.SchemaField("actualizado_en", "TIMESTAMP", mode="REQUIRED"),
    ],
)
# Sin stock: los servicios no tienen existencia, solo precio.


# ---------------------------------------------- venta_linea (tipo anidado)
# No es una tabla: es la definicion de cada elemento del arreglo `lineas`
# dentro de `venta`. Una venta y sus lineas se escriben como una sola fila.
CAMPOS_VENTA_LINEA = [
    # 'categoria'   -- captura rapida por categoria, sin producto (#22)
    # 'producto'    -- venta detallada contra el catalogo (#21)
    # 'servicio'    -- copias/impresion (#22 actualizacion)
    # 'recarga'     -- monto y comision por separado (#24)
    bigquery.SchemaField("tipo", "STRING", mode="REQUIRED"),
    # Presente solo si tipo = 'categoria'. Sirve tanto para el reporte por
    # categoria como para saber que linea aun no esta detallada.
    bigquery.SchemaField("categoria", "STRING", mode="NULLABLE"),
    # NULL en captura rapida, lleno al vender detallado -- ver regla de
    # migracion progresiva en #21/#22.
    bigquery.SchemaField("producto_id", "STRING", mode="NULLABLE"),
    bigquery.SchemaField("servicio_id", "STRING", mode="NULLABLE"),
    bigquery.SchemaField("descripcion", "STRING", mode="NULLABLE"),
    bigquery.SchemaField("cantidad", "NUMERIC", mode="REQUIRED"),
    # Congelado al momento de la venta. No se vuelve a leer del catalogo.
    bigquery.SchemaField("precio_unitario", "NUMERIC", mode="REQUIRED"),
    # Copiado de producto.costo al momento de vender, para margen (#32).
    bigquery.SchemaField("costo_unitario", "NUMERIC", mode="NULLABLE"),
    bigquery.SchemaField("subtotal", "NUMERIC", mode="REQUIRED"),
    # Solo para tipo = 'recarga'. El monto de la recarga va en 'subtotal';
    # la ganancia real es esta comision, no el monto (#24).
    bigquery.SchemaField("monto_comision", "NUMERIC", mode="NULLABLE"),
]


# ------------------------------------------------------------------ venta
TABLA_VENTA = DefinicionTabla(
    nombre="venta",
    schema=[
        bigquery.SchemaField("id", "STRING", mode="REQUIRED"),
        bigquery.SchemaField("fecha_hora", "TIMESTAMP", mode="REQUIRED"),
        bigquery.SchemaField("total", "NUMERIC", mode="REQUIRED"),
        # 'efectivo' | 'transferencia' | 'tarjeta' -- ver #25
        bigquery.SchemaField("metodo_pago", "STRING", mode="REQUIRED"),
        bigquery.SchemaField("usuario_id", "STRING", mode="REQUIRED"),
        # Nombre de quien capturo la venta ("quien vendio"). NULLABLE:
        # las filas migradas (#10) y las de ajuste no lo llevan. Se agrego
        # despues de crear la tabla -- ver esquema/migrar_vendedor.py.
        bigquery.SchemaField("vendedor", "STRING", mode="NULLABLE"),
        # 'activa' | 'cancelada' | 'devolucion_parcial' | 'editada' |
        # 'editada_reversa' -- ni cancelar ni editar borran o modifican la
        # fila original: insertan filas de ajuste que la referencian por
        # `venta_original_id` y llevan su propio `estado` (cancelacion: #26;
        # edicion de monto: reversion 'editada_reversa' + recaptura 'editada').
        # Que una venta este cancelada o editada se DERIVA al leer (existe una
        # reversion total o una recaptura que la apunta), no se guarda en la
        # fila original.
        bigquery.SchemaField("estado", "STRING", mode="REQUIRED"),
        bigquery.SchemaField("detallada", "BOOL", mode="REQUIRED"),
        # 'pos' | 'migracion' -- distingue lo capturado en vivo de lo
        # migrado desde 'cuentas' (#10).
        bigquery.SchemaField("origen", "STRING", mode="REQUIRED"),
        # Venta registrada con fecha pasada sobre un dia ya cerrado (#54).
        bigquery.SchemaField("extemporanea", "BOOL", mode="REQUIRED"),
        bigquery.SchemaField("motivo_extemporanea", "STRING", mode="NULLABLE"),
        # Si esta fila es una reversion, apunta a la venta que cancela.
        bigquery.SchemaField("venta_original_id", "STRING", mode="NULLABLE"),
        # Auditoria de la cancelacion (#26) -- solo en la fila de reversion,
        # NULL en una venta normal.
        bigquery.SchemaField("motivo_cancelacion", "STRING", mode="NULLABLE"),
        bigquery.SchemaField("cancelada_por", "STRING", mode="NULLABLE"),
        bigquery.SchemaField("cancelada_en", "TIMESTAMP", mode="NULLABLE"),
        bigquery.SchemaField("creado_en", "TIMESTAMP", mode="REQUIRED"),
        bigquery.SchemaField(
            "lineas", "RECORD", mode="REPEATED", fields=CAMPOS_VENTA_LINEA
        ),
    ],
    particion_por="fecha_hora",
    # CORRECCION respecto al issue #8 original: ahi se propuso
    # "CLUSTER BY categoria". No es posible -- categoria vive dentro de
    # `lineas`, que es REPEATED, y BigQuery solo permite clusterizar por
    # columnas de nivel superior. Se clusteriza por lo que si sirve para
    # filtrar el camino caliente: separar canceladas de activas y agrupar
    # por metodo de pago (reportes por metodo de pago, #34).
    cluster_por=["estado", "metodo_pago"],
)


# ------------------------------------------------- movimiento_inventario
TABLA_MOVIMIENTO_INVENTARIO = DefinicionTabla(
    nombre="movimiento_inventario",
    schema=[
        bigquery.SchemaField("id", "STRING", mode="REQUIRED"),
        bigquery.SchemaField("producto_id", "STRING", mode="REQUIRED"),
        # 'compra' | 'venta' | 'ajuste' | 'merma' | 'cancelacion'
        # | 'inventario_inicial' (usado solo por la migracion #9)
        bigquery.SchemaField("tipo", "STRING", mode="REQUIRED"),
        # Con signo: positivo entra, negativo sale. El stock es la suma.
        bigquery.SchemaField("cantidad", "NUMERIC", mode="REQUIRED"),
        bigquery.SchemaField("costo_unitario", "NUMERIC", mode="NULLABLE"),
        # id de la venta, compra o ajuste que origino el movimiento.
        bigquery.SchemaField("referencia_id", "STRING", mode="NULLABLE"),
        bigquery.SchemaField("fecha", "TIMESTAMP", mode="REQUIRED"),
        bigquery.SchemaField("usuario_id", "STRING", mode="REQUIRED"),
    ],
    particion_por="fecha",
    cluster_por=["producto_id", "tipo"],
)


# ----------------------------------------------------------------- cierre
CAMPOS_DESGLOSE = [
    bigquery.SchemaField("clave", "STRING", mode="REQUIRED"),
    bigquery.SchemaField("monto", "NUMERIC", mode="REQUIRED"),
]

TABLA_CIERRE = DefinicionTabla(
    nombre="cierre",
    schema=[
        bigquery.SchemaField("id", "STRING", mode="REQUIRED"),
        # 'dia' | 'semana' | 'mes' | 'anio' -- ver #50, #51, #52
        bigquery.SchemaField("tipo", "STRING", mode="REQUIRED"),
        bigquery.SchemaField("fecha_inicio", "DATE", mode="REQUIRED"),
        bigquery.SchemaField("fecha_fin", "DATE", mode="REQUIRED"),
        # Debe coincidir siempre con SUM(total) de `venta` en el rango.
        # Si no coincide, es una alarma -- nunca se corrige en silencio.
        bigquery.SchemaField("total", "NUMERIC", mode="REQUIRED"),
        bigquery.SchemaField("num_ventas", "INT64", mode="REQUIRED"),
        bigquery.SchemaField(
            "desglose_categoria", "RECORD", mode="REPEATED", fields=CAMPOS_DESGLOSE
        ),
        bigquery.SchemaField(
            "desglose_metodo_pago", "RECORD", mode="REPEATED", fields=CAMPOS_DESGLOSE
        ),
        bigquery.SchemaField("generado_en", "TIMESTAMP", mode="REQUIRED"),
        # 'automatico' | 'perezoso' | 'manual' -- ver #50
        bigquery.SchemaField("generado_por", "STRING", mode="REQUIRED"),
        bigquery.SchemaField("pdf_ruta", "STRING", mode="NULLABLE"),
        # 'cerrado' | 'corregido' -- una correccion (#54) inserta un nuevo
        # cierre marcado 'corregido' y conserva el original para trazar
        # el historial, nunca lo sobreescribe.
        bigquery.SchemaField("estado", "STRING", mode="REQUIRED"),
    ],
    particion_por="fecha_inicio",
)
# Unicidad esperada sobre (tipo, fecha_inicio) -- BigQuery no la aplica,
# el codigo que genera cierres (#50-52) debe verificar antes de insertar
# para mantener la idempotencia.


# -------------------------------------------------------------- gasto_dia
# Gasto manual del dia, descontado de 'papeleria' en el modal por dia de
# la pantalla de Ventas (handoff, columna "Gastos"). Append-only, como el
# resto del esquema: cada guardado agrega una fila nueva con el monto
# vigente; el repositorio lee la ULTIMA por fecha (ver
# acceso_datos/repositorios/gasto_dia.py). Deliberadamente fuera de
# `venta`: es un egreso, no una venta, y mezclarlo ahi corromperia
# `total`/`num_ventas` en los reportes agregados (#34).
TABLA_GASTO_DIA = DefinicionTabla(
    nombre="gasto_dia",
    schema=[
        bigquery.SchemaField("id", "STRING", mode="REQUIRED"),
        bigquery.SchemaField("fecha", "DATE", mode="REQUIRED"),
        bigquery.SchemaField("monto", "NUMERIC", mode="REQUIRED"),
        bigquery.SchemaField("usuario_id", "STRING", mode="REQUIRED"),
        bigquery.SchemaField("generado_en", "TIMESTAMP", mode="REQUIRED"),
    ],
    particion_por="fecha",
)


# ------------------------------------------------- compras de trabajadores
# Lo que los trabajadores le compran a la duena (y lo que le van abonando).
# Solo en la sucursal original (ver compras/acceso.py). La fuente de verdad
# es el journal local datos_locales/compras/compras.jsonl (funciona sin
# internet, como las ventas); estas tablas son su respaldo en BigQuery y la
# base para reconstruirlo (almacen_local/reconstruir_compras.py).
#
# Versionadas por `compra_id` / `abono_id`: editar o eliminar agrega una
# fila nueva con la instantanea completa. `id` es el del EVENTO (unico por
# fila), el que viaja como row_id para que los reintentos no dupliquen.
# Deliberadamente fuera de `venta`: no es una venta ni toca inventario.
TABLA_COMPRA_TRABAJADOR = DefinicionTabla(
    nombre="compra_trabajador",
    schema=[
        bigquery.SchemaField("id", "STRING", mode="REQUIRED"),
        bigquery.SchemaField("compra_id", "STRING", mode="REQUIRED"),
        bigquery.SchemaField("nombre", "STRING", mode="REQUIRED"),
        bigquery.SchemaField("producto", "STRING", mode="REQUIRED"),
        bigquery.SchemaField("cantidad", "INT64", mode="REQUIRED"),
        bigquery.SchemaField("precio", "NUMERIC", mode="REQUIRED"),
        bigquery.SchemaField("fecha", "DATE", mode="REQUIRED"),
        bigquery.SchemaField("eliminada", "BOOL", mode="REQUIRED"),
        bigquery.SchemaField("usuario_id", "STRING", mode="REQUIRED"),
        bigquery.SchemaField("registrado_por", "STRING", mode="NULLABLE"),
        bigquery.SchemaField("generado_en", "TIMESTAMP", mode="REQUIRED"),
    ],
)

TABLA_ABONO_COMPRA = DefinicionTabla(
    nombre="abono_compra",
    schema=[
        bigquery.SchemaField("id", "STRING", mode="REQUIRED"),
        bigquery.SchemaField("abono_id", "STRING", mode="REQUIRED"),
        bigquery.SchemaField("compra_id", "STRING", mode="REQUIRED"),
        bigquery.SchemaField("monto", "NUMERIC", mode="REQUIRED"),
        bigquery.SchemaField("fecha", "DATE", mode="REQUIRED"),
        bigquery.SchemaField("eliminado", "BOOL", mode="REQUIRED"),
        bigquery.SchemaField("usuario_id", "STRING", mode="REQUIRED"),
        bigquery.SchemaField("registrado_por", "STRING", mode="NULLABLE"),
        bigquery.SchemaField("generado_en", "TIMESTAMP", mode="REQUIRED"),
    ],
)


# ------------------------------------------------- lista de faltantes
# Productos que se acabaron y hay que comprar. En TODAS las sucursales (cada
# dataset lleva su propia lista). Fuente de verdad: el journal local
# datos_locales/faltantes/faltantes.jsonl (funciona sin internet); esta tabla
# es su respaldo y la base para reconstruirlo
# (almacen_local/reconstruir_faltantes.py).
#
# Versionada por `faltante_id`: cada operacion (alta, edicion, comprado,
# eliminar) agrega una fila con la instantanea completa. `id` es el del
# EVENTO, el que viaja como row_id. `producto_id` nulo = texto libre.
TABLA_FALTANTE = DefinicionTabla(
    nombre="faltante",
    schema=[
        bigquery.SchemaField("id", "STRING", mode="REQUIRED"),
        bigquery.SchemaField("faltante_id", "STRING", mode="REQUIRED"),
        bigquery.SchemaField("producto_id", "STRING", mode="NULLABLE"),
        bigquery.SchemaField("nombre", "STRING", mode="REQUIRED"),
        bigquery.SchemaField("cantidad", "INT64", mode="NULLABLE"),
        bigquery.SchemaField("nota", "STRING", mode="NULLABLE"),
        # 'pendiente' | 'comprado'
        bigquery.SchemaField("estado", "STRING", mode="REQUIRED"),
        bigquery.SchemaField("eliminado", "BOOL", mode="REQUIRED"),
        bigquery.SchemaField("usuario_id", "STRING", mode="REQUIRED"),
        bigquery.SchemaField("registrado_por", "STRING", mode="NULLABLE"),
        bigquery.SchemaField("creado_en", "TIMESTAMP", mode="REQUIRED"),
        bigquery.SchemaField("comprado_por", "STRING", mode="NULLABLE"),
        bigquery.SchemaField("comprado_en", "TIMESTAMP", mode="NULLABLE"),
        bigquery.SchemaField("modificado_por", "STRING", mode="NULLABLE"),
        bigquery.SchemaField("generado_en", "TIMESTAMP", mode="REQUIRED"),
    ],
)


TABLAS = [
    TABLA_USUARIO,
    TABLA_USUARIO_FOTO,
    TABLA_USUARIO_ROL,
    TABLA_PRODUCTO,
    TABLA_CATEGORIA,
    TABLA_SERVICIO,
    TABLA_VENTA,
    TABLA_MOVIMIENTO_INVENTARIO,
    TABLA_CIERRE,
    TABLA_GASTO_DIA,
    TABLA_COMPRA_TRABAJADOR,
    TABLA_ABONO_COMPRA,
    TABLA_FALTANTE,
]

# Deliberadamente fuera de este primer esquema: 'proveedor' y 'compra'
# (llegan con #28, cuando se implementen las entradas de mercancia).
