import { useMemo, useState, type CSSProperties } from "react";
import { useTheme } from "../useTheme";
import "./Foundations.css";

/* ==========================================================================
   Recreación de "Foundations lapape.dc.html" (bundle de Claude Design).
   El .dc.html usaba un runtime propio (support.js) con {{ }} y <sc-for>;
   acá se porta a React. Los tokens viven en frontend/src/index.css.
   ========================================================================== */

/* ---------- primitivos de color (de support.js) ---------- */
const P: Record<string, Record<number, string>> = {
  green: { 50: "#EEF8F0", 100: "#D2EFD8", 200: "#A6DFB3", 300: "#74C888", 400: "#47B15F", 500: "#309C43", 600: "#268038", 700: "#1F672E", 800: "#1A5527", 900: "#164421" },
  blue: { 50: "#EEF4FF", 100: "#D9E6FF", 200: "#B3CCFF", 300: "#85AEFF", 400: "#558CF7", 500: "#2563EB", 600: "#1E4FD8", 700: "#1B41B0", 800: "#1B388C", 900: "#1B3270" },
  gray: { 0: "#FFFFFF", 50: "#F8FAFC", 100: "#F1F5F9", 200: "#E2E8F0", 300: "#CBD5E1", 400: "#94A3B8", 500: "#64748B", 600: "#475569", 700: "#334155", 800: "#1E293B", 900: "#0F172A" },
  success: { 100: "#CCFBF1", 500: "#0D9488", 700: "#0F766E" },
  danger: { 100: "#FEE2E2", 500: "#DC2626", 700: "#B91C1C" },
  warning: { 100: "#FEF3C7", 500: "#D97706", 700: "#B45309" },
  info: { 100: "#D9E6FF", 500: "#2563EB", 700: "#1B41B0" },
};

/* ---------- matemática de contraste (de support.js) ---------- */
type RGBA = { r: number; g: number; b: number; a: number };
function parseColor(c: string): RGBA {
  const s = (c || "").trim();
  if (s[0] === "#") {
    const h = s.slice(1);
    const n = h.length === 3 ? h.split("").map((x) => x + x).join("") : h;
    return { r: parseInt(n.slice(0, 2), 16), g: parseInt(n.slice(2, 4), 16), b: parseInt(n.slice(4, 6), 16), a: 1 };
  }
  const m = s.match(/rgba?\(([^)]+)\)/);
  if (m) {
    const p = m[1].split(",").map((x) => parseFloat(x));
    return { r: p[0], g: p[1], b: p[2], a: p.length > 3 ? p[3] : 1 };
  }
  return { r: 0, g: 0, b: 0, a: 1 };
}
function toHex(o: { r: number; g: number; b: number }): string {
  const h = (v: number) => Math.round(Math.max(0, Math.min(255, v))).toString(16).padStart(2, "0").toUpperCase();
  return "#" + h(o.r) + h(o.g) + h(o.b);
}
function flatten(fg: string, bg: string): string {
  const f = parseColor(fg);
  const b = parseColor(bg);
  if (f.a >= 1) return toHex(f);
  return toHex({ r: f.r * f.a + b.r * (1 - f.a), g: f.g * f.a + b.g * (1 - f.a), b: f.b * f.a + b.b * (1 - f.a) });
}
function luminance(c: string): number {
  const o = parseColor(c);
  const ch = (v: number) => {
    const x = v / 255;
    return x <= 0.03928 ? x / 12.92 : Math.pow((x + 0.055) / 1.055, 2.4);
  };
  return 0.2126 * ch(o.r) + 0.7152 * ch(o.g) + 0.0722 * ch(o.b);
}
function ratio(a: string, b: string): number {
  const l1 = luminance(a);
  const l2 = luminance(b);
  return (Math.max(l1, l2) + 0.05) / (Math.min(l1, l2) + 0.05);
}
const fmt = (n: number) => n.toFixed(2);

/* ---------- bloque de tokens para el botón "Copiar CSS" ---------- */
const TOKENS_CSS = `:root {
  /* primitivos · color */
  --lp-green-500: #309C43;  --lp-green-600: #268038;  --lp-green-700: #1F672E;
  --lp-blue-500:  #2563EB;  --lp-blue-600:  #1E4FD8;
  --lp-gray-0: #FFFFFF; --lp-gray-50: #F8FAFC; --lp-gray-200: #E2E8F0;
  --lp-gray-500: #64748B; --lp-gray-800: #1E293B; --lp-gray-900: #0F172A;

  /* primitivos · escala */
  --lp-font-sans: system-ui, -apple-system, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
  --lp-space-1: 4px; --lp-space-2: 8px; --lp-space-4: 16px; --lp-space-6: 24px;
  --lp-radius-sm: 4px; --lp-radius-md: 6px; --lp-radius-lg: 8px; --lp-radius-xl: 12px;
  --lp-control-height-md: 40px; --lp-icon-size-md: 16px;

  /* semánticos · tema claro */
  --lp-color-bg: var(--lp-gray-50);
  --lp-color-surface: var(--lp-gray-0);
  --lp-color-border: var(--lp-gray-200);
  --lp-color-border-strong: var(--lp-gray-300);
  --lp-color-text: var(--lp-gray-900);
  --lp-color-text-muted: var(--lp-gray-500);
  --lp-color-text-inverse: var(--lp-gray-0);
  --lp-color-primary: var(--lp-green-600);
  --lp-color-primary-hover: var(--lp-green-700);
  --lp-color-secondary: var(--lp-blue-500);
  --lp-color-link: var(--lp-blue-600);
  --lp-color-focus-ring: rgba(48,156,67,.45);
  --lp-shadow-1: 0 1px 2px rgba(15,23,42,.06);
  --lp-shadow-2: 0 4px 12px rgba(15,23,42,.10);
  --lp-shadow-3: 0 10px 24px rgba(15,23,42,.14);
  --lp-focus-ring: 0 0 0 3px var(--lp-color-focus-ring);
}

[data-theme="dark"] {
  --lp-color-bg: var(--lp-gray-900);
  --lp-color-surface: var(--lp-gray-800);
  --lp-color-border: var(--lp-gray-700);
  --lp-color-text: var(--lp-gray-50);
  --lp-color-text-muted: var(--lp-gray-400);
  --lp-color-primary: var(--lp-green-400);
  --lp-color-link: var(--lp-blue-300);
}
`;

/* ---------- builders (equivalen a renderVals() de support.js) ---------- */
const MONO = 'var(--lp-font-mono, ui-monospace, SFMono-Regular, Menlo, Consolas, monospace)';

function buildScale(key: string, label: string, role: string) {
  const steps = Object.keys(P[key]).map((k) => {
    const hex = P[key][Number(k)];
    const w = ratio(hex, "#FFFFFF");
    const b = ratio(hex, "#0F172A");
    return { step: String(k), hex, vsWhite: fmt(w), vsBlack: fmt(b), onLight: b >= w ? "#0F172A" : "#FFFFFF" };
  });
  return { label, prefix: `--lp-${key}-*`, role, steps };
}

function useFoundationData() {
  return useMemo(() => {
    const scales = [
      buildScale("green", "Green", "primario de marca · base 500 = #309C43"),
      buildScale("blue", "Blue", "acción de sistema, enlaces, info"),
      buildScale("gray", "Gray", "neutrales, superficies, texto"),
    ];

    const feedbackRows = (["success", "danger", "warning", "info"] as const).map((role) => ({
      role,
      prefix: `--lp-${role}-*`,
      steps: [100, 500, 700].map((k) => ({ step: String(k), hex: P[role][k] })),
    }));

    const L: Record<string, string> = {};
    const D: Record<string, string> = {};
    const def = (token: string, lRef: string, lHex: string, dRef: string, dHex: string) => {
      L[token] = lHex;
      D[token] = dHex;
      return { token: `--lp-color-${token}`, lightRef: lRef, lightHex: lHex, darkRef: dRef, darkHex: dHex };
    };
    const semanticRows = [
      def("bg", "gray-50", P.gray[50], "gray-900", P.gray[900]),
      def("surface", "gray-0", P.gray[0], "gray-800", P.gray[800]),
      def("surface-raised", "gray-0", P.gray[0], "gray-700", P.gray[700]),
      def("border", "gray-200", P.gray[200], "gray-700", P.gray[700]),
      def("border-strong", "gray-300", P.gray[300], "gray-600", P.gray[600]),
      def("text", "gray-900", P.gray[900], "gray-50", P.gray[50]),
      def("text-muted", "gray-500", P.gray[500], "gray-400", P.gray[400]),
      def("text-inverse", "gray-0", P.gray[0], "gray-900", P.gray[900]),
      def("primary", "green-600", P.green[600], "green-400", P.green[400]),
      def("primary-hover", "green-700", P.green[700], "green-300", P.green[300]),
      def("primary-text", "gray-0", P.gray[0], "gray-900", P.gray[900]),
      def("secondary", "blue-500", P.blue[500], "blue-400", P.blue[400]),
      def("secondary-hover", "blue-600", P.blue[600], "blue-300", P.blue[300]),
      def("link", "blue-600", P.blue[600], "blue-300", P.blue[300]),
      def("focus-ring", "green-500 @ 45%", flatten("rgba(48,156,67,.45)", P.gray[0]), "green-400 @ 55%", flatten("rgba(71,177,95,.55)", P.gray[800])),
      def("success", "success-500", P.success[500], "success-500", P.success[500]),
      def("danger", "danger-500", P.danger[500], "danger-500", P.danger[500]),
      def("warning", "warning-500", P.warning[500], "warning-500", P.warning[500]),
      def("info", "info-500", P.info[500], "info-500", P.info[500]),
      def("success-subtle", "success-100", P.success[100], "success-700 @ 25%", flatten("rgba(15,118,110,.25)", P.gray[800])),
      def("danger-subtle", "danger-100", P.danger[100], "danger-700 @ 25%", flatten("rgba(185,28,28,.25)", P.gray[800])),
      def("warning-subtle", "warning-100", P.warning[100], "warning-700 @ 25%", flatten("rgba(180,83,9,.25)", P.gray[800])),
      def("info-subtle", "info-100", P.info[100], "info-700 @ 25%", flatten("rgba(27,65,176,.25)", P.gray[800])),
      def("success-text", "success-700", P.success[700], "teal-300", "#5EEAD4"),
      def("danger-text", "danger-700", P.danger[700], "red-300", "#FCA5A5"),
      def("warning-text", "warning-700", P.warning[700], "amber-300", "#FCD34D"),
      def("info-text", "info-700", P.info[700], "blue-300", P.blue[300]),
      def("disabled-bg", "gray-200", P.gray[200], "gray-700", P.gray[700]),
      def("disabled-text", "gray-400", P.gray[400], "gray-500", P.gray[500]),
      def("overlay", "gray-900 @ 45%", flatten("rgba(15,23,42,.45)", P.gray[0]), "gray-900 @ 65%", flatten("rgba(15,23,42,.65)", P.gray[800])),
    ];

    const pairs: [string, string, string, number][] = [
      ["text / bg", "text", "bg", 4.5],
      ["text / surface", "text", "surface", 4.5],
      ["text-muted / surface", "text-muted", "surface", 4.5],
      ["text-muted / bg", "text-muted", "bg", 4.5],
      ["primary-text / primary", "primary-text", "primary", 4.5],
      ["text-inverse / secondary", "text-inverse", "secondary", 4.5],
      ["link / surface", "link", "surface", 4.5],
      ["success-text / success-subtle", "success-text", "success-subtle", 4.5],
      ["danger-text / danger-subtle", "danger-text", "danger-subtle", 4.5],
      ["warning-text / warning-subtle", "warning-text", "warning-subtle", 4.5],
      ["info-text / info-subtle", "info-text", "info-subtle", 4.5],
      ["disabled-text / disabled-bg", "disabled-text", "disabled-bg", 3],
      ["border-strong / surface", "border-strong", "surface", 3],
      ["primary / surface (foco)", "primary", "surface", 3],
    ];
    const badge = (r: number, th: number) => {
      const ok = r >= th;
      return { text: ok ? "AA" : "FAIL", bg: ok ? P.success[100] : P.danger[100], fg: ok ? P.success[700] : P.danger[700] };
    };
    const contrastRows = pairs.map(([label, fg, bg, th]) => {
      const lr = ratio(L[fg], L[bg]);
      const dr = ratio(D[fg], D[bg]);
      const lb = badge(lr, th);
      const db = badge(dr, th);
      return {
        label,
        threshold: th === 3 ? "3:1" : "4.5:1",
        lightRatio: fmt(lr), lightPass: lb.text, lightBadgeBg: lb.bg, lightBadgeFg: lb.fg,
        darkRatio: fmt(dr), darkPass: db.text, darkBadgeBg: db.bg, darkBadgeFg: db.fg,
      };
    });

    const spaceRows = [0, 1, 2, 3, 4, 5, 6, 8, 10, 12, 16].map((n) => ({ token: `--lp-space-${n}`, px: `${n * 4}px` }));

    const bsRows = [
      { bs: "--bs-primary", lp: "--lp-color-primary", note: "Bootstrap primary = verde de marca" },
      { bs: "--bs-primary-rgb", lp: "38, 128, 56", note: "Bootstrap necesita el rgb crudo (green-600)" },
      { bs: "--bs-secondary", lp: "--lp-color-secondary", note: "azul de sistema" },
      { bs: "--bs-success / -danger / -warning / -info", lp: "--lp-color-success / -danger / -warning / -info", note: "idénticos en ambos temas" },
      { bs: "--bs-body-bg", lp: "--lp-color-bg", note: "cambia con data-theme" },
      { bs: "--bs-body-color", lp: "--lp-color-text", note: "" },
      { bs: "--bs-secondary-color", lp: "--lp-color-text-muted", note: "texto secundario de Bootstrap 5.3" },
      { bs: "--bs-border-color", lp: "--lp-color-border", note: "" },
      { bs: "--bs-border-radius", lp: "--lp-radius-md", note: "6px como radio por defecto" },
      { bs: "--bs-border-radius-sm / -lg / -xl", lp: "--lp-radius-sm / -lg / -xl", note: "" },
      { bs: "--bs-link-color", lp: "--lp-color-link", note: "hover: --lp-color-primary" },
      { bs: "--bs-box-shadow-sm / (base) / -lg", lp: "--lp-shadow-1 / -2 / -3", note: "modal usa shadow-4" },
      { bs: "--bs-font-sans-serif", lp: "--lp-font-sans", note: "" },
      { bs: "--bs-body-font-size", lp: "--lp-font-size-md", note: "16px base" },
      { bs: "--bs-emphasis-color", lp: "--lp-color-text", note: "" },
      { bs: "--bs-tertiary-bg", lp: "--lp-color-surface-raised", note: "table-striped y form-control:disabled" },
    ];

    return { scales, feedbackRows, semanticRows, contrastRows, spaceRows, bsRows };
  }, []);
}

