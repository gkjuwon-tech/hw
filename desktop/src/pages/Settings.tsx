/**
 * Settings page.
 *
 * Lets the operator configure the local sidecar URL (read-only — set
 * by the Electron bridge) and the optional bearer token used to
 * authenticate against Tactile Cloud.
 */

import { useEffect, useState } from "react";
import { PageHeader } from "../components/PageHeader";
import { api, getApiToken, setApiToken } from "../lib/api";

export interface SettingsProps {
  apiBase: string;
  apiStatus: "ok" | "boot" | "down";
}

export function Settings({ apiBase, apiStatus }: SettingsProps): JSX.Element {
  const [health, setHealth] = useState<string>("…");
  const [token, setToken] = useState<string>(() => getApiToken());
  const [savedAt, setSavedAt] = useState<Date | null>(null);

  useEffect(() => {
    let cancelled = false;
    api
      .health()
      .then((h) => {
        if (cancelled) return;
        setHealth(`${h.service} ${h.version} (${h.environment})`);
      })
      .catch((e: unknown) => {
        if (cancelled) return;
        setHealth(e instanceof Error ? e.message : String(e));
      });
    return () => {
      cancelled = true;
    };
  }, []);

  const platform =
    typeof navigator !== "undefined" && navigator.platform
      ? navigator.platform
      : "browser";

  const saveToken = (): void => {
    setApiToken(token.trim());
    setSavedAt(new Date());
  };

  return (
    <div className="page">
      <PageHeader
        eyebrow="SETTINGS"
        title="Sidecar configuration"
        lede="The desktop binds to a loopback-only Tactile Cloud sidecar. Most operational knobs live in the cloud console — this page only configures local credentials and shows the current runtime."
        actions={
          <span className="led" data-state={apiStatus === "ok" ? "online" : apiStatus}>
            <span className="led__dot" aria-hidden="true" />
            API {apiStatus === "ok" ? "CONNECTED" : apiStatus.toUpperCase()}
          </span>
        }
      />

      <div className="grid grid--2">
        <section className="card">
          <header className="card__head">
            <h3 className="h3">Runtime</h3>
          </header>
          <div className="card__body">
            <dl className="kv">
              <div>
                <dt>Sidecar base</dt>
                <dd>{apiBase}</dd>
              </div>
              <div>
                <dt>Sidecar health</dt>
                <dd>{health}</dd>
              </div>
              <div>
                <dt>Host platform</dt>
                <dd>{platform}</dd>
              </div>
              <div>
                <dt>Build channel</dt>
                <dd>industrial</dd>
              </div>
            </dl>
          </div>
        </section>

        <section className="card">
          <header className="card__head">
            <h3 className="h3">Authentication</h3>
            <span className="mono" style={{ fontSize: 11, color: "var(--muted)" }}>
              Bearer token
            </span>
          </header>
          <div className="card__body" style={{ display: "grid", gap: 8 }}>
            <p className="lede">
              Optional. If set, the desktop attaches{" "}
              <code className="mono">Authorization: Bearer &lt;token&gt;</code>{" "}
              to every API call. Stored only in this client&apos;s
              localStorage — never synced to disk by the sidecar.
            </p>
            <label className="field">
              <span>API TOKEN</span>
              <input
                type="password"
                value={token}
                onChange={(e) => setToken(e.target.value)}
                placeholder="(empty for unauthenticated)"
                autoComplete="off"
              />
            </label>
            <div style={{ display: "flex", gap: 6, alignItems: "center" }}>
              <button type="button" className="btn btn--primary" onClick={saveToken}>
                Save
              </button>
              <button
                type="button"
                className="btn"
                onClick={() => {
                  setToken("");
                  setApiToken("");
                  setSavedAt(new Date());
                }}
              >
                Clear
              </button>
              {savedAt ? (
                <span className="mono" style={{ fontSize: 11, color: "var(--muted)" }}>
                  saved {savedAt.toLocaleTimeString()}
                </span>
              ) : null}
            </div>
          </div>
        </section>
      </div>
    </div>
  );
}
