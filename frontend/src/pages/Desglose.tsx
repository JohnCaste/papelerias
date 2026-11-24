import { useCallback, useEffect, useState } from "react";
import {
  Alert,
  Badge,
  Button,
  Card,
  Col,
  Form,
  Modal,
  Row,
  Table,
} from "react-bootstrap";
import {
  obtenerDesgloseDia,
  type DesgloseDia,
  type Desglose,
  type VentaResumen,
} from "../services/desglose";
import {
  cancelarVenta,
  editarVenta,
  obtenerVentasDelDia,
  type VentaDelDia,
} from "../services/ventas";
import { etiquetaCategoria } from "../categorias";

const pesos = (n: number) =>
  n.toLocaleString("es-MX", { style: "currency", currency: "MXN" });

// `etiqueta` traduce la clave guardada a texto legible. En el desglose por
// categoría el backend manda SIEMPRE la lista canónica completa, incluidas
// las que quedaron en cero: la fila en $0 es información (no se vendió
// nada de eso hoy), no un hueco que convenga esconder.
function TablaDesglose({
  titulo,
  filas,
  etiqueta = (clave: string) => clave,
}: {
  titulo: string;
  filas: Desglose[];
  etiqueta?: (clave: string) => string;
}) {
  return (
    <Card className="h-100">
      <Card.Header>{titulo}</Card.Header>
      <Card.Body className="p-0">
        {filas.length === 0 ? (
          <p className="text-muted p-3 mb-0">Sin datos</p>
        ) : (
          <Table striped size="sm" className="mb-0">
            <tbody>
              {filas.map((f) => (
                <tr key={f.clave}>
                  <td>{etiqueta(f.clave)}</td>
                  <td className="text-end">{pesos(f.monto)}</td>
                </tr>
              ))}
            </tbody>
          </Table>
        )}
      </Card.Body>
    </Card>
  );
}