/* ---------- fragmentos de estilo reutilizados ---------- */
const S = {
  section: { maxWidth: 1200, margin: "0 auto", padding: "56px 40px", borderTop: "1px solid var(--lp-color-border)" } as CSSProperties,
  eyebrow: { margin: "0 0 8px", fontSize: 12, fontWeight: 600, letterSpacing: "0.14em", textTransform: "uppercase", color: "var(--lp-color-text-muted)" } as CSSProperties,
  h2: { margin: "0 0 12px", fontSize: 30, lineHeight: 1.2, fontWeight: 700, letterSpacing: "-0.015em" } as CSSProperties,
  h3sm: { margin: "0 0 16px", fontSize: 12, fontWeight: 600, letterSpacing: "0.14em", textTransform: "uppercase", color: "var(--lp-color-text-muted)" } as CSSProperties,
  lead: { margin: "0 0 40px", maxWidth: "70ch", fontSize: 16, color: "var(--lp-color-text-muted)" } as CSSProperties,
  mono: { fontFamily: MONO } as CSSProperties,
  monoMuted: { fontFamily: MONO, fontSize: 12, color: "var(--lp-color-text-muted)" } as CSSProperties,
  card: { padding: 20, border: "1px solid var(--lp-color-border)", borderRadius: 12, background: "var(--lp-color-surface)" } as CSSProperties,
  chip: { padding: "6px 12px", borderRadius: 999, background: "var(--lp-color-surface)", border: "1px solid var(--lp-color-border)", fontFamily: MONO, fontSize: 12 } as CSSProperties,
};

const btnBase: CSSProperties = {
  display: "inline-flex", alignItems: "center", justifyContent: "center", gap: 8,
  padding: "10px 16px", borderRadius: 6, border: "1px solid transparent",
  fontFamily: "inherit", fontSize: 14, fontWeight: 600, cursor: "pointer",
};

function Spinner({ size = 14 }: { size?: number }) {
  return (
    <span style={{ width: size, height: size, borderRadius: "50%", border: "2px solid currentColor", borderTopColor: "transparent", animation: "lp-spin 700ms linear infinite" }} />
  );
}

function Plus({ s = 16 }: { s?: number }) {
  return (
    <svg width={s} height={s} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2} strokeLinecap="round">
      <path d="M12 5v14M5 12h14" />
    </svg>
  );
}

