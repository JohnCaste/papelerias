"""
Repositorio de cierre (#50-#54). Append-only.

BigQuery no aplica la unicidad sobre (tipo, fecha_inicio) por si sola
(ver esquema/README.md) -- la idempotencia depende de que quien genera
el cierre llame `existe(...)` antes de `insertar(...)`.
"""

import datetime
import uuid

from acceso_datos.consultas import ejecutar_query, ejecutar_uno
from acceso_datos.escrituras import insertar_filas
from esquema.tablas import DATASET

TABLA = f"{DATASET}.cierre"


def existe(tipo: str, fecha_inicio):
    """
    True si ya hay un cierre vigente (no corregido) para ese periodo.
    Los generadores de cierre (#50-52) deben checar esto antes de
    insertar -- es lo que los vuelve idempotentes.
    """
    sql = f"""
        SELECT id FROM `{TABLA}`
        WHERE tipo = @tipo AND fecha_inicio = @fecha_inicio AND estado != 'corregido'
        LIMIT 1
    """
    fila = ejecutar_uno(
        sql, {"tipo": tipo, "fecha_inicio": fecha_inicio}, {"fecha_inicio": "DATE"}
    )
    return fila is not None


def obtener_vigente(tipo: str, fecha_inicio):
    sql = f"""
        SELECT * FROM `{TABLA}`
        WHERE tipo = @tipo AND fecha_inicio = @fecha_inicio
        ORDER BY generado_en DESC
        LIMIT 1
    """
    return ejecutar_uno(
        sql, {"tipo": tipo, "fecha_inicio": fecha_inicio}, {"fecha_inicio": "DATE"}
    )


def marcar_corregido(id_cierre: str):
    """
    Marca un acta como 'corregido' -- la reemplaza una regeneracion
    local (#54). `existe()` y las agregaciones filtran
    `estado != 'corregido'`, asi que la fila vieja deja de contar.

    Es DML (UPDATE), no streaming: corre raras veces (solo al regenerar)
    y BigQuery puede rechazarla mientras la fila siga en el streaming
    buffer (~90 min); el sincronizador reintenta en el siguiente ciclo y
    `obtener_vigente` (orden por generado_en DESC) ya devuelve la version
    nueva mientras tanto.
    """
    sql = f"UPDATE `{TABLA}` SET estado = 'corregido' WHERE id = @id"
    ejecutar_query(sql, {"id": id_cierre})


def insertar(datos: dict):
    """
    Quien llama es responsable de checar `existe(...)` antes. Este
    repositorio no lo hace por si solo: esconder esa verificacion detras
    de una llamada que parece simple ocultaria condiciones de carrera
    que el generador de cierres (#50-52) debe manejar con su propio
    criterio (por ejemplo, con un lock o una transaccion externa).
    """
    fila = {
        "id": str(uuid.uuid4()),
        # 'dia' | 'semana' | 'mes' | 'anio'
        "tipo": datos["tipo"],
        "fecha_inicio": datos["fecha_inicio"],
        "fecha_fin": datos["fecha_fin"],
        "total": float(datos["total"]),
        "num_ventas": int(datos["num_ventas"]),
        "desglose_categoria": datos.get("desglose_categoria", []),
        "desglose_metodo_pago": datos.get("desglose_metodo_pago", []),
        # Si ya venia con su propia marca de tiempo (por ejemplo, un
        # cierre generado localmente y sincronizado despues, #50), se
        # respeta -- 'generado_en' debe reflejar cuando se genero el
        # cierre, no cuando se sincronizo a BigQuery.
        "generado_en": datos.get("generado_en") or datetime.datetime.now(datetime.timezone.utc),
        # 'automatico' | 'perezoso' | 'manual' | 'regeneracion'
        "generado_por": datos["generado_por"],
        "pdf_ruta": datos.get("pdf_ruta"),
        # 'cerrado' | 'corregido'
        "estado": datos.get("estado", "cerrado"),
    }
    insertar_filas(TABLA, [fila])
    return fila
