import { useEffect, useState } from "react";
import { PageHeader } from "../components/PageHeader";
import { KV } from "../components/KV";
import { api, apiBaseUrl } from "../lib/api";

export function Settings(): JSX.Element {
  const [base, setBase] = useState<string>("…");
  const [health, setHealth] = useState<string>("…");

  useEffect(() => {
    let cancelled = false;
    void apiBaseUrl().then((b) => {
      if (!cancelled) setBase(b);
    });
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
    typeof window !== "undefined" && window.conet?.platform
      ? window.conet.platform
      : "browser";

  return (
    <div className="page">
      <PageHeader
        eyebrow="03 — Settings"
        title="Local sidecar configuration."
        lede="The desktop binds to a loopback-only Tactile Cloud sidecar. There is no remote network surface to configure here — the only knob is which sidecar URL the renderer talks to."
      />

      <div className="grid grid--2" style={{ marginTop: "2rem" }}>
        <section className="card">
          <p className="eyebrow">
            <span className="eyebrow__dot" aria-hidden="true" />
            Runtime
          </p>
          <h3 className="h3" style={{ marginTop: "0.5rem" }}>
            Where the bytes are.
          </h3>
          <KV
            rows={[
              { k: "Sidecar base", v: base },
              { k: "Sidecar health", v: health },
              { k: "Host platform", v: platform },
              { k: "Build channel", v: "evt-dev" },
            ]}
          />
        </section>

        <section className="card card--ink">
          <p className="eyebrow eyebrow--light">
            <span className="eyebrow__dot" aria-hidden="true" />
            Why so few settings?
          </p>
          <h3 className="h3" style={{ marginTop: "0.5rem", color: "var(--paper)" }}>
            The desktop is a thin pane of glass.
          </h3>
          <p className="body" style={{ color: "var(--paper-2)", maxWidth: "60ch" }}>
            All operational knobs — drift thresholds, reject windows, webhook
            destinations, fleet rules — live in Tactile Cloud and are pushed to
            the Edge appliance. The desktop renders what the cloud computes; it
            does not configure the cloud. To change a threshold, use the cloud
            console.
          </p>
        </section>
      </div>
    </div>
  );
}
