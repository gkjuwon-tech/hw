/**
 * Recipes list.
 *
 * Inventory of saved per-product inspection configs. Each recipe is a
 * named bundle of thresholds, ROI, preprocessing, blob analysis, and
 * trigger settings. Operators swap recipes when changing products.
 *
 * Cognex In-Sight calls these "Jobs"; we call them Recipes because the
 * tactile interpretation is closer to a chemistry recipe than a
 * machine-vision job.
 */

import { useEffect, useState } from "react";

import { PageHeader } from "../components/PageHeader";
import { api } from "../lib/api";
import type { ApiError, Line, Recipe, TriggerMode } from "../lib/types";

export interface RecipesListProps {
  lines: Line[];
}

const DEFAULT_NEW: Pick<Recipe, "name" | "product_sku" | "description"> = {
  name: "",
  product_sku: "",
  description: "",
};

export function RecipesList({ lines }: RecipesListProps): JSX.Element {
  const [recipes, setRecipes] = useState<Recipe[]>([]);
  const [err, setErr] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [selected, setSelected] = useState<string | null>(null);
  const [editing, setEditing] = useState<Recipe | null>(null);

  // create form
  const [draft, setDraft] = useState(DEFAULT_NEW);

  // load-into-line form
  const [loadLine, setLoadLine] = useState("");
  const [loadMsg, setLoadMsg] = useState<string | null>(null);

  const refresh = async (): Promise<void> => {
    setErr(null);
    try {
      const rs = await api.listRecipes();
      setRecipes(rs);
    } catch (e) {
      setErr((e as ApiError).message);
    }
  };

  useEffect(() => {
    void refresh();
  }, []);

  useEffect(() => {
    if (selected) {
      const r = recipes.find((x) => x.id === selected);
      setEditing(r ? { ...r } : null);
    } else {
      setEditing(null);
    }
  }, [selected, recipes]);

  const create = async (): Promise<void> => {
    if (!draft.name.trim()) {
      setErr("recipe name required");
      return;
    }
    setBusy(true);
    setErr(null);
    try {
      const r = await api.createRecipe({
        name: draft.name.trim(),
        product_sku: draft.product_sku.trim(),
        description: draft.description.trim(),
      });
      setDraft(DEFAULT_NEW);
      await refresh();
      setSelected(r.id);
    } catch (e) {
      setErr((e as ApiError).message);
    } finally {
      setBusy(false);
    }
  };

  const save = async (): Promise<void> => {
    if (!editing) return;
    setBusy(true);
    setErr(null);
    try {
      await api.updateRecipe(editing.id, {
        name: editing.name,
        product_sku: editing.product_sku,
        description: editing.description,
        threshold_score: editing.threshold_score,
        threshold_hits: editing.threshold_hits,
        sigma_threshold: editing.sigma_threshold,
        drift_alert_z: editing.drift_alert_z,
        roi_x0: editing.roi_x0,
        roi_y0: editing.roi_y0,
        roi_x1: editing.roi_x1,
        roi_y1: editing.roi_y1,
        gain: editing.gain,
        gamma: editing.gamma,
        sharpen: editing.sharpen,
        denoise: editing.denoise,
        blob_min_area: editing.blob_min_area,
        blob_max_area: editing.blob_max_area,
        rotation_tolerance_deg: editing.rotation_tolerance_deg,
        scale_tolerance_pct: editing.scale_tolerance_pct,
        trigger_mode: editing.trigger_mode,
        debounce_ms: editing.debounce_ms,
        reject_queue_depth: editing.reject_queue_depth,
        strobe_duty_pct: editing.strobe_duty_pct,
        strobe_delay_us: editing.strobe_delay_us,
        logic_dsl: editing.logic_dsl,
      });
      await refresh();
    } catch (e) {
      setErr((e as ApiError).message);
    } finally {
      setBusy(false);
    }
  };

  const remove = async (id: string): Promise<void> => {
    setBusy(true);
    setErr(null);
    try {
      await api.deleteRecipe(id);
      if (selected === id) setSelected(null);
      await refresh();
    } catch (e) {
      setErr((e as ApiError).message);
    } finally {
      setBusy(false);
    }
  };

  const loadIntoLine = async (): Promise<void> => {
    if (!editing || !loadLine) return;
    setBusy(true);
    setErr(null);
    setLoadMsg(null);
    try {
      const r = await api.loadRecipe(loadLine, editing.id);
      setLoadMsg(`Loaded "${r.recipe_name}" into ${r.line_id}.`);
    } catch (e) {
      setErr((e as ApiError).message);
    } finally {
      setBusy(false);
    }
  };

  const update = <K extends keyof Recipe>(k: K, v: Recipe[K]): void => {
    setEditing((prev) => (prev ? { ...prev, [k]: v } : prev));
  };

  return (
    <div className="page">
      <PageHeader
        eyebrow="RECIPES"
        title="Per-product inspection configs"
        lede="Named bundles of thresholds, ROI, preprocessing, blob analysis, and trigger pacing. Swap recipes to change products on the same line without re-teaching."
        actions={
          <button type="button" className="btn" onClick={() => void refresh()}>
            Refresh
          </button>
        }
      />

      {err ? (
        <div className="banner">
          <b>ERR</b>&nbsp;{err}
        </div>
      ) : null}

      <section className="card">
        <header className="card__head">
          <h3 className="h3">Create recipe</h3>
          <span className="mono" style={{ fontSize: 11, color: "var(--muted)" }}>
            POST /v1/recipes
          </span>
        </header>
        <div
          className="card__body"
          style={{ display: "grid", gridTemplateColumns: "2fr 1fr 2fr auto", gap: 8, alignItems: "end" }}
        >
          <label className="field">
            <span>NAME</span>
            <input
              type="text"
              value={draft.name}
              onChange={(e) => setDraft({ ...draft, name: e.target.value })}
              placeholder="Bread loaf 500g"
              disabled={busy}
            />
          </label>
          <label className="field">
            <span>SKU</span>
            <input
              type="text"
              value={draft.product_sku}
              onChange={(e) => setDraft({ ...draft, product_sku: e.target.value })}
              placeholder="BRD-500"
              disabled={busy}
            />
          </label>
          <label className="field">
            <span>DESCRIPTION</span>
            <input
              type="text"
              value={draft.description}
              onChange={(e) => setDraft({ ...draft, description: e.target.value })}
              placeholder="hot baked, 22cm long"
              disabled={busy}
            />
          </label>
          <button
            type="button"
            className="btn btn--primary"
            onClick={() => void create()}
            disabled={busy || !draft.name.trim()}
          >
            Create
          </button>
        </div>
      </section>

      <div className="grid grid--detail">
        <section className="card">
          <header className="card__head">
            <h3 className="h3">Saved recipes</h3>
            <span className="mono" style={{ fontSize: 11, color: "var(--muted)" }}>
              {recipes.length}
            </span>
          </header>
          <div className="card__body" style={{ padding: 0 }}>
            {recipes.length === 0 ? (
              <div className="empty">No recipes yet.</div>
            ) : (
              <table className="datagrid">
                <thead>
                  <tr>
                    <th>Name</th>
                    <th>SKU</th>
                    <th className="right">Score thr</th>
                    <th className="right">Hits thr</th>
                    <th>Trigger</th>
                    <th></th>
                  </tr>
                </thead>
                <tbody>
                  {recipes.map((r) => (
                    <tr
                      key={r.id}
                      className="is-clickable"
                      onClick={() => setSelected(r.id)}
                      aria-pressed={selected === r.id ? true : undefined}
                    >
                      <td>{r.name}</td>
                      <td className="mono">{r.product_sku || "—"}</td>
                      <td className="right">{r.threshold_score.toFixed(2)}</td>
                      <td className="right">{r.threshold_hits}</td>
                      <td className="mono">{r.trigger_mode}</td>
                      <td>
                        <button
                          type="button"
                          className="btn btn--ghost"
                          onClick={(e) => {
                            e.stopPropagation();
                            void remove(r.id);
                          }}
                          disabled={busy}
                        >
                          Delete
                        </button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </div>
        </section>

        <section className="card">
          <header className="card__head">
            <h3 className="h3">Editor</h3>
            <span className="mono" style={{ fontSize: 11, color: "var(--muted)" }}>
              {editing ? editing.id : "no selection"}
            </span>
          </header>
          <div className="card__body">
            {editing ? (
              <RecipeEditor
                recipe={editing}
                onChange={update}
                busy={busy}
                onSave={save}
                lines={lines}
                loadLine={loadLine}
                onLoadLineChange={setLoadLine}
                onLoadIntoLine={loadIntoLine}
                loadMsg={loadMsg}
              />
            ) : (
              <p className="lede">Pick a recipe from the list to edit it.</p>
            )}
          </div>
        </section>
      </div>
    </div>
  );
}

interface RecipeEditorProps {
  recipe: Recipe;
  onChange: <K extends keyof Recipe>(k: K, v: Recipe[K]) => void;
  busy: boolean;
  onSave: () => Promise<void>;
  lines: Line[];
  loadLine: string;
  onLoadLineChange: (s: string) => void;
  onLoadIntoLine: () => Promise<void>;
  loadMsg: string | null;
}

function RecipeEditor({
  recipe,
  onChange,
  busy,
  onSave,
  lines,
  loadLine,
  onLoadLineChange,
  onLoadIntoLine,
  loadMsg,
}: RecipeEditorProps): JSX.Element {
  const num = (
    label: string,
    key: keyof Recipe,
    step = 0.1,
    min?: number,
    max?: number,
  ): JSX.Element => (
    <label className="field" style={{ minWidth: 0 }}>
      <span>{label}</span>
      <input
        type="number"
        step={step}
        min={min}
        max={max}
        value={recipe[key] as number}
        onChange={(e) => onChange(key, parseFloat(e.target.value) as Recipe[typeof key])}
        disabled={busy}
      />
    </label>
  );

  return (
    <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 8 }}>
      <label className="field">
        <span>NAME</span>
        <input
          type="text"
          value={recipe.name}
          onChange={(e) => onChange("name", e.target.value)}
          disabled={busy}
        />
      </label>
      <label className="field">
        <span>SKU</span>
        <input
          type="text"
          value={recipe.product_sku}
          onChange={(e) => onChange("product_sku", e.target.value)}
          disabled={busy}
        />
      </label>

      {num("THRESHOLD SCORE", "threshold_score", 0.1, 0, 20)}
      {num("THRESHOLD HITS", "threshold_hits", 1, 0, 10000)}
      {num("SIGMA THRESHOLD", "sigma_threshold", 0.1, 0.5, 10)}
      {num("DRIFT ALERT Z", "drift_alert_z", 0.1, 0.5, 10)}

      {num("ROI X0", "roi_x0", 0.01, 0, 1)}
      {num("ROI Y0", "roi_y0", 0.01, 0, 1)}
      {num("ROI X1", "roi_x1", 0.01, 0, 1)}
      {num("ROI Y1", "roi_y1", 0.01, 0, 1)}

      {num("GAIN", "gain", 0.01, 0.01, 10)}
      {num("GAMMA", "gamma", 0.05, 0.1, 5)}
      {num("SHARPEN", "sharpen", 0.05, 0, 5)}
      {num("DENOISE", "denoise", 0.05, 0, 5)}

      {num("BLOB MIN AREA", "blob_min_area", 1, 1, 1000000)}
      {num("BLOB MAX AREA", "blob_max_area", 1, 1, 10000000)}
      {num("ROTATION TOL °", "rotation_tolerance_deg", 1, 0, 180)}
      {num("SCALE TOL %", "scale_tolerance_pct", 1, 0, 100)}

      <label className="field">
        <span>TRIGGER MODE</span>
        <select
          className="mono"
          value={recipe.trigger_mode}
          onChange={(e) => onChange("trigger_mode", e.target.value as TriggerMode)}
          disabled={busy}
        >
          <option value="continuous">continuous</option>
          <option value="external">external</option>
          <option value="software">software</option>
          <option value="encoder">encoder</option>
        </select>
      </label>
      {num("DEBOUNCE MS", "debounce_ms", 1, 0, 10000)}
      {num("REJECT QUEUE DEPTH", "reject_queue_depth", 1, 1, 1000)}
      {num("STROBE DUTY %", "strobe_duty_pct", 1, 0, 100)}
      {num("STROBE DELAY US", "strobe_delay_us", 1, 0, 1000000)}

      <label className="field" style={{ gridColumn: "1 / -1" }}>
        <span>LOGIC DSL</span>
        <textarea
          rows={2}
          value={recipe.logic_dsl}
          onChange={(e) => onChange("logic_dsl", e.target.value)}
          disabled={busy}
          style={{ fontFamily: "var(--mono, monospace)", fontSize: 12 }}
        />
      </label>

      <label className="field" style={{ gridColumn: "1 / -1" }}>
        <span>DESCRIPTION</span>
        <textarea
          rows={2}
          value={recipe.description}
          onChange={(e) => onChange("description", e.target.value)}
          disabled={busy}
        />
      </label>

      <div style={{ gridColumn: "1 / -1", display: "flex", gap: 8, alignItems: "end" }}>
        <button
          type="button"
          className="btn btn--primary"
          onClick={() => void onSave()}
          disabled={busy}
        >
          Save changes
        </button>
        <label className="field" style={{ flex: 1 }}>
          <span>LOAD INTO LINE</span>
          <select
            className="mono"
            value={loadLine}
            onChange={(e) => onLoadLineChange(e.target.value)}
            disabled={busy}
          >
            <option value="">— choose —</option>
            {lines.map((l) => (
              <option key={l.id} value={l.id}>
                {l.id} · {l.customer_tag}
              </option>
            ))}
          </select>
        </label>
        <button
          type="button"
          className="btn"
          onClick={() => void onLoadIntoLine()}
          disabled={busy || !loadLine}
        >
          Apply to line
        </button>
      </div>

      {loadMsg ? (
        <div
          className="banner"
          style={{ gridColumn: "1 / -1", margin: 0, background: "#1a3", color: "#fff" }}
        >
          <b>OK</b>&nbsp;{loadMsg}
        </div>
      ) : null}
    </div>
  );
}