/* ========================================================================== */
export default function Foundations() {
  const { theme, toggleTheme } = useTheme();
  const [copied, setCopied] = useState(false);
  const data = useFoundationData();
  const copyCss = () => {
    const done = () => {
      setCopied(true);
      setTimeout(() => setCopied(false), 1600);
    };
    if (navigator.clipboard) navigator.clipboard.writeText(TOKENS_CSS).then(done, done);
    else done();
  };

  const navLink: CSSProperties = { color: "var(--lp-color-text-muted)", whiteSpace: "nowrap" };

  return (
    <div className="lp-foundations" data-theme={theme === "dark" ? "dark" : undefined}>
      {/* ---------- header ---------- */}
      <header style={{ position: "sticky", top: 0, zIndex: 1020, background: "var(--lp-color-surface)", borderBottom: "1px solid var(--lp-color-border)", boxShadow: "var(--lp-shadow-1)" }}>
        <div style={{ maxWidth: 1200, margin: "0 auto", padding: "0 40px", height: 60, display: "flex", alignItems: "center", gap: 32 }}>
          <a
            href="/catalogo"
            style={{ display: "inline-flex", alignItems: "center", gap: 6, padding: "7px 14px", borderRadius: 999, border: "1px solid var(--lp-color-border-strong)", color: "var(--lp-color-text)", textDecoration: "none", fontSize: 13, fontWeight: 600, whiteSpace: "nowrap" }}
          >
            ← Menú principal
          </a>
          <div style={{ display: "flex", alignItems: "baseline", gap: 8 }}>
            <span style={{ fontSize: 18, fontWeight: 700, letterSpacing: "-0.01em" }}>lapape</span>
            <span style={{ fontFamily: MONO, fontSize: 12, color: "var(--lp-color-primary)" }}>--lp-</span>
          </div>
          <nav className="lp-foundations__nav" style={{ display: "flex", gap: 20, flex: 1, fontSize: 13, fontWeight: 500, overflow: "hidden" }}>
            <a href="#color-primitivos" style={navLink}>Color</a>
            <a href="#color-semantico" style={navLink}>Semántico</a>
            <a href="#tipografia" style={navLink}>Tipografía</a>
            <a href="#espaciado" style={navLink}>Espaciado</a>
            <a href="#forma" style={navLink}>Forma &amp; motion</a>
            <a href="#componentes" style={navLink}>Componentes</a>
            <a href="#entregables" style={navLink}>Entregables</a>
          </nav>
          <button
            className="lp-foundations__theme-btn"
            onClick={toggleTheme}
            style={{ display: "inline-flex", alignItems: "center", gap: 8, padding: "7px 14px", borderRadius: 999, border: "1px solid var(--lp-color-border-strong)", background: "transparent", color: "var(--lp-color-text)", fontFamily: "inherit", fontSize: 13, fontWeight: 600, cursor: "pointer", transition: "background var(--lp-duration-fast) var(--lp-ease-standard)" }}
          >
            <span style={{ width: 8, height: 8, borderRadius: "50%", background: "var(--lp-color-primary)" }} />
            {theme === "dark" ? "Oscuro" : "Claro"}
          </button>
        </div>
      </header>

      {/* ---------- portada ---------- */}
      <section id="portada" style={{ maxWidth: 1200, margin: "0 auto", padding: "96px 40px 64px" }}>
        <div style={{ display: "grid", gridTemplateColumns: "minmax(0, 1.25fr) minmax(0, 1fr)", gap: 64, alignItems: "end" }}>
          <div>
            <p style={{ margin: "0 0 20px", fontSize: 12, fontWeight: 600, letterSpacing: "0.14em", textTransform: "uppercase", color: "var(--lp-color-text-muted)" }}>Sistema de diseño · Foundations</p>
            <h1 style={{ margin: "0 0 24px", fontSize: 40, lineHeight: 1.2, fontWeight: 700, letterSpacing: "-0.02em" }}>
              Primitivos y tokens de <span style={{ color: "var(--lp-color-primary)" }}>lapape</span>
            </h1>
            <p style={{ margin: "0 0 32px", maxWidth: "60ch", fontSize: 18, lineHeight: 1.65, color: "var(--lp-color-text-muted)" }}>
              Fuente de verdad visual para el rediseño de Login, Menú, Catálogo, Admin, VentaDía, Desglose y modales. Los{" "}
              <strong style={{ color: "var(--lp-color-text)", fontWeight: 600 }}>primitivos</strong> son escalas crudas e inmutables; los{" "}
              <strong style={{ color: "var(--lp-color-text)", fontWeight: 600 }}>tokens semánticos</strong> son decisiones que cambian con el tema. La UI consume solo tokens semánticos.
            </p>
            <div style={{ display: "flex", flexWrap: "wrap", gap: 10 }}>
              {["React 19 + Vite + TS", "React-Bootstrap 5.3", "CSS custom properties", "WCAG AA"].map((t) => (
                <span key={t} style={S.chip}>{t}</span>
              ))}
            </div>
          </div>
          <div style={{ display: "grid", gap: 12, padding: 24, background: "var(--lp-color-surface)", border: "1px solid var(--lp-color-border)", borderRadius: 12, boxShadow: "var(--lp-shadow-2)" }}>
            <p style={{ margin: "0 0 4px", fontSize: 12, fontWeight: 600, letterSpacing: "0.14em", textTransform: "uppercase", color: "var(--lp-color-text-muted)" }}>Leyenda de estados</p>
            {[
              ["def", "apariencia por defecto"],
              ["hov", "puntero encima"],
              ["act", "presionado"],
              ["foc", "foco de teclado"],
              ["dis", "deshabilitado"],
              ["load", "cargando"],
            ].map(([k, v]) => (
              <div key={k} style={{ display: "flex", alignItems: "center", gap: 12, fontSize: 13 }}>
                <span style={{ flex: "none", width: 44, textAlign: "center", padding: "3px 0", borderRadius: 4, background: "var(--lp-color-bg)", border: "1px solid var(--lp-color-border)", fontFamily: MONO, fontSize: 11 }}>{k}</span>
                {v}
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* ---------- color · primitivos ---------- */}
      <section id="color-primitivos" style={S.section}>
        <p style={S.eyebrow}>02 · Color</p>
        <h2 style={S.h2}>Primitivos</h2>
        <p style={S.lead}>
          Verde de marca (base <span style={{ fontFamily: MONO, fontSize: 14 }}>#309C43</span>), azul de sistema y grises. Cada swatch muestra su token, hex y el ratio de contraste contra blanco y negro — el valor mayor a 4.5 indica sobre qué fondo ese paso funciona como texto.
        </p>

        {data.scales.map((scale) => (
          <div key={scale.label} style={{ marginBottom: 40 }}>
            <div style={{ display: "flex", alignItems: "baseline", gap: 12, marginBottom: 12 }}>
              <h3 style={{ margin: 0, fontSize: 20, fontWeight: 600, lineHeight: 1.35 }}>{scale.label}</h3>
              <span style={S.monoMuted}>{scale.prefix}</span>
              <span style={{ fontSize: 13, color: "var(--lp-color-text-muted)" }}>{scale.role}</span>
            </div>
            <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(104px, 1fr))", gap: 8 }}>
              {scale.steps.map((s) => (
                <div key={s.step} style={{ border: "1px solid var(--lp-color-border)", borderRadius: 8, overflow: "hidden", background: "var(--lp-color-surface)" }}>
                  <div style={{ height: 76, background: s.hex, display: "flex", alignItems: "flex-end", justifyContent: "space-between", padding: "6px 8px" }}>
                    <span style={{ fontFamily: MONO, fontSize: 11, fontWeight: 600, color: s.onLight }}>W {s.vsWhite}</span>
                    <span style={{ fontFamily: MONO, fontSize: 11, fontWeight: 600, color: s.onLight }}>B {s.vsBlack}</span>
                  </div>
                  <div style={{ padding: 8 }}>
                    <div style={{ fontFamily: MONO, fontSize: 11, fontWeight: 600 }}>{s.step}</div>
                    <div style={{ fontFamily: MONO, fontSize: 11, color: "var(--lp-color-text-muted)" }}>{s.hex}</div>
                  </div>
                </div>
              ))}
            </div>
          </div>
        ))}

        <h3 style={{ margin: "48px 0 12px", fontSize: 20, fontWeight: 600 }}>Feedback · escala corta</h3>
        <p style={{ margin: "0 0 16px", fontSize: 14, color: "var(--lp-color-text-muted)" }}>100 fondo · 500 sólido · 700 texto. El success se movió a teal para no confundirse con el verde de marca; el warning es ámbar.</p>
        <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(240px, 1fr))", gap: 16 }}>
          {data.feedbackRows.map((f) => (
            <div key={f.role} style={{ border: "1px solid var(--lp-color-border)", borderRadius: 8, background: "var(--lp-color-surface)", overflow: "hidden" }}>
              <div style={{ padding: "12px 14px", borderBottom: "1px solid var(--lp-color-border)", display: "flex", alignItems: "center", justifyContent: "space-between" }}>
                <strong style={{ fontSize: 15, fontWeight: 600 }}>{f.role}</strong>
                <span style={{ fontFamily: MONO, fontSize: 11, color: "var(--lp-color-text-muted)" }}>{f.prefix}</span>
              </div>
              {f.steps.map((s) => (
                <div key={s.step} style={{ display: "flex", alignItems: "center", gap: 12, padding: "8px 14px" }}>
                  <span style={{ flex: "none", width: 40, height: 26, borderRadius: 4, border: "1px solid var(--lp-color-border)", background: s.hex }} />
                  <span style={{ fontFamily: MONO, fontSize: 12, fontWeight: 600, width: 32 }}>{s.step}</span>
                  <span style={{ fontFamily: MONO, fontSize: 12, color: "var(--lp-color-text-muted)" }}>{s.hex}</span>
                </div>
              ))}
            </div>
          ))}
        </div>
      </section>

      {/* ---------- color · semántico ---------- */}
      <section id="color-semantico" style={S.section}>
        <p style={S.eyebrow}>03 · Color</p>
        <h2 style={S.h2}>Tokens semánticos</h2>
        <p style={{ ...S.lead, margin: "0 0 32px" }}>Lo único que la UI debe nombrar. Claro y oscuro lado a lado con el primitivo del que derivan.</p>

        <div style={{ border: "1px solid var(--lp-color-border)", borderRadius: 12, overflow: "hidden", background: "var(--lp-color-surface)" }}>
          <div style={{ display: "grid", gridTemplateColumns: "minmax(0, 1.4fr) minmax(0, 1fr) minmax(0, 1fr)", gap: 16, padding: "12px 20px", background: "var(--lp-color-bg)", borderBottom: "1px solid var(--lp-color-border)", fontSize: 12, fontWeight: 600, letterSpacing: "0.06em", textTransform: "uppercase", color: "var(--lp-color-text-muted)" }}>
            <span>Token</span><span>Claro</span><span>Oscuro</span>
          </div>
          {data.semanticRows.map((r) => (
            <div key={r.token} style={{ display: "grid", gridTemplateColumns: "minmax(0, 1.4fr) minmax(0, 1fr) minmax(0, 1fr)", gap: 16, padding: "10px 20px", borderBottom: "1px solid var(--lp-color-border)", alignItems: "center" }}>
              <span style={{ fontFamily: MONO, fontSize: 12.5 }}>{r.token}</span>
              {([[r.lightRef, r.lightHex], [r.darkRef, r.darkHex]] as const).map(([ref, hex], i) => (
                <span key={i} style={{ display: "flex", alignItems: "center", gap: 10, minWidth: 0 }}>
                  <span style={{ flex: "none", width: 28, height: 28, borderRadius: 6, border: "1px solid var(--lp-color-border-strong)", background: hex }} />
                  <span style={{ minWidth: 0 }}>
                    <span style={{ display: "block", fontFamily: MONO, fontSize: 11.5 }}>{ref}</span>
                    <span style={{ display: "block", fontFamily: MONO, fontSize: 11, color: "var(--lp-color-text-muted)" }}>{hex}</span>
                  </span>
                </span>
              ))}
            </div>
          ))}
        </div>

        <h3 style={{ margin: "48px 0 12px", fontSize: 20, fontWeight: 600 }}>Matriz de contraste · pares texto / fondo</h3>
        <p style={{ margin: "0 0 16px", fontSize: 14, color: "var(--lp-color-text-muted)" }}>Umbral AA: 4.5:1 texto normal, 3:1 texto grande y bordes / focos. Cada par se evalúa en ambos temas.</p>
        <div style={{ border: "1px solid var(--lp-color-border)", borderRadius: 12, overflow: "hidden", background: "var(--lp-color-surface)" }}>
          <div style={{ display: "grid", gridTemplateColumns: "minmax(0, 2fr) 120px 120px 90px", gap: 12, padding: "12px 20px", background: "var(--lp-color-bg)", borderBottom: "1px solid var(--lp-color-border)", fontSize: 12, fontWeight: 600, letterSpacing: "0.06em", textTransform: "uppercase", color: "var(--lp-color-text-muted)" }}>
            <span>Par</span><span>Claro</span><span>Oscuro</span><span>Umbral</span>
          </div>
          {data.contrastRows.map((c) => (
            <div key={c.label} style={{ display: "grid", gridTemplateColumns: "minmax(0, 2fr) 120px 120px 90px", gap: 12, padding: "10px 20px", borderBottom: "1px solid var(--lp-color-border)", alignItems: "center" }}>
              <span style={{ fontFamily: MONO, fontSize: 12 }}>{c.label}</span>
              <span style={{ display: "flex", alignItems: "center", gap: 8 }}>
                <span style={{ fontFamily: MONO, fontSize: 12.5, fontWeight: 600 }}>{c.lightRatio}</span>
                <span style={{ padding: "2px 7px", borderRadius: 999, fontSize: 10.5, fontWeight: 700, letterSpacing: "0.04em", background: c.lightBadgeBg, color: c.lightBadgeFg }}>{c.lightPass}</span>
              </span>
              <span style={{ display: "flex", alignItems: "center", gap: 8 }}>
                <span style={{ fontFamily: MONO, fontSize: 12.5, fontWeight: 600 }}>{c.darkRatio}</span>
                <span style={{ padding: "2px 7px", borderRadius: 999, fontSize: 10.5, fontWeight: 700, letterSpacing: "0.04em", background: c.darkBadgeBg, color: c.darkBadgeFg }}>{c.darkPass}</span>
              </span>
              <span style={{ fontFamily: MONO, fontSize: 12, color: "var(--lp-color-text-muted)" }}>{c.threshold}</span>
            </div>
          ))}
        </div>
        <div style={{ marginTop: 16, display: "grid", gap: 8, maxWidth: "90ch", fontSize: 13, lineHeight: 1.5, color: "var(--lp-color-text-muted)" }}>
          <div><strong style={{ color: "var(--lp-color-text)", fontWeight: 600 }}>disabled-text / disabled-bg</strong> falla a propósito: WCAG exime a los controles deshabilitados, y el estado se comunica además con cursor y semántica.</div>
          <div><strong style={{ color: "var(--lp-color-text)", fontWeight: 600 }}>border-strong / surface</strong> no llega a 3:1 con gray-300. Recomendado: gray-500 en inputs, gray-300 solo en separadores decorativos.</div>
        </div>
      </section>

      {/* ---------- tipografía ---------- */}
      <section id="tipografia" style={S.section}>
        <p style={S.eyebrow}>04</p>
        <h2 style={S.h2}>Tipografía</h2>
        <p style={S.lead}>Familia de sistema, sin webfont: <span style={{ fontFamily: MONO, fontSize: 13 }}>--lp-font-sans</span></p>

        <div style={{ display: "grid", gridTemplateColumns: "minmax(0, 1fr) minmax(0, 1fr)", gap: 48 }}>
          <div>
            <h3 style={S.h3sm}>Escala</h3>
            <div style={{ display: "grid", gap: 4 }}>
              {[
                ["--lp-font-size-xs · 12", 12, "Venta del día 12"],
                ["--lp-font-size-sm · 14", 14, "Venta del día 14"],
                ["--lp-font-size-md · 16", 16, "Venta del día 16"],
                ["--lp-font-size-lg · 18", 18, "Venta del día 18"],
                ["--lp-font-size-xl · 20", 20, "Venta del día 20"],
                ["--lp-font-size-2xl · 24", 24, "Venta del día"],
                ["--lp-font-size-3xl · 30", 30, "Venta del día"],
                ["--lp-font-size-4xl · 40", 40, "Catálogo"],
              ].map(([label, size, sample], i, arr) => (
                <div key={String(label)} style={{ display: "flex", alignItems: "baseline", gap: 16, padding: "8px 0", borderBottom: i < arr.length - 1 ? "1px dashed var(--lp-color-border)" : undefined }}>
                  <span style={{ flex: "none", width: 132, fontFamily: MONO, fontSize: 11.5, color: "var(--lp-color-text-muted)" }}>{label}</span>
                  <span style={{ fontSize: size as number, lineHeight: 1.2, whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>{sample}</span>
                </div>
              ))}
            </div>

            <h3 style={{ ...S.h3sm, margin: "40px 0 16px" }}>Pesos &amp; line-height</h3>
            <div style={{ display: "grid", gap: 6, fontSize: 16 }}>
              {[["regular · 400", 400], ["medium · 500", 500], ["semibold · 600", 600], ["bold · 700", 700]].map(([label, w]) => (
                <div key={String(label)} style={{ display: "flex", gap: 16, alignItems: "baseline" }}>
                  <span style={{ flex: "none", width: 132, fontFamily: MONO, fontSize: 11.5, color: "var(--lp-color-text-muted)" }}>{label}</span>
                  <span style={{ fontWeight: w as number }}>Precio unitario</span>
                </div>
              ))}
            </div>
            <div style={{ display: "grid", gridTemplateColumns: "repeat(4, minmax(0, 1fr))", gap: 12, marginTop: 20 }}>
              {[["tight 1.2", 1.2], ["snug 1.35", 1.35], ["normal 1.5", 1.5], ["relaxed 1.65", 1.65]].map(([label, lh]) => (
                <div key={String(label)} style={{ padding: 10, border: "1px solid var(--lp-color-border)", borderRadius: 6 }}>
                  <div style={{ fontFamily: MONO, fontSize: 11, color: "var(--lp-color-text-muted)", marginBottom: 6 }}>{label}</div>
                  <div style={{ fontSize: 13, lineHeight: lh as number }}>Dos líneas de texto para ver el ritmo.</div>
                </div>
              ))}
            </div>
          </div>

          <div>
            <h3 style={S.h3sm}>Estilos compuestos</h3>
            <div style={{ display: "grid", gap: 20, padding: 28, background: "var(--lp-color-surface)", border: "1px solid var(--lp-color-border)", borderRadius: 12 }}>
              {[
                { el: <div style={{ fontSize: 40, fontWeight: 700, lineHeight: 1.2, letterSpacing: "-0.02em" }}>Catálogo de productos</div>, m: "display · 4xl / bold / tight" },
                { el: <div style={{ fontSize: 30, fontWeight: 700, lineHeight: 1.2, letterSpacing: "-0.015em" }}>Venta del día</div>, m: "h1 · 3xl / bold / tight" },
                { el: <div style={{ fontSize: 24, fontWeight: 600, lineHeight: 1.35 }}>Resumen de caja</div>, m: "h2 · 2xl / semibold / snug" },
                { el: <div style={{ fontSize: 20, fontWeight: 600, lineHeight: 1.35 }}>Productos sin stock</div>, m: "h3 · xl / semibold / snug" },
                { el: <div style={{ fontSize: 16, fontWeight: 400, lineHeight: 1.5, maxWidth: "46ch" }}>El texto de cuerpo se usa para descripciones, ayuda de formularios y contenido de modales. Mantener medida entre 45 y 75 caracteres.</div>, m: "body · md / regular / normal" },
                { el: <div style={{ fontSize: 12, fontWeight: 500, lineHeight: 1.35, color: "var(--lp-color-text-muted)", textTransform: "uppercase", letterSpacing: "0.06em" }}>Actualizado hace 3 minutos</div>, m: "caption · xs / medium / snug / text-muted" },
              ].map((row) => (
                <div key={row.m}>
                  {row.el}
                  <div style={{ marginTop: 6, fontFamily: MONO, fontSize: 11.5, color: "var(--lp-color-text-muted)" }}>{row.m}</div>
                </div>
              ))}
            </div>
          </div>
        </div>
      </section>

      {/* ---------- espaciado ---------- */}
      <section id="espaciado" style={S.section}>
        <p style={S.eyebrow}>05</p>
        <h2 style={S.h2}>Espaciado</h2>
        <p style={{ ...S.lead, margin: "0 0 32px" }}>Base 4px. Saltos no lineales arriba de 6 para evitar decisiones ambiguas.</p>
        <div style={{ display: "grid", gap: 6, maxWidth: 780 }}>
          {data.spaceRows.map((sp) => (
            <div key={sp.token} style={{ display: "flex", alignItems: "center", gap: 16 }}>
              <span style={{ flex: "none", width: 128, fontFamily: MONO, fontSize: 12, color: "var(--lp-color-text-muted)" }}>{sp.token}</span>
              <span style={{ flex: "none", width: 44, fontFamily: MONO, fontSize: 12, fontWeight: 600 }}>{sp.px}</span>
              <span style={{ height: 18, borderRadius: 4, background: "var(--lp-color-primary)", width: sp.px, minWidth: 2 }} />
            </div>
          ))}
        </div>
        <div style={{ marginTop: 40, padding: "20px 24px", background: "var(--lp-color-surface)", border: "1px solid var(--lp-color-border)", borderRadius: 12, display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(200px, 1fr))", gap: 20 }}>
          {[
            ["--lp-container-max", "1200px"],
            ["breakpoints (Bootstrap)", "576 · 768 · 992 · 1200"],
            ["padding de página", "space-10 / space-4"],
          ].map(([k, v]) => (
            <div key={k}>
              <div style={{ fontFamily: MONO, fontSize: 11.5, color: "var(--lp-color-text-muted)", marginBottom: 4 }}>{k}</div>
              <div style={{ fontSize: 18, fontWeight: 600 }}>{v}</div>
            </div>
          ))}
        </div>
      </section>

      {/* ---------- forma & motion ---------- */}
      <section id="forma" style={S.section}>
        <p style={S.eyebrow}>06</p>
        <h2 style={{ ...S.h2, margin: "0 0 32px" }}>Radios · Sombras · Bordes · Foco · Motion · Dimensiones</h2>

        <h3 style={S.h3sm}>Radios</h3>
        <div style={{ display: "flex", flexWrap: "wrap", gap: 16, marginBottom: 48 }}>
          {[["sm · 4", 4], ["md · 6", 6], ["lg · 8", 8], ["xl · 12", 12], ["pill · 999", 999], ["circle · 50%", "50%"]].map(([label, r]) => (
            <div key={String(label)} style={{ textAlign: "center" }}>
              <div style={{ width: label === "circle · 50%" ? 72 : 92, height: 72, margin: label === "circle · 50%" ? "0 10px" : undefined, background: "var(--lp-color-surface)", border: "1px solid var(--lp-color-border-strong)", borderRadius: r as number | string }} />
              <div style={{ marginTop: 8, fontFamily: MONO, fontSize: 11.5, color: "var(--lp-color-text-muted)" }}>{label}</div>
            </div>
          ))}
        </div>

        <h3 style={S.h3sm}>Elevación</h3>
        <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(180px, 1fr))", gap: 24, marginBottom: 48 }}>
          {[
            ["--lp-shadow-1 · listas, inputs", "var(--lp-shadow-1)"],
            ["--lp-shadow-2 · login-card", "var(--lp-shadow-2)"],
            ["--lp-shadow-3 · dropdown, popover", "var(--lp-shadow-3)"],
            ["--lp-shadow-4 · modal", "var(--lp-shadow-4)"],
          ].map(([label, sh]) => (
            <div key={label}>
              <div style={{ height: 96, background: "var(--lp-color-surface)", borderRadius: 8, boxShadow: sh }} />
              <div style={{ marginTop: 12, fontFamily: MONO, fontSize: 11.5, color: "var(--lp-color-text-muted)" }}>{label}</div>
            </div>
          ))}
        </div>

        <div style={{ display: "grid", gridTemplateColumns: "minmax(0, 1fr) minmax(0, 1fr)", gap: 40 }}>
          <div>
            <h3 style={S.h3sm}>Bordes &amp; foco</h3>
            <div style={{ display: "grid", gap: 16 }}>
              <div style={{ display: "flex", alignItems: "center", gap: 16 }}>
                <span style={{ flex: "none", width: 120, height: 40, border: "1px solid var(--lp-color-border)", borderRadius: 6, background: "var(--lp-color-surface)" }} />
                <span style={{ fontFamily: MONO, fontSize: 11.5, color: "var(--lp-color-text-muted)" }}>border-width 1px · color-border</span>
              </div>
              <div style={{ display: "flex", alignItems: "center", gap: 16 }}>
                <span style={{ flex: "none", width: 120, height: 40, border: "2px solid var(--lp-color-border-strong)", borderRadius: 6, background: "var(--lp-color-surface)" }} />
                <span style={{ fontFamily: MONO, fontSize: 11.5, color: "var(--lp-color-text-muted)" }}>border-width-strong 2px · border-strong</span>
              </div>
              <div style={{ display: "flex", alignItems: "center", gap: 16, padding: "6px 0" }}>
                <span style={{ flex: "none", width: 120, height: 40, border: "1px solid var(--lp-color-border)", borderRadius: 6, background: "var(--lp-color-surface)", outline: "2px solid var(--lp-color-primary)", outlineOffset: 2, boxShadow: "var(--lp-focus-ring)" }} />
                <span style={{ fontFamily: MONO, fontSize: 11.5, color: "var(--lp-color-text-muted)" }}>--lp-focus-ring + outline 2px / offset 2px</span>
              </div>
              <button style={{ ...btnBase, justifySelf: "start", background: "var(--lp-color-primary)", color: "var(--lp-color-primary-text)" }}>Probá el foco con Tab</button>
            </div>
          </div>
          <div>
            <h3 style={S.h3sm}>Motion</h3>
            <p style={{ margin: "0 0 16px", fontSize: 14, color: "var(--lp-color-text-muted)" }}>
              Cada barra usa una duración distinta con <span style={{ fontFamily: MONO, fontSize: 12.5 }}>--lp-ease-standard</span>. Se respeta <span style={{ fontFamily: MONO, fontSize: 12.5 }}>prefers-reduced-motion</span>.
            </p>
            <div style={{ display: "grid", gap: 12 }}>
              {[["fast · 120ms"], ["base · 180ms"], ["slow · 280ms"]].map(([label]) => (
                <div key={label} style={{ display: "flex", alignItems: "center", gap: 16 }}>
                  <span style={{ flex: "none", width: 116, fontFamily: MONO, fontSize: 11.5, color: "var(--lp-color-text-muted)" }}>{label}</span>
                  <span style={{ flex: 1, height: 34, borderRadius: 6, background: "var(--lp-color-surface)", border: "1px solid var(--lp-color-border)" }} />
                </div>
              ))}
            </div>
            <h3 style={{ ...S.h3sm, margin: "32px 0 12px" }}>Z-index</h3>
            <div style={{ display: "flex", flexWrap: "wrap", gap: 8 }}>
              {["dropdown 1000", "sticky 1020", "fixed 1030", "backdrop 1040", "modal 1050", "popover 1060", "toast 1080 ↑"].map((z, i) => (
                <span key={z} style={{ padding: "5px 10px", borderRadius: 4, background: i === 6 ? "var(--lp-color-primary)" : "var(--lp-color-surface)", color: i === 6 ? "var(--lp-color-primary-text)" : undefined, border: i === 6 ? undefined : "1px solid var(--lp-color-border)", fontFamily: MONO, fontSize: 11.5 }}>{z}</span>
              ))}
            </div>
          </div>
        </div>

        <h3 style={{ ...S.h3sm, margin: "48px 0 16px" }}>Dimensiones de control &amp; ícono</h3>
        <p style={{ margin: "0 0 20px", maxWidth: "70ch", fontSize: 14, color: "var(--lp-color-text-muted)" }}>
          Alturas y paddings de <span style={{ fontFamily: MONO, fontSize: 12.5 }}>button</span> / <span style={{ fontFamily: MONO, fontSize: 12.5 }}>input</span> / <span style={{ fontFamily: MONO, fontSize: 12.5 }}>select</span>, tamaño de ícono <span style={{ fontFamily: MONO, fontSize: 12.5 }}>lucide-react</span> y opacidades. Se aplican token a token al rediseñar cada pantalla; nunca un px suelto por vista.
        </p>
        <div style={{ display: "grid", gridTemplateColumns: "minmax(0, 1fr) minmax(0, 1fr)", gap: 40 }}>
          <div>
            <div style={{ fontFamily: MONO, fontSize: 11.5, color: "var(--lp-color-text-muted)", marginBottom: 14 }}>alto de control · sm 32 / md 40 (def) / lg 48</div>
            <div style={{ display: "grid", gap: 12 }}>
              {[["--lp-control-height-sm · 32", 32, "0 12px", 12], ["--lp-control-height-md · 40", 40, "0 16px", 14], ["--lp-control-height-lg · 48", 48, "0 22px", 16]].map(([label, h, pad, fs]) => (
                <div key={String(label)} style={{ display: "flex", alignItems: "center", gap: 16 }}>
                  <span style={{ flex: "none", width: 190, fontFamily: MONO, fontSize: 11, color: "var(--lp-color-text-muted)" }}>{label}</span>
                  <span style={{ display: "inline-flex", alignItems: "center", padding: pad as string, height: h as number, borderRadius: 6, background: "var(--lp-color-surface)", border: "1px solid var(--lp-color-border-strong)", fontSize: fs as number, fontWeight: 600 }}>Guardar</span>
                </div>
              ))}
            </div>
            <div style={{ marginTop: 14, fontFamily: MONO, fontSize: 11, color: "var(--lp-color-text-muted)" }}>--lp-control-pad-x-sm / -md / -lg · 12 / 16 / 22</div>
          </div>
          <div>
            <div style={{ fontFamily: MONO, fontSize: 11.5, color: "var(--lp-color-text-muted)", marginBottom: 14 }}>ícono lucide-react · --lp-icon-stroke 2</div>
            <div style={{ display: "flex", alignItems: "flex-end", gap: 24 }}>
              {[["sm · 14", 14], ["md · 16 (def)", 16], ["lg · 18", 18]].map(([label, s]) => (
                <div key={String(label)} style={{ textAlign: "center", color: "var(--lp-color-primary)" }}>
                  <Plus s={s as number} />
                  <div style={{ marginTop: 8, fontFamily: MONO, fontSize: 11, color: "var(--lp-color-text-muted)" }}>{label}</div>
                </div>
              ))}
            </div>
            <div style={{ marginTop: 24, marginBottom: 12, fontFamily: MONO, fontSize: 11.5, color: "var(--lp-color-text-muted)" }}>opacidad</div>
            <div style={{ display: "flex", flexWrap: "wrap", gap: 10 }}>
              {[["disabled · .55", 0.55], ["loading · .85", 0.85], ["muted · .7", 0.7]].map(([label, o]) => (
                <span key={String(label)} style={{ display: "inline-flex", alignItems: "center", gap: 8, padding: "6px 12px", borderRadius: 6, border: "1px solid var(--lp-color-border)", fontSize: 12 }}>
                  <span style={{ width: 40, height: 16, borderRadius: 4, background: "var(--lp-color-primary)", opacity: o as number }} />
                  {label}
                </span>
              ))}
            </div>
          </div>
        </div>
      </section>

      {/* ---------- componentes ---------- */}
      <section id="componentes" style={S.section}>
        <p style={S.eyebrow}>07</p>
        <h2 style={S.h2}>Primitivos de componente</h2>
        <p style={S.lead}>Solo apariencia y estados. Cada estado se muestra renderizado en vez de depender del puntero, para poder revisarlo de un vistazo.</p>

        <h3 style={{ margin: "0 0 4px", fontSize: 20, fontWeight: 600 }}>Button</h3>
        <p style={{ margin: "0 0 20px", fontSize: 14, color: "var(--lp-color-text-muted)" }}>primary verde · secondary azul · outline · ghost · danger</p>
        <ButtonMatrix />

        <div style={{ display: "grid", gridTemplateColumns: "minmax(0, 1fr) minmax(0, 1fr)", gap: 24, marginTop: 24 }}>
          <div style={{ ...S.card, padding: "20px 24px" }}>
            <div style={{ fontFamily: MONO, fontSize: 11.5, color: "var(--lp-color-text-muted)", marginBottom: 16 }}>tamaños · sm 32 / md 40 / lg 48</div>
            <div style={{ display: "flex", alignItems: "center", gap: 12, flexWrap: "wrap" }}>
              <button style={{ ...btnBase, height: 32, padding: "0 12px", fontSize: 12, background: "var(--lp-color-primary)", color: "var(--lp-color-primary-text)" }}>sm</button>
              <button style={{ ...btnBase, height: 40, padding: "0 16px", background: "var(--lp-color-primary)", color: "var(--lp-color-primary-text)" }}>md</button>
              <button style={{ ...btnBase, height: 48, padding: "0 22px", fontSize: 16, background: "var(--lp-color-primary)", color: "var(--lp-color-primary-text)" }}>lg</button>
            </div>
          </div>
          <div style={{ ...S.card, padding: "20px 24px" }}>
            <div style={{ fontFamily: MONO, fontSize: 11.5, color: "var(--lp-color-text-muted)", marginBottom: 16 }}>con ícono · lucide-react 16px, gap space-2</div>
            <div style={{ display: "flex", alignItems: "center", gap: 12, flexWrap: "wrap" }}>
              <button style={{ ...btnBase, height: 40, padding: "0 16px", background: "var(--lp-color-primary)", color: "var(--lp-color-primary-text)" }}><Plus />Nuevo producto</button>
              <button style={{ ...btnBase, height: 40, padding: "0 16px", border: "1px solid var(--lp-color-border-strong)", background: "transparent", color: "var(--lp-color-text)" }}>Exportar<Plus /></button>
              <button style={{ ...btnBase, width: 40, height: 40, padding: 0, border: "1px solid var(--lp-color-border-strong)", background: "transparent", color: "var(--lp-color-text)" }}><Plus /></button>
            </div>
          </div>
        </div>

        <h3 style={{ margin: "48px 0 20px", fontSize: 20, fontWeight: 600 }}>Input · Textarea · Select</h3>
        <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(240px, 1fr))", gap: 20 }}>
          <Field label="Nombre del producto" hint="Como aparece en el catálogo." tag="normal">
            <input defaultValue="Papel A4 75g" style={inputStyle()} />
          </Field>
          <Field label="Nombre del producto" hint="Como aparece en el catálogo." tag="focus">
            <input defaultValue="Papel A4 75g" style={{ ...inputStyle(), borderColor: "var(--lp-color-primary)", outline: "2px solid var(--lp-color-primary)", outlineOffset: 2, boxShadow: "var(--lp-focus-ring)" }} />
          </Field>
          <Field label="Precio" tag="error" error="El precio debe ser mayor a 0.">
            <input defaultValue="-120" style={{ ...inputStyle(), border: "2px solid var(--lp-color-danger)" }} />
          </Field>
          <Field label="Código interno" hint="Se genera automáticamente." tag="disabled" labelMuted>
            <input defaultValue="LP-0042" disabled style={{ ...inputStyle(), background: "var(--lp-color-disabled-bg)", color: "var(--lp-color-disabled-text)", border: "1px solid var(--lp-color-border)", cursor: "not-allowed" }} />
          </Field>
          <Field label="Observaciones" tag="textarea">
            <textarea rows={3} defaultValue="Entrega parcial, faltan 3 resmas." style={{ ...inputStyle(), height: "auto", padding: "10px 12px", lineHeight: 1.5, resize: "vertical" }} />
          </Field>
          <Field label="Categoría" tag="select">
            <select style={inputStyle()}>
              <option>Papelería</option>
              <option>Librería</option>
            </select>
          </Field>
        </div>

        <h3 style={{ margin: "48px 0 20px", fontSize: 20, fontWeight: 600 }}>Checkbox · Radio · Switch</h3>
        <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(220px, 1fr))", gap: 20 }}>
          <ControlCard title="checkbox">
            <CtrlRow><Box /> Sin stock</CtrlRow>
            <CtrlRow><Box checked /> Destacado</CtrlRow>
            <CtrlRow><Box focus /> Con foco</CtrlRow>
            <CtrlRow muted><Box disabled /> Deshabilitado</CtrlRow>
          </ControlCard>
          <ControlCard title="radio">
            <CtrlRow><Dot /> Efectivo</CtrlRow>
            <CtrlRow><Dot checked /> Transferencia</CtrlRow>
            <CtrlRow><Dot focus /> Con foco</CtrlRow>
            <CtrlRow muted><Dot disabled /> Cuenta corriente</CtrlRow>
          </ControlCard>
          <ControlCard title="switch">
            <CtrlRow><Toggle /> Off</CtrlRow>
            <CtrlRow><Toggle on /> On</CtrlRow>
            <CtrlRow><Toggle on focus /> On + foco</CtrlRow>
            <CtrlRow muted><Toggle disabled /> Deshabilitado</CtrlRow>
          </ControlCard>
        </div>

        <div style={{ display: "grid", gridTemplateColumns: "minmax(0, 1fr) minmax(0, 1.15fr)", gap: 24, marginTop: 48 }}>
          <div>
            <h3 style={{ margin: "0 0 20px", fontSize: 20, fontWeight: 600 }}>Badge / Pill</h3>
            <div style={{ ...S.card, display: "grid", gap: 16 }}>
              <div>
                <div style={{ fontFamily: MONO, fontSize: 11, color: "var(--lp-color-text-muted)", marginBottom: 10 }}>sólido</div>
                <div style={{ display: "flex", flexWrap: "wrap", gap: 8 }}>
                  <Badge bg="var(--lp-color-border-strong)" fg="var(--lp-color-text)">Neutro</Badge>
                  <Badge bg="var(--lp-color-success)" fg="#FFFFFF">Pagado</Badge>
                  <Badge bg="var(--lp-color-danger)" fg="#FFFFFF">Sin stock</Badge>
                  <Badge bg="var(--lp-color-warning)" fg="#FFFFFF">Pendiente</Badge>
                  <Badge bg="var(--lp-color-info)" fg="#FFFFFF">Nuevo</Badge>
                </div>
              </div>
              <div>
                <div style={{ fontFamily: MONO, fontSize: 11, color: "var(--lp-color-text-muted)", marginBottom: 10 }}>subtle</div>
                <div style={{ display: "flex", flexWrap: "wrap", gap: 8 }}>
                  <Badge bg="var(--lp-color-bg)" fg="var(--lp-color-text-muted)" border>Neutro</Badge>
                  <Badge bg="var(--lp-color-success-subtle)" fg="var(--lp-color-success-text)">Pagado</Badge>
                  <Badge bg="var(--lp-color-danger-subtle)" fg="var(--lp-color-danger-text)">Sin stock</Badge>
                  <Badge bg="var(--lp-color-warning-subtle)" fg="var(--lp-color-warning-text)">Pendiente</Badge>
                  <Badge bg="var(--lp-color-info-subtle)" fg="var(--lp-color-info-text)">Nuevo</Badge>
                </div>
              </div>
            </div>
          </div>
          <div>
            <h3 style={{ margin: "0 0 20px", fontSize: 20, fontWeight: 600 }}>
              Alert <span style={{ fontSize: 13, fontWeight: 400, color: "var(--lp-color-text-muted)" }}>— componente <span style={{ fontFamily: MONO }}>Alerta</span></span>
            </h3>
            <div style={{ display: "grid", gap: 12 }}>
              <Alert tone="success" title="Venta registrada" body="Se guardó el movimiento de caja." />
              <Alert tone="danger" title="No se pudo guardar" body="Revisá la conexión e intentá de nuevo." />
              <Alert tone="warning" title="Stock bajo" body="Quedan 4 unidades de 12 productos." />
              <Alert tone="info" title="Cierre de caja a las 21:00" body="Los movimientos posteriores van al día siguiente." />
            </div>
          </div>
        </div>

        <div style={{ display: "grid", gridTemplateColumns: "minmax(0, 1fr) minmax(0, 1.2fr)", gap: 24, marginTop: 48, alignItems: "start" }}>
          <div>
            <h3 style={{ margin: "0 0 20px", fontSize: 20, fontWeight: 600 }}>Card / Surface</h3>
            <div style={{ display: "grid", gap: 16 }}>
              <div style={{ padding: 20, borderRadius: 8, background: "var(--lp-color-surface)", border: "1px solid var(--lp-color-border)", boxShadow: "var(--lp-shadow-1)" }}>
                <div style={{ fontSize: 12, fontWeight: 500, textTransform: "uppercase", letterSpacing: "0.06em", color: "var(--lp-color-text-muted)" }}>Ventas de hoy</div>
                <div style={{ marginTop: 8, fontSize: 30, fontWeight: 700, lineHeight: 1.2 }}>$ 184.500</div>
                <div style={{ marginTop: 4, fontSize: 13, color: "var(--lp-color-success-text)" }}>+12% vs ayer</div>
                <div style={{ marginTop: 14, fontFamily: MONO, fontSize: 11, color: "var(--lp-color-text-muted)" }}>surface + border + shadow-1</div>
              </div>
              <div style={{ padding: 20, borderRadius: 8, background: "var(--lp-color-surface-raised)", boxShadow: "var(--lp-shadow-2)" }}>
                <div style={{ fontSize: 12, fontWeight: 500, textTransform: "uppercase", letterSpacing: "0.06em", color: "var(--lp-color-text-muted)" }}>Tickets emitidos</div>
                <div style={{ marginTop: 8, fontSize: 30, fontWeight: 700, lineHeight: 1.2 }}>37</div>
                <div style={{ marginTop: 14, fontFamily: MONO, fontSize: 11, color: "var(--lp-color-text-muted)" }}>surface-raised + shadow-2 (login-card)</div>
              </div>
            </div>
          </div>
          <div>
            <h3 style={{ margin: "0 0 20px", fontSize: 20, fontWeight: 600 }}>Modal</h3>
            <div style={{ position: "relative", borderRadius: 12, overflow: "hidden", background: "var(--lp-color-overlay)", padding: "32px 24px" }}>
              <div style={{ maxWidth: 460, margin: "0 auto", borderRadius: 12, background: "var(--lp-color-surface)", boxShadow: "var(--lp-shadow-4)", overflow: "hidden" }}>
                <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: 16, padding: "16px 20px", borderBottom: "1px solid var(--lp-color-border)" }}>
                  <strong style={{ fontSize: 20, fontWeight: 600 }}>Eliminar producto</strong>
                  <button style={{ ...btnBase, width: 32, height: 32, padding: 0, background: "transparent", color: "var(--lp-color-text-muted)" }}>
                    <svg width={16} height={16} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2} strokeLinecap="round"><path d="M6 6l12 12M18 6 6 18" /></svg>
                  </button>
                </div>
                <div style={{ padding: 20, fontSize: 16, lineHeight: 1.5, color: "var(--lp-color-text)" }}>
                  ¿Eliminar <strong style={{ fontWeight: 600 }}>Papel A4 75g</strong> del catálogo? Esta acción no se puede deshacer.
                </div>
                <div style={{ display: "flex", justifyContent: "flex-end", gap: 12, padding: "16px 20px", borderTop: "1px solid var(--lp-color-border)", background: "var(--lp-color-bg)" }}>
                  <button style={{ ...btnBase, background: "transparent", color: "var(--lp-color-text)" }}>Cancelar</button>
                  <button style={{ ...btnBase, background: "var(--lp-color-danger)", color: "#FFFFFF" }}>Eliminar</button>
                </div>
              </div>
              <div style={{ position: "absolute", top: 10, left: 14, fontFamily: MONO, fontSize: 11, color: "rgba(255,255,255,0.75)" }}>backdrop 1040 · overlay · modal 1050 · shadow-4</div>
            </div>
          </div>
        </div>

        <h3 style={{ margin: "48px 0 20px", fontSize: 20, fontWeight: 600 }}>Table</h3>
        <div style={{ border: "1px solid var(--lp-color-border)", borderRadius: 12, overflow: "hidden", background: "var(--lp-color-surface)" }}>
          <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 14 }}>
            <thead>
              <tr style={{ background: "var(--lp-color-bg)" }}>
                {["Producto", "Cant.", "P. unit", "Total", ""].map((h, i) => (
                  <th key={i} style={{ textAlign: i === 0 ? "left" : i === 4 ? "center" : "right", padding: i === 0 || i === 3 ? "12px 16px" : "12px 12px", width: i === 1 || i === 2 || i === 4 ? 80 : undefined, fontSize: 12, fontWeight: 600, letterSpacing: "0.06em", textTransform: "uppercase", color: "var(--lp-color-text-muted)", borderBottom: "1px solid var(--lp-color-border)" }}>{h}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {[
                ["Papel A4 75g", "12", "3.200", "38.400", "OK", "success"],
                ["Cuaderno tapa dura", "4", "5.900", "23.600", "Bajo", "warning"],
                ["Lápiz HB x12", "30", "890", "26.700", "Falta", "danger"],
              ].map((row, ri) => (
                <tr key={ri} style={{ background: ri === 1 ? "var(--lp-color-bg)" : undefined }}>
                  <td style={{ padding: "12px 16px", borderBottom: ri < 2 ? "1px solid var(--lp-color-border)" : undefined }}>{row[0]}</td>
                  <td style={{ padding: "12px 12px", textAlign: "right", fontVariantNumeric: "tabular-nums", borderBottom: ri < 2 ? "1px solid var(--lp-color-border)" : undefined }}>{row[1]}</td>
                  <td style={{ padding: "12px 12px", textAlign: "right", fontVariantNumeric: "tabular-nums", borderBottom: ri < 2 ? "1px solid var(--lp-color-border)" : undefined }}>{row[2]}</td>
                  <td style={{ padding: "12px 16px", textAlign: "right", fontWeight: 600, fontVariantNumeric: "tabular-nums", borderBottom: ri < 2 ? "1px solid var(--lp-color-border)" : undefined }}>{row[3]}</td>
                  <td style={{ padding: "12px 12px", textAlign: "center", borderBottom: ri < 2 ? "1px solid var(--lp-color-border)" : undefined }}>
                    <span style={{ padding: "3px 8px", borderRadius: 999, background: `var(--lp-color-${row[5]}-subtle)`, color: `var(--lp-color-${row[5]}-text)`, fontSize: 11, fontWeight: 600 }}>{row[4]}</span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: 16, padding: "12px 16px", borderTop: "1px solid var(--lp-color-border)", background: "var(--lp-color-bg)" }}>
            <span style={{ fontSize: 13, color: "var(--lp-color-text-muted)" }}>Zebra con <span style={{ fontFamily: MONO, fontSize: 12 }}>--lp-color-bg</span> · celda compacta 80px</span>
            <span style={{ display: "flex", gap: 8 }}>
              <button style={{ ...btnBase, padding: "7px 12px", fontSize: 13, border: "1px solid var(--lp-color-border-strong)", background: "var(--lp-color-surface)", color: "var(--lp-color-disabled-text)", cursor: "not-allowed" }}>Anterior</button>
              <button style={{ ...btnBase, padding: "7px 12px", fontSize: 13, border: "1px solid var(--lp-color-border-strong)", background: "var(--lp-color-surface)", color: "var(--lp-color-text)" }}>Siguiente</button>
            </span>
          </div>
        </div>

        <h3 style={{ margin: "48px 0 20px", fontSize: 20, fontWeight: 600 }}>Navbar · Tabs · Dropdown</h3>
        <div style={{ display: "grid", gap: 20 }}>
          <div style={{ borderRadius: 8, overflow: "hidden", boxShadow: "var(--lp-shadow-1)" }}>
            <div style={{ display: "flex", alignItems: "center", gap: 24, padding: "0 20px", height: 56, background: "var(--lp-color-primary)" }}>
              <span style={{ fontSize: 18, fontWeight: 700, color: "var(--lp-color-primary-text)" }}>lapape</span>
              <span style={{ display: "flex", gap: 4, flex: 1 }}>
                <span style={{ padding: "8px 14px", borderRadius: 6, background: "rgba(255,255,255,0.22)", color: "var(--lp-color-primary-text)", fontSize: 14, fontWeight: 600 }}>Catálogo</span>
                {["Venta del día", "Desglose", "Admin"].map((t) => (
                  <span key={t} style={{ padding: "8px 14px", borderRadius: 6, color: "var(--lp-color-primary-text)", fontSize: 14, fontWeight: 500, opacity: 0.85 }}>{t}</span>
                ))}
              </span>
              <span style={{ display: "inline-flex", alignItems: "center", gap: 8, padding: "6px 12px", borderRadius: 999, border: "1px solid rgba(255,255,255,0.4)", color: "var(--lp-color-primary-text)", fontSize: 13, fontWeight: 600 }}>Vendedor</span>
            </div>
            <div style={{ padding: "8px 20px", background: "var(--lp-color-surface)", fontFamily: MONO, fontSize: 11, color: "var(--lp-color-text-muted)" }}>navbar de marca · fondo primary · texto primary-text · activo = blanco 22%</div>
          </div>
          <div style={{ borderRadius: 8, overflow: "hidden", boxShadow: "var(--lp-shadow-1)" }}>
            <div style={{ display: "flex", alignItems: "center", gap: 24, padding: "0 20px", height: 56, background: "var(--lp-gray-800)" }}>
              <span style={{ fontSize: 18, fontWeight: 700, color: "var(--lp-gray-50)" }}>lapape</span>
              <span style={{ display: "flex", gap: 4, flex: 1 }}>
                <span style={{ padding: "8px 14px", borderRadius: 6, background: "var(--lp-color-primary)", color: "var(--lp-color-primary-text)", fontSize: 14, fontWeight: 600 }}>Catálogo</span>
                {["Venta del día", "Desglose"].map((t) => (
                  <span key={t} style={{ padding: "8px 14px", borderRadius: 6, color: "var(--lp-gray-300)", fontSize: 14, fontWeight: 500 }}>{t}</span>
                ))}
              </span>
            </div>
            <div style={{ padding: "8px 20px", background: "var(--lp-color-surface)", fontFamily: MONO, fontSize: 11, color: "var(--lp-color-text-muted)" }}>navbar oscuro · gray-800 · activo = primary</div>
          </div>
          <div style={{ display: "grid", gridTemplateColumns: "minmax(0, 1fr) 260px", gap: 20, alignItems: "start" }}>
            <div style={{ padding: "0 20px", background: "var(--lp-color-surface)", border: "1px solid var(--lp-color-border)", borderRadius: 8 }}>
              <div style={{ display: "flex", gap: 8, borderBottom: "1px solid var(--lp-color-border)" }}>
                <span style={{ padding: "14px 4px", marginBottom: -1, borderBottom: "2px solid var(--lp-color-primary)", color: "var(--lp-color-text)", fontSize: 14, fontWeight: 600 }}>Productos</span>
                {["Categorías", "Proveedores"].map((t) => (
                  <span key={t} style={{ padding: "14px 12px", color: "var(--lp-color-text-muted)", fontSize: 14, fontWeight: 500 }}>{t}</span>
                ))}
                <span style={{ padding: "14px 12px", color: "var(--lp-color-disabled-text)", fontSize: 14, fontWeight: 500 }}>Importar</span>
              </div>
              <div style={{ padding: "16px 4px", fontSize: 14, color: "var(--lp-color-text-muted)" }}>Tab activa marcada con borde inferior de 2px en primary; nunca solo por color de texto.</div>
            </div>
            <div style={{ borderRadius: 8, background: "var(--lp-color-surface)", border: "1px solid var(--lp-color-border)", boxShadow: "var(--lp-shadow-3)", padding: 6, display: "grid", gap: 2 }}>
              <span style={{ padding: "9px 12px", borderRadius: 6, fontSize: 14, background: "var(--lp-color-bg)" }}>Editar</span>
              <span style={{ padding: "9px 12px", borderRadius: 6, fontSize: 14 }}>Duplicar</span>
              <span style={{ padding: "9px 12px", borderRadius: 6, fontSize: 14 }}>Ver historial</span>
              <span style={{ height: 1, background: "var(--lp-color-border)", margin: "4px 0" }} />
              <span style={{ padding: "9px 12px", borderRadius: 6, fontSize: 14, color: "var(--lp-color-danger-text)" }}>Eliminar</span>
              <span style={{ padding: "4px 12px 6px", fontFamily: MONO, fontSize: 10.5, color: "var(--lp-color-text-muted)" }}>dropdown 1000 · shadow-3</span>
            </div>
          </div>
        </div>

        <h3 style={{ margin: "48px 0 20px", fontSize: 20, fontWeight: 600 }}>Spinner · Toast · Tooltip</h3>
        <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(240px, 1fr))", gap: 20, alignItems: "start" }}>
          <div style={{ ...S.card, padding: 24, display: "flex", alignItems: "center", gap: 20, color: "var(--lp-color-primary)" }}>
            <span style={{ width: 20, height: 20, borderRadius: "50%", border: "2px solid var(--lp-color-border-strong)", borderTopColor: "var(--lp-color-primary)", animation: "lp-spin 700ms linear infinite" }} />
            <span style={{ width: 32, height: 32, borderRadius: "50%", border: "3px solid var(--lp-color-border-strong)", borderTopColor: "var(--lp-color-primary)", animation: "lp-spin 700ms linear infinite" }} />
            <span style={{ fontFamily: MONO, fontSize: 11, color: "var(--lp-color-text-muted)" }}>spinner sm / md · 700ms</span>
          </div>
          <div style={{ display: "grid", gap: 12 }}>
            <div style={{ display: "flex", alignItems: "center", gap: 12, padding: "12px 16px", borderRadius: 8, background: "var(--lp-gray-800)", color: "var(--lp-gray-50)", boxShadow: "var(--lp-shadow-3)" }}>
              <span style={{ width: 8, height: 8, borderRadius: "50%", background: "var(--lp-color-success)" }} />
              <span style={{ flex: 1, fontSize: 14 }}>Producto agregado</span>
              <span style={{ fontFamily: MONO, fontSize: 10.5, opacity: 0.7 }}>z 1080</span>
            </div>
            <div style={{ display: "flex", alignItems: "center", gap: 12, padding: "12px 16px", borderRadius: 8, background: "var(--lp-color-danger)", color: "#FFFFFF", boxShadow: "var(--lp-shadow-3)" }}>
              <span style={{ width: 8, height: 8, borderRadius: "50%", background: "#FFFFFF" }} />
              <span style={{ flex: 1, fontSize: 14 }}>Error al guardar la venta</span>
              <span style={{ fontFamily: MONO, fontSize: 10.5, opacity: 0.8 }}>z 1080</span>
            </div>
          </div>
          <div style={{ ...S.card, padding: 24, display: "flex", flexDirection: "column", alignItems: "center", gap: 10 }}>
            <span style={{ padding: "6px 10px", borderRadius: 6, background: "var(--lp-gray-800)", color: "var(--lp-gray-50)", fontSize: 12.5, boxShadow: "var(--lp-shadow-2)" }}>Stock disponible: 12</span>
            <span style={{ width: 0, height: 0, borderLeft: "6px solid transparent", borderRight: "6px solid transparent", borderTop: "6px solid var(--lp-gray-800)" }} />
            <span style={{ padding: "7px 12px", borderRadius: 6, border: "1px solid var(--lp-color-border-strong)", fontSize: 13, fontWeight: 600 }}>Papel A4 75g</span>
            <span style={{ fontFamily: MONO, fontSize: 11, color: "var(--lp-color-text-muted)" }}>tooltip · popover 1060</span>
          </div>
        </div>
      </section>

      {/* ---------- do / don't ---------- */}
      <section id="reglas" style={S.section}>
        <p style={S.eyebrow}>08</p>
        <h2 style={{ ...S.h2, margin: "0 0 32px" }}>Do / Don't</h2>
        <div style={{ display: "grid", gridTemplateColumns: "minmax(0, 1fr) minmax(0, 1fr)", gap: 24 }}>
          <div style={{ padding: 24, borderRadius: 12, background: "var(--lp-color-surface)", border: "1px solid var(--lp-color-border)", borderTop: "3px solid var(--lp-color-success)" }}>
            <div style={{ fontSize: 12, fontWeight: 700, letterSpacing: "0.14em", textTransform: "uppercase", color: "var(--lp-color-success-text)", marginBottom: 16 }}>Do</div>
            <div style={{ display: "grid", gap: 12, fontSize: 14.5, lineHeight: 1.5 }}>
              <div><Code>background: var(--lp-color-primary)</Code> — siempre el token semántico.</div>
              <div>Derivar tokens nuevos de primitivos existentes, no de hex sueltos.</div>
              <div>Mapear <Code>--bs-*</Code> sobre <Code>--lp-*</Code> una sola vez en <Code>index.css</Code>.</div>
              <div>Comunicar estado con color <em>y</em> forma o texto (badge, ícono, borde).</div>
              <div>Verificar contraste al agregar cualquier par texto/fondo.</div>
            </div>
          </div>
          <div style={{ padding: 24, borderRadius: 12, background: "var(--lp-color-surface)", border: "1px solid var(--lp-color-border)", borderTop: "3px solid var(--lp-color-danger)" }}>
            <div style={{ fontSize: 12, fontWeight: 700, letterSpacing: "0.14em", textTransform: "uppercase", color: "var(--lp-color-danger-text)", marginBottom: 16 }}>Don't</div>
            <div style={{ display: "grid", gap: 12, fontSize: 14.5, lineHeight: 1.5 }}>
              <div><Code>background: #2563eb</Code> — hex crudo en un componente.</div>
              <div><Code>color: azure</Code> / <Code>aliceblue</Code> — colores con nombre CSS.</div>
              <div>Usar un primitivo (<Code>--lp-green-500</Code>) directo en la UI: no cambia con el tema.</div>
              <div>Radios o sombras ad hoc por pantalla.</div>
              <div>Quitar el outline de foco para "que quede prolijo".</div>
            </div>
          </div>
        </div>
      </section>

      {/* ---------- entregables ---------- */}
      <section id="entregables" style={{ ...S.section, padding: "56px 40px 96px" }}>
        <p style={S.eyebrow}>09</p>
        <h2 style={S.h2}>Entregables</h2>
        <p style={{ ...S.lead, margin: "0 0 32px" }}>Mapa antes → después, override de React-Bootstrap y el bloque de tokens listo para pegar.</p>

        <h3 style={{ margin: "0 0 16px", fontSize: 20, fontWeight: 600 }}>Antes → después</h3>
        <div style={{ border: "1px solid var(--lp-color-border)", borderRadius: 12, overflow: "hidden", background: "var(--lp-color-surface)", marginBottom: 48 }}>
          <div style={{ display: "grid", gridTemplateColumns: "minmax(0, 1.1fr) minmax(0, 1fr) minmax(0, 1.2fr)", gap: 16, padding: "12px 20px", background: "var(--lp-color-bg)", borderBottom: "1px solid var(--lp-color-border)", fontSize: 12, fontWeight: 600, letterSpacing: "0.06em", textTransform: "uppercase", color: "var(--lp-color-text-muted)" }}>
            <span>Dónde</span><span>Valor actual</span><span>Token destino</span>
          </div>
          {[
            ["login-container bg", "#395c91", "--lp-gray-800 (aplicado en PR #58)"],
            ["login-button · catalogo-actions", "#2563eb / #1e4fd8", "--lp-color-secondary / -secondary-hover"],
            ["botón deshabilitado", "#94a3b8", "--lp-color-disabled-bg / -disabled-text"],
            ["toast · .catalogo-error", "#dc2626", "--lp-color-danger + z-toast 1080"],
            [".nav-link · títulos", "azure / aliceblue", "--lp-color-text-inverse / --lp-color-text"],
            ["login-card shadow", "0 4px 12px rgba(0,0,0,.1)", "--lp-shadow-2"],
            ["radios sueltos", "4 / 6 / 8 px mezclados", "--lp-radius-sm / -md / -lg"],
          ].map(([donde, actual, destino], i, arr) => (
            <div key={i} style={{ display: "grid", gridTemplateColumns: "minmax(0, 1.1fr) minmax(0, 1fr) minmax(0, 1.2fr)", gap: 16, padding: "12px 20px", borderBottom: i < arr.length - 1 ? "1px solid var(--lp-color-border)" : undefined, alignItems: "center", fontSize: 13.5 }}>
              <span style={{ fontFamily: MONO, fontSize: 12.5 }}>{donde}</span>
              <span style={{ fontFamily: MONO, fontSize: 12, color: "var(--lp-color-text-muted)" }}>{actual}</span>
              <span style={{ fontFamily: MONO, fontSize: 12.5, color: "var(--lp-color-primary)" }}>{destino}</span>
            </div>
          ))}
        </div>

        <h3 style={{ margin: "0 0 16px", fontSize: 20, fontWeight: 600 }}>
          Override de React-Bootstrap · <span style={{ fontFamily: MONO, fontSize: 14, fontWeight: 400 }}>--lp-* → --bs-*</span>
        </h3>
        <div style={{ border: "1px solid var(--lp-color-border)", borderRadius: 12, overflow: "hidden", background: "var(--lp-color-surface)", marginBottom: 48 }}>
          <div style={{ display: "grid", gridTemplateColumns: "minmax(0, 1fr) minmax(0, 1fr) minmax(0, 1.4fr)", gap: 16, padding: "12px 20px", background: "var(--lp-color-bg)", borderBottom: "1px solid var(--lp-color-border)", fontSize: 12, fontWeight: 600, letterSpacing: "0.06em", textTransform: "uppercase", color: "var(--lp-color-text-muted)" }}>
            <span>Variable Bootstrap</span><span>Token lapape</span><span>Nota</span>
          </div>
          {data.bsRows.map((b, i) => (
            <div key={i} style={{ display: "grid", gridTemplateColumns: "minmax(0, 1fr) minmax(0, 1fr) minmax(0, 1.4fr)", gap: 16, padding: "10px 20px", borderBottom: i < data.bsRows.length - 1 ? "1px solid var(--lp-color-border)" : undefined, alignItems: "center" }}>
              <span style={{ fontFamily: MONO, fontSize: 12.5 }}>{b.bs}</span>
              <span style={{ fontFamily: MONO, fontSize: 12.5, color: "var(--lp-color-primary)" }}>{b.lp}</span>
              <span style={{ fontSize: 13, color: "var(--lp-color-text-muted)" }}>{b.note}</span>
            </div>
          ))}
        </div>

        <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: 16, marginBottom: 16 }}>
          <h3 style={{ margin: 0, fontSize: 20, fontWeight: 600 }}>
            Bloque de tokens · <span style={{ fontFamily: MONO, fontSize: 14, fontWeight: 400 }}>frontend/src/index.css</span>
          </h3>
          <button onClick={copyCss} style={{ ...btnBase, padding: "9px 14px", fontSize: 13, background: "var(--lp-color-primary)", color: "var(--lp-color-primary-text)" }}>
            {copied ? "Copiado ✓" : "Copiar CSS"}
          </button>
        </div>
        <pre style={{ margin: 0, padding: "20px 24px", maxHeight: 480, overflow: "auto", background: "var(--lp-gray-900)", color: "var(--lp-gray-100)", borderRadius: 12, fontFamily: MONO, fontSize: 12, lineHeight: 1.6 }}>{TOKENS_CSS}</pre>
      </section>

      <footer style={{ borderTop: "1px solid var(--lp-color-border)", background: "var(--lp-color-surface)" }}>
        <div style={{ maxWidth: 1200, margin: "0 auto", padding: "24px 40px", display: "flex", flexWrap: "wrap", gap: 16, alignItems: "center", justifyContent: "space-between", fontSize: 13, color: "var(--lp-color-text-muted)" }}>
          <span>lapape · foundations v1 — fuera de alcance: rediseño de pantallas, layout de producto, iconografía nueva.</span>
          <a href="#portada">Volver arriba ↑</a>
        </div>
      </footer>
    </div>
  );
}

