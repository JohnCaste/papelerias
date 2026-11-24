import { Modal, Button, Form, Spinner } from "react-bootstrap";
import { useEffect, useRef, useState } from "react";
import {
  agregarProducto,
  obtenerCategorias,
  subirImagenProducto,
} from "../services/catalogo";

interface Props {
  show: boolean;
  onHide: () => void;
  onProductoAgregado: () => void;
  /** Precarga el campo de código de barras (flujo de escaneo de un código nuevo). */
  codigoInicial?: string;
}

const FORM_VACIO = {
  nombre: "",
  categoria: "",
  imagen: "",
  marca: "",
  codigo_barras: "",
  precio: "",
  cantidad: "",
  descripcion: "",
  papeleria: "",
};

function ModalAgregarProducto({
  show,
  onHide,
  onProductoAgregado,
  codigoInicial,
}: Props) {
  const [loading, setLoading] = useState(false);
  const [form, setForm] = useState(FORM_VACIO);
  const [categorias, setCategorias] = useState<string[]>([]);
  const [errorForm, setErrorForm] = useState("");

  // imagen: se sube al final, aparte del resto del formulario
  const [subiendoImg, setSubiendoImg] = useState(false);
  const [errorImg, setErrorImg] = useState("");
  const inputCamara = useRef<HTMLInputElement>(null);
  const inputArchivo = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (!show) return;
    setForm({ ...FORM_VACIO, codigo_barras: codigoInicial ?? "" });
    setErrorForm("");
    setErrorImg("");
    obtenerCategorias()
      .then(setCategorias)
      .catch(() => setCategorias([]));
  }, [show, codigoInicial]);

  const handleChange = (
    e: React.ChangeEvent<
      HTMLInputElement | HTMLTextAreaElement | HTMLSelectElement
    >,
  ) => {
    setForm({ ...form, [e.target.name]: e.target.value });
  };

  const handleImagen = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    e.target.value = ""; // permite re-elegir el mismo archivo
    if (!file) return;

    setSubiendoImg(true);
    setErrorImg("");
    try {
      const { url } = await subirImagenProducto(file);
      setForm((prev) => ({ ...prev, imagen: url }));
    } catch (err) {
      setErrorImg(err instanceof Error ? err.message : "No se pudo subir la imagen");
    } finally {
      setSubiendoImg(false);
    }
  };

  const handleSubmit = async () => {
    if (Number(form.precio) < 0) {
      setErrorForm("El precio no puede ser negativo");
      return;
    }
    setErrorForm("");
    setLoading(true);
    try {
      await agregarProducto(form);
      onProductoAgregado();
      onHide();
    } catch (err) {
      setErrorForm(
        err instanceof Error ? err.message : "No se pudo agregar el producto",
      );
    } finally {
      setLoading(false);
    }
  };

  return (
    <Modal show={show} onHide={onHide} centered>
      <Modal.Header closeButton>
        <Modal.Title>Agregar producto</Modal.Title>
      </Modal.Header>

      <Modal.Body>
        {errorForm && <p className="text-danger">{errorForm}</p>}

        <Form>
          <Form.Control
            name="nombre"
            placeholder="Nombre"
            className="mb-2"
            value={form.nombre}
            onChange={handleChange}
          />

          <Form.Label className="mb-1">Categoría</Form.Label>
          <Form.Select
            name="categoria"
            className="mb-2"
            value={form.categoria}
            onChange={handleChange}
          >
            <option value="">Seleccioná una categoría</option>
            {categorias.map((c) => (
              <option key={c} value={c}>
                {c}
              </option>
            ))}
          </Form.Select>

          <Form.Control
            name="marca"
            placeholder="Marca"
            className="mb-2"
            value={form.marca}
            onChange={handleChange}
          />
          <Form.Control
            name="codigo_barras"
            placeholder="Código de barras (opcional)"
            className="mb-2"
            value={form.codigo_barras}
            onChange={handleChange}
          />
          <Form.Control
            name="precio"
            type="number"
            min={0}
            step="0.01"
            placeholder="Precio"
            className="mb-2"
            value={form.precio}
            onChange={handleChange}
          />
          <Form.Control
            name="cantidad"
            type="number"
            min={0}
            placeholder="Cantidad"
            className="mb-2"
            value={form.cantidad}
            onChange={handleChange}
          />
          <Form.Control
            as="textarea"
            name="descripcion"
            placeholder="Descripción"
            rows={3}
            className="mb-2"
            value={form.descripcion}
            onChange={handleChange}
          />
          <Form.Control
            name="papeleria"
            placeholder="Papeleria"
            className="mb-3"
            value={form.papeleria}
            onChange={handleChange}
          />

          {/* ---------- imagen: siempre al final ---------- */}
          <Form.Label className="mb-1">Imagen</Form.Label>
          <div className="d-flex gap-2 mb-2">
            <Button
              variant="outline-secondary"
              size="sm"
              disabled={subiendoImg}
              onClick={() => inputCamara.current?.click()}
            >
              Tomar foto
            </Button>
            <Button
              variant="outline-secondary"
              size="sm"
              disabled={subiendoImg}
              onClick={() => inputArchivo.current?.click()}
            >
              Subir foto
            </Button>
            {subiendoImg && <Spinner size="sm" className="align-self-center" />}
          </div>
          <input
            ref={inputCamara}
            type="file"
            accept="image/*"
            capture="environment"
            hidden
            onChange={handleImagen}
          />
          <input
            ref={inputArchivo}
            type="file"
            accept="image/*"
            hidden
            onChange={handleImagen}
          />
          {errorImg && <p className="text-danger mb-2">{errorImg}</p>}
          {form.imagen && (
            <img
              src={form.imagen}
              alt="Previsualización"
              style={{
                width: "100%",
                maxHeight: 180,
                objectFit: "contain",
                borderRadius: 8,
              }}
            />
          )}
        </Form>
      </Modal.Body>

      <Modal.Footer>
        <Button variant="secondary" onClick={onHide} disabled={loading}>
          Cancelar
        </Button>
        <Button
          variant="primary"
          onClick={handleSubmit}
          disabled={loading || subiendoImg}
        >
          {loading ? <Spinner size="sm" /> : "Guardar"}
        </Button>
      </Modal.Footer>
    </Modal>
  );
}

export default ModalAgregarProducto;
