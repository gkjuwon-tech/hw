import { useMemo } from "react";

export interface HeatmapProps {
  /** rows × cols grid of 0..1 values (or null for "no data yet"). */
  grid: number[][] | null;
  rows: number;
  cols: number;
}

function colorFor(v: number): string {
  // Map 0..1 → ink(charcoal) → lime. Anything above 0.85 saturates to lime,
  // anything below 0.05 stays at the matte panel color. We deliberately do
  // NOT use a rainbow ramp — the landing page palette is two-tone industrial.
  const clamped = Math.min(1, Math.max(0, v));
  if (clamped < 0.05) return "#1f2220";
  // interpolate between #2e3230 (ink-3) and #b5e853 (lime).
  const t = (clamped - 0.05) / 0.95;
  const r = Math.round(0x2e + (0xb5 - 0x2e) * t);
  const g = Math.round(0x32 + (0xe8 - 0x32) * t);
  const b = Math.round(0x30 + (0x53 - 0x30) * t);
  return `rgb(${r}, ${g}, ${b})`;
}

/**
 * 16×16 (or whatever rows/cols) pressure heatmap, rendered as a CSS Grid
 * of equal-aspect cells. Lives inside an ink-card so the lime ramp pops
 * the way it does in the landing page's `.section--photo` regions.
 */
export function Heatmap({ grid, rows, cols }: HeatmapProps): JSX.Element {
  const cells = useMemo(() => {
    if (!grid || grid.length !== rows) {
      // No data yet — show a uniform dim grid.
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
