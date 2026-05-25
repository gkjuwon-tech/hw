/**
 * Line Tune.
 *
 * Cognex In-Sight-style detailed control panel for a single conveyor
 * line. Surfaces every knob the backend supports as a discrete control:
 *
 *   - Anomaly thresholds (score + hit count)
 *   - Recipe selection (loads thresholds in one click)
 *   - Customer tag / labelling
 *   - Live verdict feedback while you tweak
 *
 * The slider/dial set is intentionally dense. Operators trained on
 * Cognex EasyBuilder will find this familiar.
 */

import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import { PageHeader } from "../components/PageHeader";
import { Spark } from "../components/Spark";
import { api } from "../lib/api";
import { subscribeLineEvents, type Subscription } from "../lib/sse";
import type { ApiError, InspectionEvent, Line, Recipe } from "../lib/types";

export interface LineTuneProps {
  lineId: string;
  onBack: () => void;
}

interface DraftState {
  customer_tag: string;
  threshold_score: number;
  threshold_hits: number;
}

const HISTORY_LEN = 240;

export function LineTune({ lineId, onBack }: LineTuneProps): JSX.Element {
  const [line, setLine] = useState<Line | null>(null);
  const [draft, setDraft] = useState<DraftState | null>(null);
  const [recipes, setRecipes] = useState<Recipe[]>([]);
  const [pickedRecipe, setPickedRecipe] = useState("");
  const [err, setErr] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState<string | null>(null);

  const [latest, setLatest] = useState<InspectionEvent | null>(null);
  const [history, setHistory] = useState<number[]>([]);
  const subRef = useRef<Subscription | null>(null);

  const load = useCallback(async (): Promise<void> => {
    setErr(null);
    try {
      const [row, recs, recent] = await Promise.all([
        api.getLine(lineId),
        api.listRecipes(lineId),
        api.recentEvents(lineId).catch(() => []),
      ]);
      setLine(row);
      setRecipes(recs);
      setDraft({
        customer_tag: row.customer_tag,
        threshold_score: row.threshold_score ?? 3.0,
        threshold_hits: row.threshold_hits ?? 8,
      });
      setHistory(recent.map((r) => r.score));
      if (recent.length > 0) setLatest(recent[recent.length - 1] ?? null);
    } catch (e) {
      setErr((e as ApiError).message);
    }
  }, [lineId]);

  useEffect(() => {
    void load();
  }, [load]);

  // Pull threshold defaults from /v1/lines (it returns them too).
  useEffect(() => {
    if (line && draft) {
      // re-sync if line refetched
      setDraft((d) =>
        d
          ? {
              ...d,
              customer_tag: line.customer_tag,
            }
          : d,
      );
    }
  }, [line, draft]);

  // Live anomaly score feed.
  useEffect(() => {
    let cancelled = false;
    void subscribeLineEvents(
      lineId,
      (ev) => {
        setLatest(ev);
        setHistory((prev) => {
          const next = prev.concat(ev.score);
          if (next.length > HISTORY_LEN) next.shift();
          return next;
        });
      },
      () => {},
    ).then((s) => {
      if (cancelled) {
        s.close();
        return;
      }
      subRef.current = s;
    });
    return () => {
      cancelled = true;
      subRef.current?.close();
      subRef.current = null;
    };
  }, [lineId]);

  const save = async (): Promise<void> => {
    if (!draft) return;
    setBusy(true);
    setErr(null);
    setMsg(null);
    try {
      const updated = await api.updateLine(lineId, {
        customer_tag: draft.customer_tag,
        threshold_score: draft.threshold_score,
        threshold_hits: draft.threshold_hits,
      });
      setLine(updated);
      setMsg("Line settings saved.");
    } catch (e) {
      setErr((e as ApiError).message);
    } finally {
      setBusy(false);
    }
  };

  const loadRecipe = async (): Promise<void> => {
    if (!pickedRecipe) return;
    setBusy(true);
    setErr(null);
    setMsg(null);
    try {
      const r = await api.loadRecipe(lineId, pickedRecipe);
      setMsg(`Loaded recipe "${r.recipe_name}".`);
      setDraft((d) =>
        d
          ? {
              ...d,
              threshold_score: r.threshold_score,
              threshold_hits: r.threshold_hits,
            }
          : d,
      );
      await load();
    } catch (e) {
      setErr((e as ApiError).message);
    } finally {
      setBusy(false);
    }
  };

  const verdictColor = useMemo(() => {
    if (!latest) return "var(--muted)";
    return latest.passed ? "var(--signal-good)" : "var(--signal-bad)";
  }, [latest]);

  return (
    <div className="page">
      <PageHeader
        eyebrow={`TUNE · ${lineId}`}
        title={line?.customer_tag || "Loading…"}
        lede="Cognex-grade inspection knobs. Adjust thresholds live, swap recipes, watch the verdict change in real time."
        actions={
          <button type="button" className="btn" onClick={onBack}>
            ← Back
          </button>
        }
      />

      {err ? (
        <div className="banner">
          <b>ERR</b>&nbsp;{err}
        </div>
      ) : null}
      {msg ? (
        <div className="banner" style={{ background: "#1a3", color: "#fff" }}>
          <b>OK</b>&nbsp;{msg}
        </div>
      ) : null}

      <div className="grid grid--detail">
        <section className="card">
          <header className="card__head">
            <h3 className="h3">Thresholds</h3>
            <span className="mono" style={{ fontSize: 11, color: "var(--muted)" }}>
              PATCH /v1/lines/{lineId}
            </span>
          </header>
          <div className="card__body" style={{ display: "grid", gap: 10 }}>
            <Slider
              label="SCORE THRESHOLD"
              hint="Any inspection above this is suspicious. Higher = stricter."
              value={draft?.threshold_score ?? 3.0}
              min={0}
              max={20}
              step={0.05}
              onChange={(v) => setDraft((d) => (d ? { ...d, threshold_score: v } : d))}
              disabled={busy}
            />
            <Slider
              label="HIT COUNT THRESHOLD"
              hint="Minimum number of suspicious cells before failing the part."
              value={draft?.threshold_hits ?? 8}
              min={0}
              max={200}
              step={1}
              onChange={(v) => setDraft((d) => (d ? { ...d, threshold_hits: v } : d))}
              disabled={busy}
              integer
            />
            <label className="field">
              <span>CUSTOMER TAG</span>
              <input
                type="text"
                value={draft?.customer_tag ?? ""}
                onChange={(e) =>
                  setDraft((d) => (d ? { ...d, customer_tag: e.target.value } : d))
                }
                disabled={busy}
              />
            </label>
            <div style={{ display: "flex", gap: 8 }}>
              <button
                type="button"
                className="btn btn--primary"
                onClick={() => void save()}
                disabled={busy || !draft}
              >
                Save
              </button>
              <button
                type="button"
                className="btn"
                onClick={() => void load()}
                disabled={busy}
              >
                Reload from server
              </button>
            </div>
          </div>
        </section>

        <section className="card">
          <header className="card__head">
            <h3 className="h3">Live verdict</h3>
            <span className="mono" style={{ fontSize: 11, color: "var(--muted)" }}>
              {history.length} pts
            </span>
          </header>
          <div className="card__body">
            <Spark values={history} threshold={draft?.threshold_score ?? 3.0} />
            <dl className="kv" style={{ marginTop: 12 }}>
              <div>
                <dt>Latest score</dt>
                <dd>{latest ? latest.score.toFixed(3) : "—"}</dd>
              </div>
              <div>
                <dt>Drift Z</dt>
                <dd>{latest?.drift_z != null ? latest.drift_z.toFixed(2) : "—"}</dd>
              </div>
              <div>
                <dt>Verdict</dt>
                <dd style={{ color: verdictColor, fontWeight: 700 }}>
                  {latest ? (latest.passed ? "PASS" : "REJECT") : "—"}
                </dd>
              </div>
              <div>
                <dt>Mesh geometry</dt>
                <dd>
                  {line ? `${line.rows} × ${line.cols}` : "—"}
                </dd>
              </div>
            </dl>
          </div>
        </section>
      </div>

      <section className="card">
        <header className="card__head">
          <h3 className="h3">Load recipe into this line</h3>
          <span className="mono" style={{ fontSize: 11, color: "var(--muted)" }}>
            POST /v1/lines/{lineId}/load_recipe
          </span>
        </header>
        <div
          className="card__body"
          style={{ display: "grid", gridTemplateColumns: "1fr auto", gap: 8, alignItems: "end" }}
        >
          <label className="field">
            <span>RECIPE</span>
            <select
              className="mono"
              value={pickedRecipe}
              onChange={(e) => setPickedRecipe(e.target.value)}
              disabled={busy}
            >
              <option value="">— choose —</option>
              {recipes.map((r) => (
                <option key={r.id} value={r.id}>
                  {r.name} · score={r.threshold_score} hits={r.threshold_hits} · trig=
                  {r.trigger_mode}
                </option>
              ))}
            </select>
          </label>
          <button
            type="button"
            className="btn btn--primary"
            disabled={busy || !pickedRecipe}
            onClick={() => void loadRecipe()}
          >
            Apply recipe
          </button>
        </div>
      </section>
    </div>
  );
}

interface SliderProps {
  label: string;
  hint?: string;
  value: number;
  min: number;
  max: number;
  step: number;
  onChange: (v: number) => void;
  disabled?: boolean;
  integer?: boolean;
}

function Slider({
  label,
  hint,
  value,
  min,
  max,
  step,
  onChange,
  disabled,
  integer,
}: SliderProps): JSX.Element {
  return (
    <div>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline" }}>
        <span className="mono" style={{ fontSize: 11, letterSpacing: "0.05em" }}>
          {label}
        </span>
        <span className="mono" style={{ fontSize: 12 }}>
          {integer ? Math.round(value) : value.toFixed(2)}
        </span>
      </div>
      <input
        type="range"
        min={min}
        max={max}
        step={step}
        value={value}
        onChange={(e) => onChange(parseFloat(e.target.value))}
        disabled={disabled}
        style={{ width: "100%" }}
      />
      <div
        style={{
          display: "flex",
          justifyContent: "space-between",
          fontSize: 10,
          color: "var(--muted)",
        }}
      >
        <span>{min}</span>
        <span>{hint}</span>
        <span>{max}</span>
      </div>
    </div>
  );
}
