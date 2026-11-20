// Chart.js helpers. Charts always have a text alternative (aria-label + data table/summary nearby).
// Colours are read from CSS custom properties so charts follow the light/dark theme; every chart is
// rebuilt from its config builder when the theme changes.
const LEVEL_VAR = {
  low: "--c-low", moderate: "--c-moderate", high: "--c-high", critical: "--c-critical",
  insufficient_data: "--c-insufficient", unavailable: "--c-unavailable", primary: "--series-1", secondary: "--series-3",
};
const cssVar = (name) => getComputedStyle(document.documentElement).getPropertyValue(name).trim();
const series = () => Array.from({ length: 9 }, (_, i) => cssVar(`--series-${i + 1}`));

/** Live, theme-aware colour lookup (kept for compatibility with the previous constant export). */
export const COLORS = new Proxy({}, { get: (_, k) => (LEVEL_VAR[k] ? cssVar(LEVEL_VAR[k]) : undefined) });

function alpha(color, a) {
  const m = /^#([0-9a-f]{6})$/i.exec(color);
  if (!m) return color;
  const n = parseInt(m[1], 16);
  return `rgba(${(n >> 16) & 255}, ${(n >> 8) & 255}, ${n & 255}, ${a})`;
}

function applyDefaults() {
  const C = window.Chart;
  const text = cssVar("--chart-text"), grid = cssVar("--chart-grid");
  C.defaults.font.family = getComputedStyle(document.body).fontFamily;
  C.defaults.font.size = 12;
  C.defaults.color = text;
  C.defaults.borderColor = grid;
  // Mutate (never replace) the animation defaults: replacing the object drops `easing` and breaks Chart.js.
  if (matchMedia("(prefers-reduced-motion: reduce)").matches) C.defaults.animation = false;
  else if (C.defaults.animation) C.defaults.animation.duration = 500;
  Object.assign(C.defaults.plugins.tooltip, {
    backgroundColor: cssVar("--surface"), titleColor: cssVar("--text"), bodyColor: cssVar("--text-2"),
    borderColor: cssVar("--border-strong"), borderWidth: 1, padding: 10, cornerRadius: 10, boxPadding: 4,
    usePointStyle: true, titleFont: { weight: "600" },
  });
  Object.assign(C.defaults.plugins.legend.labels, { usePointStyle: true, pointStyle: "circle", boxWidth: 8, boxHeight: 8, padding: 16 });
}

const registry = new Map(); // canvas -> { chart, build }

function make(canvas, build) {
  if (!window.Chart || !canvas) return null;
  registry.get(canvas)?.chart.destroy();
  for (const [c, e] of registry) if (!c.isConnected) { e.chart.destroy(); registry.delete(c); } // canvases removed by a re-render
  applyDefaults();
  const chart = new window.Chart(canvas, build());
  registry.set(canvas, { chart, build });
  return chart;
}

document.addEventListener("saews:themechange", () => {
  if (!window.Chart) return;
  applyDefaults();
  for (const [canvas, entry] of registry) {
    entry.chart.destroy();
    if (!canvas.isConnected) { registry.delete(canvas); continue; }
    entry.chart = new window.Chart(canvas, entry.build());
  }
});

const axes = (extra = {}) => ({
  x: { grid: { display: false }, border: { display: false }, ...extra.x },
  y: { beginAtZero: true, border: { display: false }, grid: { color: cssVar("--chart-grid") }, ...extra.y },
});
const baseOptions = () => ({ responsive: true, maintainAspectRatio: false, interaction: { mode: "index", intersect: false } });

export function riskBar(canvas, labels, values, levels) {
  return make(canvas, () => ({
    type: "bar",
    data: { labels, datasets: [{ label: "Students", data: values, backgroundColor: levels.map((l) => COLORS[l]),
      borderWidth: 0, borderRadius: 8, borderSkipped: false, maxBarThickness: 56 }] },
    options: { ...baseOptions(), plugins: { legend: { display: false } }, scales: axes({ y: { ticks: { precision: 0 } } }) },
  }));
}

export function stackedLevels(canvas, labels, seriesByLevel) {
  return make(canvas, () => ({
    type: "bar",
    data: { labels, datasets: Object.entries(seriesByLevel).map(([lvl, data]) => ({
      label: lvl.replace("_", " "), data, backgroundColor: COLORS[lvl], borderWidth: 0, borderRadius: 3, maxBarThickness: 56 })) },
    options: { ...baseOptions(), scales: axes({ x: { stacked: true }, y: { stacked: true, ticks: { precision: 0 } } }) },
  }));
}

export function line(canvas, labels, datasets, { yMax, yFormat } = {}) {
  return make(canvas, () => {
    const palette = series();
    const single = datasets.length === 1;
    return {
      type: "line",
      data: { labels, datasets: datasets.map((d, i) => {
        const color = palette[i % palette.length];
        return { cubicInterpolationMode: "monotone", pointRadius: 3, pointHoverRadius: 5, borderWidth: 2.25, borderColor: color, pointBackgroundColor: color,
          pointBorderColor: cssVar("--surface"), pointBorderWidth: 1.5, spanGaps: true, fill: single,
          backgroundColor: single ? (ctx) => {
            const { chart } = ctx; const area = chart.chartArea;
            if (!area) return alpha(color, 0.12);
            const g = chart.ctx.createLinearGradient(0, area.top, 0, area.bottom);
            g.addColorStop(0, alpha(color, 0.28)); g.addColorStop(1, alpha(color, 0));
            return g;
          } : color,
          ...d };
      }) },
      options: { ...baseOptions(), plugins: { legend: { display: !single } },
        scales: axes({ y: { max: yMax, ticks: yFormat ? { callback: yFormat } : {} } }) },
    };
  });
}

export function doughnut(canvas, labels, values, colors) {
  return make(canvas, () => ({
    type: "doughnut",
    data: { labels, datasets: [{ data: values, backgroundColor: colors, borderWidth: 2, borderColor: cssVar("--surface"), hoverOffset: 6 }] },
    options: { ...baseOptions(), cutout: "68%", plugins: { legend: { position: "bottom" } } },
  }));
}
