"""
Reconstruye el journal local de compras de trabajadores
(datos_locales/compras/compras.jsonl) a partir de BigQuery.

Para cuando la PC del negocio se cambia o se le dana el disco: el journal
es la fuente de verdad de la pantalla de Compras, y BigQuery
(compra_trabajador / abono_compra) es su respaldo.

Reglas:
  - Si el journal actual tiene eventos SIN subir, no hace nada: esos
    eventos solo existen en esta PC y se perderian.
  - Si existe un journal (ya todo subido), pide confirmacion y lo guarda
    como compras.jsonl.respaldo-<fecha> antes de escribir el nuevo.

Uso:
    cd backend
    python -m almacen_local.reconstruir_compras
    python -m almacen_local.reconstruir_compras --si    (sin preguntar)
"""

import argparse
import datetime
import sys

from acceso_datos.consultas import ejecutar_query
from almacen_local import compras as journal_compras
from esquema.tablas import DATASET
from utilidades import sucursal


class ReconstruccionNoPermitida(RuntimeError):
    pass


def _texto_fecha(valor):
    if isinstance(valor, (datetime.datetime, datetime.date)):
        return valor.isoformat()
    return valor


def _leer_bigquery(consultar=ejecutar_query) -> list:
    compras = consultar(f"SELECT * FROM `{DATASET}.compra_trabajador`")
    abonos = consultar(f"SELECT * FROM `{DATASET}.abono_compra`")

    eventos = []
    for fila in compras:
        eventos.append({
            "evento": "compra",
            **{k: _texto_fecha(v) for k, v in fila.items()},
            "precio": str(fila["precio"]),
            "cantidad": int(fila["cantidad"]),
        })
    for fila in abonos:
        eventos.append({
            "evento": "abono",
            **{k: _texto_fecha(v) for k, v in fila.items()},
            "monto": str(fila["monto"]),
        })
    # Mismo orden en que se escribieron. Un abono nunca es anterior a su
    # compra, asi que el orden por generado_en conserva "ultima linea gana".
    eventos.sort(key=lambda e: e["generado_en"])
    return eventos


def reconstruir(carpeta=None, consultar=ejecutar_query, confirmar=lambda: True) -> int:
    """Devuelve el numero de eventos escritos. Lanza ReconstruccionNoPermitida."""
    archivo = journal_compras.ruta_archivo(carpeta)
    if archivo.exists():
        pendientes = journal_compras.leer_pendientes(carpeta)
        if pendientes:
            raise ReconstruccionNoPermitida(
                f"El journal de compras tiene {len(pendientes)} cambios sin subir a "
                "BigQuery. Conecta la PC a internet, espera a que se suban "
                "(la pantalla de Compras deja de mostrar 'pendientes') y vuelve a intentar."
            )
        if not confirmar():
            raise ReconstruccionNoPermitida("Cancelado: no se modifico nada.")

    eventos = _leer_bigquery(consultar)

    with journal_compras.lock:
        if archivo.exists():
            sello = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
            archivo.rename(archivo.with_name(f"{archivo.name}.respaldo-{sello}"))
        for evento in eventos:
            journal_compras.escribir_confirmado(evento, carpeta)
    return len(eventos)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--si", action="store_true", help="No pedir confirmacion")
    args = parser.parse_args(argv)

    if not sucursal.confirmar_destino("Reconstruir el journal de compras desde BigQuery", si=args.si):
        print("Cancelado.")
        return 1

    def confirmar():
        if args.si:
            return True
        respuesta = input("Ya existe un journal de compras. Reemplazarlo (se guarda respaldo)? (s/N): ")
        return respuesta.strip().lower() in ("s", "si", "sí")

    try:
        total = reconstruir(confirmar=confirmar)
    except ReconstruccionNoPermitida as error:
        print(error)
        return 1
    print(f"Listo: {total} eventos escritos en {journal_compras.ruta_archivo()}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
