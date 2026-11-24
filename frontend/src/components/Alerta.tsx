import Alert from "react-bootstrap/Alert";

interface AlertaProps {
  message: string;
  variant?: "danger" | "success" | "warning" | "info";
  onClose?: () => void;
}

function AlertaMsj({ message, variant = "danger", onClose }: AlertaProps) {
  return (
    <Alert variant={variant} dismissible onClose={onClose}>
      {message}
    </Alert>
  );
}

export default AlertaMsj;