/* ---------- subcomponentes ---------- */
function Code({ children }: { children: React.ReactNode }) {
  return <code style={{ fontFamily: MONO, fontSize: 12.5, background: "var(--lp-color-bg)", padding: "2px 6px", borderRadius: 4 }}>{children}</code>;
}

function inputStyle(): CSSProperties {
  return {
    width: "100%", height: 40, padding: "0 12px", borderRadius: 6,
    border: "1px solid var(--lp-color-border-strong)", background: "var(--lp-color-surface)",
    color: "var(--lp-color-text)", fontFamily: "inherit", fontSize: 14,
  };
}

function Field({ label, hint, error, tag, labelMuted, children }: { label: string; hint?: string; error?: string; tag: string; labelMuted?: boolean; children: React.ReactNode }) {
  return (
    <div style={S.card}>
      <div style={{ fontFamily: MONO, fontSize: 11, color: "var(--lp-color-text-muted)", marginBottom: 12 }}>{tag}</div>
      <label style={{ display: "block", fontSize: 14, fontWeight: 500, marginBottom: 6, color: labelMuted ? "var(--lp-color-disabled-text)" : undefined }}>{label}</label>
      {children}
      {hint && <div style={{ marginTop: 6, fontSize: 12, color: "var(--lp-color-text-muted)" }}>{hint}</div>}
      {error && (
        <div style={{ marginTop: 6, display: "flex", alignItems: "center", gap: 6, fontSize: 12, fontWeight: 500, color: "var(--lp-color-danger-text)" }}>
          <svg width={13} height={13} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2.5} strokeLinecap="round"><circle cx="12" cy="12" r="9" /><path d="M12 8v5M12 16.5v.01" /></svg>
          {error}
        </div>
      )}
    </div>
  );
}

