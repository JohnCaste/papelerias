import { Modal, Button } from "react-bootstrap";

/* ==========================================================================
   Modal que aparece cuando se escanea un código de barras que no corresponde
   a ningún producto. Componente tonto: no sabe de catálogo ni de inventario.
   - "Agregar" solo se ofrece a quien puede dar de alta productos
     (`puedeAgregar`); el contenedor decide qué hace (abrir el alta con el
     código precargado).
   - "Cancelar" / "Cerrar" cierra sin efecto.
   ========================================================================== */

interface Props {
  show: boolean;
  codigo: string;
  puedeAgregar: boolean;
  onAgregar: () => void;
  onCancelar: () => void;
}

function ModalArticuloInexistente({
  show,
  codigo,
  puedeAgregar,
  onAgregar,
  onCancelar,
}: Props) {
  return (
    <Modal show={show} onHide={onCancelar} centered>
      <Modal.Header closeButton>
        <Modal.Title>Artículo inexistente</Modal.Title>
      </Modal.Header>

      <Modal.Body>
        Artículo «{codigo}» inexistente.
        {puedeAgregar && " ¿Querés agregarlo al catálogo?"}
      </Modal.Body>

      <Modal.Footer>
        {puedeAgregar ? (
          <>
            <Button variant="secondary" onClick={onCancelar}>
              Cancelar
            </Button>
            <Button variant="primary" onClick={onAgregar}>
              Agregar
            </Button>
          </>
        ) : (
          <Button variant="secondary" onClick={onCancelar}>
            Cerrar
          </Button>
        )}
      </Modal.Footer>
    </Modal>
  );
}

export default ModalArticuloInexistente;
