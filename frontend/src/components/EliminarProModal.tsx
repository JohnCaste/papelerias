import { Modal, Button } from "react-bootstrap";
import { eliminarProducto } from "../services/catalogo";
import { useState } from "react";

interface Props {
  show: boolean;
  onHide: () => void;
  productoId: string;
  onEliminado: () => void;
}

function ModalEliminarProducto({
  show,
  onHide,
  productoId,
  onEliminado,
}: Props) {
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  const handleEliminar = async () => {
    if (!productoId) return;

    setLoading(true);
    setError("");

    try {
      await eliminarProducto(productoId);
      onEliminado();
      onHide();
    } catch {
      setError("No se pudo eliminar el producto");
    } finally {
      setLoading(false);
    }
  };

  return (
    <Modal show={show} onHide={onHide} centered>
      <Modal.Header closeButton>
        <Modal.Title>¡CUIDADO!</Modal.Title>
      </Modal.Header>

      <Modal.Body>
        <h2 style={{ fontSize: "1.2rem", textAlign: "center" }}>
          ¿Estás seguro que deseas eliminar el producto?
        </h2>

        {error && <p className="text-danger text-center mt-2">{error}</p>}
      </Modal.Body>

      <Modal.Footer>
        <Button variant="secondary" onClick={onHide} disabled={loading}>
          Cancelar
        </Button>

        <Button variant="danger" onClick={handleEliminar} disabled={loading}>
          {loading ? "Eliminando..." : "Aceptar"}
        </Button>
      </Modal.Footer>
    </Modal>
  );
}

export default ModalEliminarProducto;
