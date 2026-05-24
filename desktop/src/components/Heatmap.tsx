import { useMemo } from "react";

export interface HeatmapProps {
  /** rows × cols grid of 0..1 values (or null for "no data yet"). */
  grid: number[][] | null;
  rows: number;
  cols: number;
}

/**
 * Map a 0..1 value to the industrial LUT:
 *
 *   v < 0.05  → near-black (machine off / no signal)
 *   0..0.40   → grayscale ramp (#1a1a1a → #8a8a8a)  — "all clear" range
 *   0.40..1.0 → red ramp (#a0a0a0 → #d40000)         — alarm region
 *
 * This is deliberately NOT a rainbow / viridis ramp: machine-vision
 * operators expect "red = problem" to be the only non-gray colour on
 * the screen.
 */
function colorFor(v: number): string {
  const clamped = Math.min(1, Math.max(0, v));
  if (clamped < 0.05) return "#0a0a0a";
  if (clamped < 0.4) {
    const t = (clamped - 0.05) / 0.35;
    const g = Math.round(0x1a + (0x8a - 0x1a) * t);
    return `rgb(${g}, ${g}, ${g})`;
  }
  const t = (clamped - 0.4) / 0.6;
  const r = Math.round(0xa0 + (0xd4 - 0xa0) * t);
  const g = Math.round(0xa0 * (1 - t));
  const b = Math.round(0xa0 * (1 - t));
  return `rgb(${r}, ${g}, ${b})`;
}

/**
 * rows × cols pressure heatmap rendered as a CSS Grid of equal-aspect
 * cells. Lives inside a `card--ink`-flavoured card so the red alarm
 * cells are immediately legible against pure black.
 */
export function Heatmap({ grid, rows, cols }: HeatmapProps): JSX.Element {
  const cells = useMemo(() => {
    if (!grid || grid.length !== rows) {
      return Array.from({ length: rows * cols }, () => null);
    }
    const flat: Array<number | null> = [];
    for (let r = 0; r < rows; r++) {
      const row = grid[r];
      if (!row) {
        for (let c = 0; c < cols; c++) flat.push(null);
        continue;
      }
      for (let c = 0; c < cols; c++) {
        const v = row[c];
        flat.push(typeof v === "number" ? v : null);
      }
    }
    return flat;
  }, [grid, rows, cols]);

  return (
    <div
      className="heatmap"
      style={{
        gridTemplateColumns: `repeat(${cols}, 1fr)`,
        gridTemplateRows: `repeat(${rows}, 1fr)`,
      }}
      role="img"
      aria-label={`Tactile heatmap, ${rows} rows by ${cols} columns`}
    >
      {cells.map((v, i) => (
        <span
          key={i}
          className="heatmap__cell"
          style={{ background: v === null ? undefined : colorFor(v) }}
        />
      ))}
    </div>
  );
}