function ControlCard({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div style={{ ...S.card, display: "grid", gap: 14 }}>
      <div style={{ fontFamily: MONO, fontSize: 11, color: "var(--lp-color-text-muted)" }}>{title}</div>
      {children}
    </div>
  );
}
function CtrlRow({ children, muted }: { children: React.ReactNode; muted?: boolean }) {
  return <label style={{ display: "flex", alignItems: "center", gap: 10, fontSize: 14, color: muted ? "var(--lp-color-disabled-text)" : undefined }}>{children}</label>;
}
const focusRing: CSSProperties = { outline: "2px solid var(--lp-color-primary)", outlineOffset: 2, boxShadow: "var(--lp-focus-ring)" };
function Box({ checked, focus, disabled }: { checked?: boolean; focus?: boolean; disabled?: boolean }) {
  const base: CSSProperties = { flex: "none", width: 18, height: 18, borderRadius: 4, border: "2px solid var(--lp-color-border-strong)", background: "var(--lp-color-surface)" };
  if (disabled) return <span style={{ ...base, border: "2px solid var(--lp-color-disabled-bg)", background: "var(--lp-color-disabled-bg)" }} />;
  if (checked) return (
    <span style={{ ...base, border: "2px solid var(--lp-color-primary)", background: "var(--lp-color-primary)", display: "inline-flex", alignItems: "center", justifyContent: "center", color: "var(--lp-color-primary-text)" }}>
      <svg width={12} height={12} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={3.5} strokeLinecap="round"><path d="m5 13 5 5L19 7" /></svg>
    </span>
  );
  return <span style={{ ...base, ...(focus ? { border: "2px solid var(--lp-color-primary)", ...focusRing } : {}) }} />;
}
function Dot({ checked, focus, disabled }: { checked?: boolean; focus?: boolean; disabled?: boolean }) {
  const base: CSSProperties = { flex: "none", width: 18, height: 18, borderRadius: "50%", border: "2px solid var(--lp-color-border-strong)", background: "var(--lp-color-surface)" };
  if (disabled) return <span style={{ ...base, border: "2px solid var(--lp-color-disabled-bg)", background: "var(--lp-color-disabled-bg)" }} />;
  if (checked) return (
    <span style={{ ...base, border: "2px solid var(--lp-color-primary)", display: "inline-flex", alignItems: "center", justifyContent: "center" }}>
      <span style={{ width: 8, height: 8, borderRadius: "50%", background: "var(--lp-color-primary)" }} />
    </span>
  );
  return <span style={{ ...base, ...(focus ? { border: "2px solid var(--lp-color-primary)", ...focusRing } : {}) }} />;
}
function Toggle({ on, focus, disabled }: { on?: boolean; focus?: boolean; disabled?: boolean }) {
  const track: CSSProperties = { flex: "none", width: 38, height: 22, borderRadius: 999, display: "inline-flex", alignItems: "center", padding: 2, background: disabled ? "var(--lp-color-disabled-bg)" : on ? "var(--lp-color-primary)" : "var(--lp-color-border-strong)", justifyContent: on ? "flex-end" : "flex-start" };
  return (
    <span style={{ ...track, ...(focus ? focusRing : {}) }}>
      <span style={{ width: 18, height: 18, borderRadius: "50%", background: disabled ? "var(--lp-color-surface)" : "#FFFFFF", boxShadow: disabled ? undefined : "var(--lp-shadow-1)" }} />
    </span>
  );
}
function Badge({ children, bg, fg, border }: { children: React.ReactNode; bg: string; fg: string; border?: boolean }) {
  return <span style={{ padding: "4px 10px", borderRadius: 999, background: bg, color: fg, fontSize: 12, fontWeight: 600, border: border ? "1px solid var(--lp-color-border)" : undefined }}>{children}</span>;
}
function Alert({ tone, title, body }: { tone: "success" | "danger" | "warning" | "info"; title: string; body: string }) {
  return (
    <div style={{ display: "flex", gap: 12, padding: "14px 16px", borderRadius: 8, background: `var(--lp-color-${tone}-subtle)`, borderLeft: `4px solid var(--lp-color-${tone})`, color: `var(--lp-color-${tone}-text)` }}>
      <svg width={18} height={18} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2.5} strokeLinecap="round" style={{ flex: "none", marginTop: 1 }}>
        {tone === "success" ? <path d="m5 13 5 5L19 7" /> : tone === "warning" ? <><path d="M12 4 2.5 20h19L12 4Z" /><path d="M12 10v4M12 17.5v.01" /></> : <><circle cx="12" cy="12" r="9" /><path d="M12 8v5M12 16.5v.01" /></>}
      </svg>
      <div>
        <strong style={{ display: "block", fontSize: 14, fontWeight: 600 }}>{title}</strong>
        <span style={{ fontSize: 13 }}>{body}</span>
      </div>
    </div>
  );
}

