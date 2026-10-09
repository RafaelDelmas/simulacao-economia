/**
 * Gráficos do mercado desenhados à mão em SVG — sem dependência de lib de
 * charts (mais leve no celular e o visual fica nosso).
 *
 * Pontos: [{ t: Date|number, p: number }]
 */
import { useTranslation } from "react-i18next";

import { localeAtual } from "../i18n/index.js";

function escala(points, w, h, padY) {
  if (!points || points.length < 2) return null;

  let min = Infinity;
  let max = -Infinity;
  for (const p of points) {
    if (p.p < min) min = p.p;
    if (p.p > max) max = p.p;
  }
  if (!isFinite(min) || !isFinite(max)) return null;

  if (max - min < 1e-9) {
    // linha chapada: abre um pouco a régua pra conseguir desenhar
    const folga = Math.max(Math.abs(max) * 0.01, 0.5);
    min -= folga;
    max += folga;
  }

  const n = points.length;
  const x = (i) => (n <= 1 ? w : (i / (n - 1)) * w);
  const y = (v) => padY + (1 - (v - min) / (max - min)) * (h - padY * 2);

  let d = "";
  points.forEach((p, i) => {
    d += `${i === 0 ? "M" : "L"}${x(i).toFixed(2)},${y(p.p).toFixed(2)}`;
  });

  return { d, min, max, y, x };
}

/** Minigráfico dentro do card do commodity. */
export function Sparkline({ points, up = 0, height = 34 }) {
  const { t } = useTranslation();
  const W = 120;
  const H = height;
  const esc = escala(points || [], W, H, 3);

  if (!esc) {
    return (
      <div className="chart-empty" style={{ height: H }}>
        {t("coletando…")}
      </div>
    );
  }

  const cor = up > 0 ? "#2fd47b" : up < 0 ? "#ff5f74" : "#8b9ab0";
  const ultimo = points[points.length - 1];

  return (
    <div className="spark chart-box">
      <svg
        viewBox={`0 0 ${W} ${H}`}
        height={H}
        preserveAspectRatio="none"
        role="img"
        aria-label={t("evolução do preço")}
      >
        <path
          d={`${esc.d} L${W},${H} L0,${H} Z`}
          fill={cor}
          opacity="0.13"
        />
        <path
          d={esc.d}
          fill="none"
          stroke={cor}
          strokeWidth="2"
          strokeLinejoin="round"
          strokeLinecap="round"
          vectorEffect="non-scaling-stroke"
        />
        <circle
          cx={esc.x(points.length - 1)}
          cy={esc.y(ultimo.p)}
          r="3.4"
          fill={cor}
          stroke="#0d121a"
          strokeWidth="1.5"
          vectorEffect="non-scaling-stroke"
        />
      </svg>
    </div>
  );
}

/** Gráfico grande da tela do commodity. */
export function PriceChart({ points, height = 168, cor = "#f2c14e" }) {
  const { t } = useTranslation();
  const W = 320;
  const H = height;
  const esc = escala(points || [], W, H, 12);
  const loc = localeAtual();

  if (!esc) {
    return (
      <div className="chart-empty" style={{ height: H }}>
        <span>
          <span className="live-dot" />
          {t("coletando histórico de preços…")}
        </span>
      </div>
    );
  }

  const ultimo = points[points.length - 1];
  const primeiro = points[0];
  const variacao =
    primeiro && primeiro.p > 0
      ? ((ultimo.p - primeiro.p) / primeiro.p) * 100
      : 0;

  return (
    <div>
      <div className="chart-box">
        <svg
          viewBox={`0 0 ${W} ${H}`}
          height={H}
          preserveAspectRatio="none"
          role="img"
          aria-label={t("gráfico de preço")}
        >
          <defs>
            <linearGradient id={`fill-${cor.slice(1)}`} x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor={cor} stopOpacity="0.34" />
              <stop offset="100%" stopColor={cor} stopOpacity="0" />
            </linearGradient>
          </defs>

          {[0.25, 0.5, 0.75].map((f) => (
            <line
              key={f}
              x1="0"
              x2={W}
              y1={H * f}
              y2={H * f}
              stroke="#22303f"
              strokeWidth="1"
              strokeDasharray="3 5"
              vectorEffect="non-scaling-stroke"
            />
          ))}

          <path
            d={`${esc.d} L${W},${H} L0,${H} Z`}
            fill={`url(#fill-${cor.slice(1)})`}
          />
          <path
            d={esc.d}
            fill="none"
            stroke={cor}
            strokeWidth="2.2"
            strokeLinejoin="round"
            strokeLinecap="round"
            vectorEffect="non-scaling-stroke"
          />
          <circle
            cx={esc.x(points.length - 1)}
            cy={esc.y(ultimo.p)}
            r="4.5"
            fill={cor}
            stroke="#0d121a"
            strokeWidth="2"
            vectorEffect="non-scaling-stroke"
          />
        </svg>
      </div>

      <div className="chart-meta num">
        <span>
          {t("mín")} {esc.min.toLocaleString(loc, { maximumFractionDigits: 2 })}
        </span>
        <span className={variacao > 0 ? "up" : variacao < 0 ? "down" : ""}>
          {t("{{n}} pontos ·", { n: points.length })}{" "}
          {variacao >= 0 ? "▲" : "▼"}{" "}
          {Math.abs(variacao).toLocaleString(loc, {
            maximumFractionDigits: 2,
          })}
          %
        </span>
        <span>
          {t("máx")} {esc.max.toLocaleString(loc, { maximumFractionDigits: 2 })}
        </span>
      </div>
    </div>
  );
}
