/**
 * About page.
 *
 * Product reference card. Same content as the landing page in spirit,
 * but rendered in the industrial register — no hero numbers, no
 * generated copy.
 */

import { PageHeader } from "../components/PageHeader";

export function About(): JSX.Element {
  const openExternal = (url: string): void => {
    if (typeof window !== "undefined" && window.conet?.openExternal) {
      void window.conet.openExternal(url);
    } else {
      window.open(url, "_blank");
    }
  };

  return (
    <div className="page">
      <PageHeader
        eyebrow="ABOUT"
        title="Conet Tactile · operator client"
        lede="Industrial tactile inspection for production lines. This client runs against a local Tactile Cloud sidecar and surfaces every enrolled Edge appliance and mesh segment in the org."
      />

      <div className="grid grid--3">
        <div className="card">
          <header className="card__head">
            <h3 className="h3">Samples to calibrate</h3>
          </header>
          <div className="card__body">
            <span className="num">5</span>
            <span className="unit">parts</span>
          </div>
        </div>
        <div className="card">
          <header className="card__head">
            <h3 className="h3">Edge inference</h3>
          </header>
          <div className="card__body">
            <span className="num">&lt;50</span>
            <span className="unit">ms p99</span>
          </div>
        </div>
        <div className="card">
          <header className="card__head">
            <h3 className="h3">Belt widths</h3>
          </header>
          <div className="card__body">
            <span className="num">200-750</span>
            <span className="unit">mm</span>
          </div>
        </div>
      </div>

      <section className="card">
        <header className="card__head">
          <h3 className="h3">Product lineup</h3>
        </header>
        <div className="card__body">
          <ul className="checks">
            <li>
              <b>Tactile Mesh</b> — flexible peel-and-stick pressure-sensing
              sheet, shipped as a roll, cut to belt width on-site.
            </li>
            <li>
              <b>Tactile Edge</b> — fanless inference appliance (Jetson Orin
              Nano class) that reads the mesh and runs anomaly scoring locally.
            </li>
            <li>
              <b>Tactile Cloud</b> — managed service that auto-calibrates from
              five known-good samples and continuously improves with fleet data.
            </li>
          </ul>
        </div>
      </section>

      <p className="lede">
        For pilot bookings, integration questions, or fab-grade installation
        support, visit{" "}
        <button
          type="button"
          onClick={() => openExternal("https://conet.studio")}
          style={{
            color: "var(--link)",
            textDecoration: "underline",
          }}
        >
          conet.studio
        </button>
        .
      </p>
    </div>
  );
}
