import {
  Package,
  Pencil,
  MoreHorizontal,
} from "lucide-react";
import "./ProductoCard.css";

/* ==========================================================================
   ProductoCard · recreación de la anatomía del handoff "Catalogo lapape.dc.html"
   (artboards 1a / 1b / 1d). Todo consume tokens semánticos --lp-* de index.css.

   Cambios vs. la card anterior:
   - se elimina el stepper - / n / + (era estado local sin persistir; sumar al
     carrito es responsabilidad del Punto de Venta).
   - width fijo 18rem -> la grilla decide el ancho.
   - superficie + borde + radius-lg + shadow-1/2, imagen 4:3, badge de stock.
   ========================================================================== */

const UMBRAL_STOCK_BAJO = 5; // constante de front hasta que exista stockMinimo por producto (M4 #32)

const money = (n: number) => "$ " + Math.round(n).toLocaleString("es-AR");

type EstadoStock = "ok" | "low" | "out";

function estadoStock(cantidad: number): EstadoStock {
  if (cantidad <= 0) return "out";
  if (cantidad <= UMBRAL_STOCK_BAJO) return "low";
  return "ok";
}

const BADGE_LABEL: Record<EstadoStock, string> = {
  ok: "En stock",
  low: "Stock bajo",
  out: "Agotado",
};

export interface ProductoCardProps {
  nombre: string;
  marca?: string;
  imagen?: string;
  precio: number;
  cantidad: number;
  /** Costo unitario; si viene y `mostrarCosto` es true se dibuja la línea mono de admin. */
  costo?: number;
  mostrarCosto?: boolean;
  /** Rol vendedor: una sola acción ("Ver detalle"), sin editar ni menú. */
  soloLectura?: boolean;
  /** Catálogo (admin): única acción "Ver" a ancho completo; editar/eliminar
   *  viven solo en Administración. Oculta lápiz y menú aunque sea admin. */
  soloAccionVer?: boolean;
  onVer?: () => void;
  onEditar?: () => void;
  onMenu?: () => void;
}

function ProductoCard({
  nombre,
  marca,
  imagen,
  precio,
  cantidad,
  costo,
  mostrarCosto = false,
  soloLectura = false,
  soloAccionVer = false,
  onVer,
  onEditar,
  onMenu,
}: ProductoCardProps) {
  const estado = estadoStock(cantidad);
  const agotado = estado === "out";

  const margen =
    costo != null && precio > 0
      ? Math.round(((precio - costo) / precio) * 100)
      : null;

  return (
    <article className="pc-card" data-agotado={agotado || undefined}>
      <div
        className="pc-media"
        data-sin-imagen={!imagen || undefined}
      >
        {imagen ? (
          <img src={imagen} alt={nombre} className="pc-img" loading="lazy" />
        ) : (
          <Package size={34} strokeWidth={1.5} aria-hidden />
        )}
        <span className={`pc-badge pc-badge--${estado}`}>
          {BADGE_LABEL[estado]}
        </span>
      </div>

      <div className="pc-body">
        <h3 className="pc-name" title={nombre}>
          {nombre}
        </h3>
        {marca && <p className="pc-brand">{marca}</p>}
      </div>

      <div className="pc-price-row">
        <span className="pc-price">{money(precio)}</span>
        <span className="pc-qty">{Math.max(cantidad, 0)} u.</span>
      </div>

      {mostrarCosto && costo != null && (
        <div className="pc-cost">
          costo {Math.round(costo).toLocaleString("es-AR")}
          {margen != null && ` · margen ${margen}%`}
        </div>
      )}

      <div className="pc-actions" data-solo-ver={soloAccionVer || undefined}>
        <button type="button" className="pc-btn pc-btn--main" onClick={onVer}>
          {soloLectura ? "Ver detalle" : "Ver"}
        </button>
        {!soloLectura && !soloAccionVer && (
          <>
            <button
              type="button"
              className="pc-btn pc-btn--icon"
              aria-label={`Editar ${nombre}`}
              onClick={onEditar}
            >
              <Pencil size={14} strokeWidth={2} />
            </button>
            <button
              type="button"
              className="pc-btn pc-btn--ghost"
              aria-label={`Más acciones para ${nombre}`}
              onClick={onMenu}
            >
              <MoreHorizontal size={16} strokeWidth={2.5} />
            </button>
          </>
        )}
      </div>
    </article>
  );
}

export default ProductoCard;
