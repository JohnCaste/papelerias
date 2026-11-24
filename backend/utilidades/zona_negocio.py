"""
Zona horaria del negocio: la unica autoridad sobre "que dia es hoy" y
"a que dia pertenece esta venta".

Existe porque el journal local (#14) guardaba cada venta en el archivo
del dia UTC (`fecha_hora.date()` sobre un datetime en UTC) mientras el
resto del sistema preguntaba por el dia LOCAL (`date.today()`). Con
UTC-6 eso corre la frontera del dia a las 18:00 hora local: toda venta
capturada de las 6pm en adelante caia en el archivo del dia SIGUIENTE y
aparecia el dia siguiente como "ventas de hoy" (y no entraba en el
cierre de su propio dia). BigQuery nunca tuvo el problema -- ahi las
agregaciones ya cortan con `DATE(fecha_hora, 'America/Mexico_City')`
(ver acceso_datos/repositorios/agregaciones.py).

Mexico dejo el horario de verano en 2022: `America/Mexico_City` es
UTC-6 fijo desde entonces. Se usa un offset fijo -- y no `zoneinfo` --
para no depender de una base de zonas horarias, que en Windows no
siempre esta instalada (mismo criterio que ya seguian
reportes/dashboard.py y ventas/resumen_diario.py, que ahora importan
de aqui).
"""

import datetime

ZONA_NEGOCIO = datetime.timezone(datetime.timedelta(hours=-6))

# Hora a partir de la cual el dia se cierra solo (#50). Vive aqui para
# que el programador de cierre, el calculo de `provisional` (#54) y la
# pantalla compartan una sola fuente.
HORA_CIERRE = datetime.time(21, 0)


def ahora() -> datetime.datetime:
    """El instante actual expresado en hora del negocio (aware)."""
    return datetime.datetime.now(datetime.timezone.utc).astimezone(ZONA_NEGOCIO)


def hoy() -> datetime.date:
    """
    La fecha civil del negocio. Reemplaza a `datetime.date.today()`, que
    depende de como este configurado el reloj de la PC.
    """
    return ahora().date()


def a_hora_negocio(momento) -> datetime.datetime:
    """
    Normaliza a hora del negocio. Acepta un datetime (aware o naive) o
    su texto ISO -- el journal releido de disco entrega texto. Un naive
    se interpreta como UTC: asi lo escriben los modelos (`fecha_hora` y
    `creado_en` se generan con `datetime.now(timezone.utc)`).
    """
    dt = (
        datetime.datetime.fromisoformat(momento)
        if isinstance(momento, str)
        else momento
    )
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=datetime.timezone.utc)
    return dt.astimezone(ZONA_NEGOCIO)


def fecha_de(momento) -> datetime.date:
    """A que dia del negocio pertenece ese instante."""
    return a_hora_negocio(momento).date()


def reloj(momento=None) -> datetime.datetime:
    """
    Lectura de RELOJ DE PARED del negocio, para comparar contra una hora
    del dia (la hora de cierre). Se distingue de `a_hora_negocio` en como
    trata un naive: aqui un naive ya viene expresado en hora del negocio
    (asi lo escribe quien dice "a las 21:01"), mientras que alla un naive
    es un instante guardado en UTC. Un aware se convierte igual en ambas.
    """
    if momento is None:
        return ahora()
    dt = (
        datetime.datetime.fromisoformat(momento)
        if isinstance(momento, str)
        else momento
    )
    if dt.tzinfo is None:
        return dt.replace(tzinfo=ZONA_NEGOCIO)
    return dt.astimezone(ZONA_NEGOCIO)


def antes_de_hora_cierre(momento=None) -> bool:
    """True si en hora del negocio todavia no se cruza la hora de cierre."""
    return reloj(momento).time() < HORA_CIERRE
