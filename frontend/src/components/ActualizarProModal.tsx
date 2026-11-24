import { Modal, Button, Form, Spinner } from "react-bootstrap";
import { useEffect, useRef, useState } from "react";
import {
  actualizarProducto,
  obtenerCategorias,
  subirImagenProducto,
} from "../services/catalogo";

interface Producto {
  id: string;
  nombre: string;
  categoria: string;
  descripcion: string;
  imagen: string;
  marca: string;
  codigo_barras?: string | null;
  precio: number;
  cantidad: number;
  papeleria?: string;
}

interface Props {
  show: boolean;
  onHide: () => void;
  onProductoActualizado: () => void;
  producto: Producto | null;
}

function ModalActualizarProducto({
  show,
  onHide,
  onProductoActualizado,
  producto,
}: Props) {
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [categorias, setCategorias] = useState<string[]>([]);

  const [subiendoImg, setSubiendoImg] = useState(false);
  const [errorImg, setErrorImg] = useState("");
  const inputCamara = useRef<HTMLInputElement>(null);
  const inputArchivo = useRef<HTMLInputElement>(null);

  const [formData, setFormData] = useState({
    nombre: "",
    categoria: "",
    descripcion: "",
    imagen: "",
    marca: "",
    codigo_barras: "",
    precio: 0,
    cantidad: 0,
    papeleria: "",
  });

  useEffect(() => {
    if (producto) {
      setFormData({
        nombre: producto.nombre,
        categoria: producto.categoria,
        descripcion: producto.descripcion,
        imagen: producto.imagen,
        marca: producto.marca,
        codigo_barras: producto.codigo_barras ?? "",
        precio: producto.precio,
        cantidad: producto.cantidad,
        papeleria: producto.papeleria ?? "",
      });
    }
  }, [producto]);

  useEffect(() => {
    if (!show) return;
    setError("");
    setErrorImg("");
    obtenerCategorias()
      .then(setCategorias)
      .catch(() => setCategorias([]));
  }, [show]);

  const handleChange = (
    e: React.ChangeEvent<
      HTMLInputElement | HTMLTextAreaElement | HTMLSelectElement
    >,
  ) => {
    const { name, value } = e.target;
    setFormData((prev) => ({
      ...prev,
      [name]: name === "precio" || name === "cantidad" ? Number(value) : value,
    }));
  };

  const handleImagen = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    e.target.value = "";
    if (!file) return;

    setSubiendoImg(true);
    setErrorImg("");
    try {
      const { url } = await subirImagenProducto(file);
      setFormData((prev) => ({ ...prev, imagen: url }));
    } catch (err) {
      setErrorImg(err instanceof Error ? err.message : "No se pudo subir la imagen");
    } finally {
      setSubiendoImg(false);
    }
  };

  const handleSubmit = async () => {
    if (!producto) return;
    if (Number(formData.precio) < 0) {
      setError("El precio no puede ser negativo");
      return;
    }

    setLoading(true);
    setError("");
    try {
      await actualizarProducto({
        ...producto,
        ...formData,
      });
      onProductoActualizado();
      onHide();
    } catch (err) {
      setError(
        err instanceof Error ? err.message : "No se pudo actualizar el producto",
      );
    } finally {
      setLoading(false);
    }
  };

  return (
    <Modal show={show} onHide={onHide} centered>
      <Modal.Header closeButton>
        <Modal.Title>Actualizar producto</Modal.Title>
      </Modal.Header>

      <Modal.Body>
        {error && <p className="text-danger">{error}</p>}

        <Form>
          <Form.Control
            name="nombre"
            value={formData.nombre}
            placeholder="Nombre"
            className="mb-2"
            onChange={handleChange}
          />

          <Form.Label className="mb-1">Categoría</Form.Label>
          <Form.Select
            name="categoria"
            value={formData.categoria}
            className="mb-2"
            onChange={handleChange}
          >
            <option value="">Seleccioná una categoría</option>
            {/* si la categoría actual del producto ya no está en la lista
                canónica, se muestra igual para no perderla al guardar */}
            {formData.categoria &&
              !categorias.includes(formData.categoria) && (
                <option value={formData.categoria}>
                  {formData.categoria} (actual)
                </option>
              )}
            {categorias.map((c) => (
              <option key={c} value={c}>
                {c}
              </option>
            ))}
          </Form.Select>

          <Form.Control
            name="marca"
            value={formData.marca}
            placeholder="Marca"
            className="mb-2"
            onChange={handleChange}
          />
          <Form.Control
            name="codigo_barras"
            value={formData.codigo_barras}
            placeholder="Código de barras (opcional)"
            className="mb-2"
            onChange={handleChange}
          />
          <Form.Control
            name="precio"
            type="number"
            min={0}
            step="0.01"
            value={formData.precio}
            placeholder="Precio"
            className="mb-2"
            onChange={handleChange}
          />
          <Form.Control
            name="cantidad"
            type="number"
            min={0}
            value={formData.cantidad}
            placeholder="Cantidad"
            className="mb-2"
            onChange={handleChange}
          />
          <Form.Control
            as="textarea"
            name="descripcion"
            value={formData.descripcion}
            placeholder="Descripción"
            rows={3}
            className="mb-2"
            onChange={handleChange}
          />
          <Form.Control
            name="papeleria"
            value={formData.papeleria}
            placeholder="Papelería"
            className="mb-3"
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
          {formData.imagen && (
            <img
              src={formData.imagen}
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
          {loading ? <Spinner size="sm" /> : "Guardar cambios"}
        </Button>
      </Modal.Footer>
    </Modal>
  );
}

export default ModalActualizarProducto;
