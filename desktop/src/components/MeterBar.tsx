/**
 * MeterBar — a tiny horizontal gauge for percentages or normalised
 * scalar values (CPU/GPU load, RAM utilisation, temperature, etc.).
 *
 * The fill colour transitions through good → warn → bad based on the
 * `value / max` ratio relative to the supplied warn/danger thresholds.
 */

export interface MeterBarProps {
  label: string;
  value: number;
  max: number;
  warnAt?: number;
  dangerAt?: number;
  unit?: string;
  digits?: number;
}

export function MeterBar({
  label,
  value,
  max,
  warnAt,
  dangerAt,
  unit = "",
  digits = 1,
}: MeterBarProps): JSX.Element {
  const safeMax = max > 0 ? max : 1;
  const pct = Math.min(1, Math.max(0, value / safeMax));
  const ratio = pct * 100;
  const warn = warnAt ?? 70;
  const danger = dangerAt ?? 90;
  let state: "good" | "warn" | "bad" = "good";
  if (ratio >= danger) state = "bad";
  else if (ratio >= warn) state = "warn";

  return (
    <div className="meter" data-state={state}>
      <span className="meter__label">{label}</span>
      <span className="meter__track">
        <span className="meter__fill" style={{ width: `${ratio.toFixed(1)}%` }} />
      </span>
      <span className="meter__value">
        {value.toFixed(digits)}
        {unit ? ` ${unit}` : ""}
      </span>
    </div>
  );
}