function ButtonMatrix() {
  const rows: { name: string; render: (state: string) => CSSProperties; label: string }[] = [
    { name: "primary", label: "Guardar", render: (st) => ({ background: st === "hover" || st === "active" ? "var(--lp-color-primary-hover)" : "var(--lp-color-primary)", color: "var(--lp-color-primary-text)" }) },
    { name: "secondary", label: "Ingresar", render: (st) => ({ background: st === "hover" || st === "active" ? "var(--lp-color-secondary-hover)" : "var(--lp-color-secondary)", color: "var(--lp-color-text-inverse)" }) },
    { name: "danger", label: "Eliminar", render: (st) => ({ background: st === "hover" || st === "active" ? "var(--lp-color-danger-text)" : "var(--lp-color-danger)", color: "#FFFFFF" }) },
  ];
  const states = ["default", "hover", "active", "focus", "disabled", "loading"];
  return (
    <div style={{ border: "1px solid var(--lp-color-border)", borderRadius: 12, background: "var(--lp-color-surface)", overflow: "hidden" }}>
      <div style={{ display: "grid", gridTemplateColumns: "104px repeat(6, minmax(0, 1fr))", gap: 12, padding: "12px 20px", background: "var(--lp-color-bg)", borderBottom: "1px solid var(--lp-color-border)", fontFamily: MONO, fontSize: 11, color: "var(--lp-color-text-muted)" }}>
        <span />
        {states.map((s) => <span key={s}>{s}</span>)}
      </div>
      {rows.map((row, ri) => (
        <div key={row.name} style={{ display: "grid", gridTemplateColumns: "104px repeat(6, minmax(0, 1fr))", gap: 12, padding: "16px 20px", borderBottom: ri < rows.length - 1 ? "1px solid var(--lp-color-border)" : undefined, alignItems: "center" }}>
          <span style={{ fontFamily: MONO, fontSize: 12, fontWeight: 600 }}>{row.name}</span>
          {states.map((st) => {
            const isDisabled = st === "disabled";
            const style: CSSProperties = {
              ...btnBase,
              ...(isDisabled ? { background: "var(--lp-color-disabled-bg)", color: "var(--lp-color-disabled-text)", cursor: "not-allowed" } : row.render(st)),
              ...(st === "focus" ? focusRing : {}),
              ...(st === "active" ? { transform: "translateY(1px)", boxShadow: "inset 0 2px 4px rgba(15,23,42,0.22)" } : {}),
              ...(st === "loading" ? { opacity: 0.85, cursor: "progress" } : {}),
            };
            return (
              <button key={st} disabled={isDisabled} style={style}>
                {st === "loading" ? <><Spinner />{row.label}</> : row.label}
              </button>
            );
          })}
        </div>
      ))}
    </div>
  );
}
