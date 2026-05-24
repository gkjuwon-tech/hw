export interface SparkProps {
  values: ReadonlyArray<number>;
  /** Optional threshold line. Drawn dashed in lime. */
  threshold?: number | undefined;
  /** Ink-on-paper (default) or paper-on-ink. */
  variant?: "paper" | "ink";
}

/**
 * A 96px-tall sparkline. SVG path interpolated from `values`. Threshold
 * is drawn as a horizontal dashed line. Matches the landing page's
 * preference for monochrome line work with a single lime accent.
 */
export function Spark({ values, threshold, variant = "paper" }: SparkProps): JSX.Element {
  const w = 600;
  const h = 96;
  const padX = 4;
  const padY = 8;
  const inkClass = variant === "ink" ? "spark spark--ink" : "spark";

  if (values.length < 2) {
    return (
      <div className={inkClass} aria-label="Score timeline (no data)">
        <svg viewBox={`0 0 ${w} ${h}`} width="100%" height="100%" preserveAspectRatio="none" />
      </div>
    );
  }

  const max = Math.max(1, ...values);
  const min = Math.min(0, ...values);
  const range = max - min || 1;

  const pts = values
    .map((v, i) => {
      const x = padX + (i / (values.length - 1)) * (w - 2 * padX);
      const y = h - padY - ((v - min) / range) * (h - 2 * padY);
      return `${x.toFixed(1)},${y.toFixed(1)}`;
    })
    .join(" ");

  const thresholdY =
    threshold !== undefined
      ? h - padY - ((threshold - min) / range) * (h - 2 * padY)
      : null;

  const stroke = variant === "ink" ? "#ecebe5" : "#1f2220";

  return (
    <div className={inkClass} aria-label="Anomaly score timeline">
      <svg
        viewBox={`0 0 ${w} ${h}`}
        width="100%"
        height="100%"
        preserveAspectRatio="none"
      >
        {thresholdY !== null && (
          <line
            x1={padX}
            x2={w - padX}
            y1={thresholdY}
            y2={thresholdY}
            stroke="#b5e853"
            strokeWidth="1"
            strokeDasharray="3 4"
          />
        )}
        <polyline points={pts} fill="none" stroke={stroke} strokeWidth="1.25" />
      </svg>
    </div>
  );
}