function DesglosePagina() {
  const [data, setData] = useState<DesgloseDia | null>(null);
  const [error, setError] = useState("");
  // Líneas de cada venta del día (para la devolución parcial): el resumen
  // del desglose no las trae, se piden aparte a /api/ventas/dia.
  const [lineasPorVenta, setLineasPorVenta] = useState<
    Record<string, VentaDelDia["lineas"]>
  >({});
  const [aCancelar, setACancelar] = useState<VentaResumen | null>(null);
  const [aEditar, setAEditar] = useState<VentaResumen | null>(null);

  const cargar = useCallback(() => {
    setError("");
    obtenerDesgloseDia()
      .then((d) => {
        setData(d);
        return obtenerVentasDelDia(d.fecha).catch(() => null);
      })
      .then((ventas) => {
        if (!ventas) return;
        const mapa: Record<string, VentaDelDia["lineas"]> = {};
        for (const v of ventas.ventas) mapa[v.id] = v.lineas;
        setLineasPorVenta(mapa);
      })
      .catch(() => setError("No se pudo cargar el desglose del día"));
  }, []);

  useEffect(() => {
    cargar();
  }, [cargar]);

  if (error) {
    return (
      <div className="container mt-4">
        <Alert variant="danger">{error}</Alert>
      </div>
    );
  }
  if (!data) {
    return <div className="container mt-4">Cargando…</div>;
  }

  const comp = data.comparacion_semana_anterior;
  const compHuboDatos = comp.num_ventas > 0 || comp.total > 0;
  const { detalle } = data;

  return (
    <div className="container mt-4">
      <div className="d-flex align-items-center gap-3 mb-3">
        <h2 className="mb-0">Día {data.fecha}</h2>
        {data.estado_dia.cerrado ? (
          <Badge bg="secondary">
            Cerrado{" "}
            {data.estado_dia.cerrado_en
              ? `· ${data.estado_dia.cerrado_en.slice(11, 16)}`
              : ""}
          </Badge>
        ) : (
          <Badge bg="success">Abierto</Badge>
        )}
      </div>

      {data.dias_sin_cerrar.length > 0 && (
        <Alert variant="warning">
          Quedan días anteriores sin cerrar: {data.dias_sin_cerrar.join(", ")}
        </Alert>
      )}

      <Row className="g-3 mb-3">
        <Col xs={6} md={3}>
          <Card body>
            <div className="text-muted small">Total del día</div>
            <div className="fs-4">{pesos(data.total)}</div>
          </Card>
        </Col>
        <Col xs={6} md={3}>
          <Card body>
            <div className="text-muted small">Ventas</div>
            <div className="fs-4">{data.num_ventas}</div>
          </Card>
        </Col>
        <Col xs={6} md={3}>
          <Card body>
            <div className="text-muted small">Capturado con detalle</div>
            <div className="fs-4">{detalle.porcentaje}%</div>
            <div className="text-muted small">
              {pesos(detalle.monto_detallado)} de {pesos(detalle.monto_total)}
            </div>
          </Card>
        </Col>
        <Col xs={6} md={3}>
          <Card body>
            <div className="text-muted small">
              vs. {comp.fecha} (semana anterior)
            </div>
            {compHuboDatos ? (
              <>
                <div className="fs-4">
                  {comp.delta_total >= 0 ? "+" : ""}
                  {pesos(comp.delta_total)}
                </div>
                <div className="text-muted small">
                  {comp.delta_pct === null
                    ? "—"
                    : `${comp.delta_pct >= 0 ? "+" : ""}${comp.delta_pct}%`}{" "}
                  · {pesos(comp.total)}
                </div>
              </>
            ) : (
              <div className="text-muted">Sin datos</div>
            )}
          </Card>
        </Col>
      </Row>

      <Row className="g-3 mb-3">
        <Col md={6}>
          <TablaDesglose
            titulo="Por categoría"
            filas={data.desglose_categoria}
            etiqueta={etiquetaCategoria}
          />
        </Col>
        <Col md={6}>
          <TablaDesglose
            titulo="Por método de pago"
            filas={data.desglose_metodo_pago}
          />
        </Col>
      </Row>

      <Card>
        <Card.Header>Últimas ventas</Card.Header>
        <Card.Body className="p-0">
          {data.ultimas_ventas.length === 0 ? (
            <p className="text-muted p-3 mb-0">Sin ventas</p>
          ) : (
            <Table striped hover size="sm" className="mb-0">
              <thead>
                <tr>
                  <th>Hora</th>
                  <th className="text-end">Total</th>
                  <th>Método</th>
                  <th>Vendió</th>
                  <th>Detalle</th>
                  <th>Estado</th>
                  <th />
                </tr>
              </thead>
              <tbody>
                {data.ultimas_ventas.map((v) => {
                  const cancelada = v.estado === "cancelada";
                  const editada = v.estado === "editada";
                  return (
                    <tr
                      key={v.id}
                      className={cancelada ? "text-muted text-decoration-line-through" : undefined}
                    >
                      <td>{v.hora}</td>
                      <td className="text-end">{pesos(v.total)}</td>
                      <td>{v.metodo_pago}</td>
                      <td>{v.vendedor ?? "—"}</td>
                      <td>{v.detallada ? "sí" : "no"}</td>
                      <td className="text-decoration-none">
                        <Badge
                          bg={
                            cancelada
                              ? "danger"
                              : editada
                                ? "info"
                                : v.estado === "enviada"
                                  ? "success"
                                  : "warning"
                          }
                        >
                          {v.estado}
                        </Badge>
                      </td>
                      <td className="text-end text-decoration-none">
                        <div className="d-flex gap-2 justify-content-end">
                          {v.editable && (
                            <Button
                              size="sm"
                              variant="outline-info"
                              onClick={() => setAEditar(v)}
                            >
                              Editar
                            </Button>
                          )}
                          {v.cancelable && (
                            <Button
                              size="sm"
                              variant="outline-danger"
                              onClick={() => setACancelar(v)}
                            >
                              Cancelar
                            </Button>
                          )}
                        </div>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </Table>
          )}
        </Card.Body>
      </Card>

      <ModalCancelar
        venta={aCancelar}
        fecha={data.fecha}
        lineas={aCancelar ? lineasPorVenta[aCancelar.id] : undefined}
        onCerrar={() => setACancelar(null)}
        onCancelada={() => {
          setACancelar(null);
          cargar();
        }}
      />

      <ModalEditar
        venta={aEditar}
        fecha={data.fecha}
        onCerrar={() => setAEditar(null)}
        onEditada={() => {
          setAEditar(null);
          cargar();
        }}
      />
    </div>
  );
}

function ModalEditar({
  venta,
  fecha,
  onCerrar,
  onEditada,
}: {
  venta: VentaResumen | null;
  fecha: string;
  onCerrar: () => void;
  onEditada: () => void;
}) {
  const [monto, setMonto] = useState("");
  const [motivo, setMotivo] = useState("");
  const [enviando, setEnviando] = useState(false);
  const [error, setError] = useState("");

  // Al abrir el modal para otra venta, precargar el monto vigente y limpiar.
  useEffect(() => {
    setMonto(venta ? String(venta.total) : "");
    setMotivo("");
    setError("");
    setEnviando(false);
  }, [venta?.id, venta?.total]);

  if (!venta) return null;

  const montoNuevo = Number(monto);
  const montoValido = Number.isFinite(montoNuevo) && montoNuevo > 0;
  const cambia = montoValido && montoNuevo !== venta.total;
  const motivoValido = motivo.trim().length > 0;
  const puedeConfirmar = cambia && motivoValido && !enviando;

  const confirmar = () => {
    if (!puedeConfirmar) return;
    setEnviando(true);
    setError("");
    editarVenta(venta.id, montoNuevo, { fecha, motivo: motivo.trim() })
      .then(onEditada)
      .catch((e) => {
        setError(e instanceof Error ? e.message : "No se pudo editar la venta");
        setEnviando(false);
      });
  };

  return (
    <Modal show onHide={onCerrar} centered>
      <Modal.Header closeButton>
        <Modal.Title>Editar venta de {pesos(venta.total)}</Modal.Title>
      </Modal.Header>
      <Modal.Body>
        {error && <Alert variant="danger">{error}</Alert>}
        <p className="text-muted small">
          La venta no se borra: se registra la reversión del importe actual y una
          recaptura con el monto nuevo. El total del día sube o baja solo por la
          diferencia.
        </p>
        <Form.Group className="mb-3">
          <Form.Label>Monto nuevo</Form.Label>
          <Form.Control
            type="number"
            min="0.01"
            step="0.01"
            value={monto}
            autoFocus
            onChange={(e) => setMonto(e.target.value)}
            isInvalid={!!error && !montoValido}
          />
        </Form.Group>
        <Form.Group className="mb-3">
          <Form.Label>Motivo</Form.Label>
          <Form.Control
            as="textarea"
            rows={2}
            value={motivo}
            onChange={(e) => setMotivo(e.target.value)}
            isInvalid={!!error && !motivoValido}
          />
        </Form.Group>
      </Modal.Body>
      <Modal.Footer>
        <Button variant="secondary" onClick={onCerrar} disabled={enviando}>
          Cerrar
        </Button>
        <Button variant="info" onClick={confirmar} disabled={!puedeConfirmar}>
          {enviando ? "Guardando…" : "Guardar cambio"}
        </Button>
      </Modal.Footer>
    </Modal>
  );
}

function ModalCancelar({
  venta,
  fecha,
  lineas,
  onCerrar,
  onCancelada,
}: {
  venta: VentaResumen | null;
  fecha: string;
  lineas: VentaDelDia["lineas"] | undefined;
  onCerrar: () => void;
  onCancelada: () => void;
}) {
  const [motivo, setMotivo] = useState("");
  const [parcial, setParcial] = useState(false);
  const [seleccion, setSeleccion] = useState<Set<number>>(new Set());
  const [enviando, setEnviando] = useState(false);
  const [error, setError] = useState("");

  // Al abrir el modal para otra venta, reiniciar el formulario.
  useEffect(() => {
    setMotivo("");
    setParcial(false);
    setSeleccion(new Set());
    setError("");
    setEnviando(false);
  }, [venta?.id]);

  if (!venta) return null;

  const hayLineas = !!lineas && lineas.length > 1;
  const motivoValido = motivo.trim().length > 0;
  const seleccionValida = !parcial || seleccion.size > 0;

  const alternarLinea = (i: number) => {
    setSeleccion((prev) => {
      const copia = new Set(prev);
      if (copia.has(i)) copia.delete(i);
      else copia.add(i);
      return copia;
    });
  };

  const confirmar = () => {
    if (!motivoValido || !seleccionValida || enviando) return;
    setEnviando(true);
    setError("");
    const indices =
      parcial && seleccion.size > 0 ? [...seleccion].sort((a, b) => a - b) : undefined;
    cancelarVenta(venta.id, motivo.trim(), { fecha, lineas: indices })
      .then(onCancelada)
      .catch((e) => {
        setError(e instanceof Error ? e.message : "No se pudo cancelar la venta");
        setEnviando(false);
      });
  };

  return (
    <Modal show onHide={onCerrar} centered>
      <Modal.Header closeButton>
        <Modal.Title>Cancelar venta de {pesos(venta.total)}</Modal.Title>
      </Modal.Header>
      <Modal.Body>
        {error && <Alert variant="danger">{error}</Alert>}
        <p className="text-muted small">
          La venta no se borra: se registra un movimiento inverso que devuelve el
          stock y baja el total del día.
        </p>
        <Form.Group className="mb-3">
          <Form.Label>Motivo</Form.Label>
          <Form.Control
            as="textarea"
            rows={2}
            value={motivo}
            autoFocus
            onChange={(e) => setMotivo(e.target.value)}
            isInvalid={!!error && !motivoValido}
          />
        </Form.Group>

        {hayLineas && (
          <>
            <Form.Check
              type="checkbox"
              id="cancelar-parcial"
              label="Devolver solo algunas líneas"
              checked={parcial}
              onChange={(e) => setParcial(e.target.checked)}
              className="mb-2"
            />
            {parcial && (
              <div className="ps-2">
                {lineas!.map((l, i) => (
                  <Form.Check
                    key={i}
                    type="checkbox"
                    id={`linea-${i}`}
                    label={`${l.categoria ?? l.tipo} · ${pesos(l.subtotal)}`}
                    checked={seleccion.has(i)}
                    onChange={() => alternarLinea(i)}
                  />
                ))}
              </div>
            )}
          </>
        )}
      </Modal.Body>
      <Modal.Footer>
        <Button variant="secondary" onClick={onCerrar} disabled={enviando}>
          Cerrar
        </Button>
        <Button
          variant="danger"
          onClick={confirmar}
          disabled={!motivoValido || !seleccionValida || enviando}
        >
          {enviando ? "Cancelando…" : "Confirmar cancelación"}
        </Button>
      </Modal.Footer>
    </Modal>
  );
}

export default DesglosePagina;
