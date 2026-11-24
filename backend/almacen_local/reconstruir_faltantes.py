"""
Reconstruye el journal local de la lista de faltantes
(datos_locales/faltantes/faltantes.jsonl) a partir de BigQuery.

Para cuando la PC del negocio se cambia o se le dana el disco: el journal
es la fuente de verdad de la pantalla de Faltantes, y BigQuery (`faltante`)
es su respaldo.

Reglas:
  - Si el journal actual tiene eventos SIN subir, no hace nada: esos
    eventos solo existen en esta PC y se perderian.
  - Si existe un journal (ya todo subido), pide confirmacion y lo guarda
    como faltantes.jsonl.respaldo-<fecha> antes de escribir el nuevo.

Uso:
    cd backend
    python -m almacen_local.reconstruir_faltantes
    python -m almacen_local.reconstruir_faltantes --si    (sin preguntar)
"""

import argparse
import datetime
import sys

from acceso_datos.consultas import ejecutar_query
from almacen_local import faltantes as journal_faltantes
from esquema.tablas import DATASET
from utilidades import sucursal


class ReconstruccionNoPermitida(RuntimeError):
    pass


def _texto_fecha(valor):
    if isinstance(valor, (datetime.datetime, datetime.date)):
        return valor.isoformat()
    return valor


def _leer_bigquery(consultar=ejecutar_query) -> list:
    filas = consultar(f"SELECT * FROM `{DATASET}.faltante`")
    eventos = []
    for fila in filas:
        evento = {"evento": "faltante", **{k: _texto_fecha(v) for k, v in fila.items()}}
        if evento.get("cantidad") is not None:
            evento["cantidad"] = int(evento["cantidad"])
        eventos.append(evento)
    # Mismo orden en que se escribieron: conserva "ultima linea gana".
    eventos.sort(key=lambda e: e["generado_en"])
    return eventos


def reconstruir(carpeta=None, consultar=ejecutar_query, confirmar=lambda: True) -> int:
    """Devuelve el numero de eventos escritos. Lanza ReconstruccionNoPermitida."""
    archivo = journal_faltantes.ruta_archivo(carpeta)
    if archivo.exists():
        pendientes = journal_faltantes.leer_pendientes(carpeta)
        if pendientes:
            raise ReconstruccionNoPermitida(
                f"El journal de faltantes tiene {len(pendientes)} cambios sin subir a "
                "BigQuery. Conecta la PC a internet, espera a que se suban "
                "(la pantalla de Faltantes deja de mostrar 'sin subir') y vuelve a intentar."
            )
        if not confirmar():
            raise ReconstruccionNoPermitida("Cancelado: no se modifico nada.")

    eventos = _leer_bigquery(consultar)

    with journal_faltantes.lock:
        if archivo.exists():
            sello = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
            archivo.rename(archivo.with_name(f"{archivo.name}.respaldo-{sello}"))
        for evento in eventos:
            journal_faltantes.escribir_confirmado(evento, carpeta)
    return len(eventos)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--si", action="store_true", help="No pedir confirmacion")
    args = parser.parse_args(argv)

    if not sucursal.confirmar_destino("Reconstruir el journal de faltantes desde BigQuery", si=args.si):
        print("Cancelado.")
        return 1

    def confirmar():
        if args.si:
            return True
        respuesta = input("Ya existe un journal de faltantes. Reemplazarlo (se guarda respaldo)? (s/N): ")
        return respuesta.strip().lower() in ("s", "si", "sí")

    try:
        total = reconstruir(confirmar=confirmar)
    except ReconstruccionNoPermitida as error:
        print(error)
        return 1
    print(f"Listo: {total} eventos escritos en {journal_faltantes.ruta_archivo()}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
