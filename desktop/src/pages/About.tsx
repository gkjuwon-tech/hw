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
        eyebrow="04 — About"
        title="Industrial tactile inspection for production lines."
        lede="Conet Tactile turns any conveyor into a per-part tactile inspection station. A peel-and-stick pressure mesh, calibrated from five known-good parts, scoring every part the way a trained operator's hand would — for fill, springback, voids, and bondline pressure that no camera can see."
      />

      <div className="grid grid--3" style={{ marginTop: "2rem" }}>
        <div className="card">
          <span className="num">5</span>
          <span className="unit">samples to calibrate</span>
        </div>
        <div className="card">
          <span className="num">&lt; 50 ms</span>
          <span className="unit">edge inference</span>
        </div>
        <div className="card">
          <span className="num">200–750 mm</span>
          <span className="unit">belt widths</span>
        </div>
      </div>

      <div className="card" style={{ marginTop: "2rem" }}>
        <p className="eyebrow">
          <span className="eyebrow__dot" aria-hidden="true" />
          Product lineup
        </p>
        <h2 className="h2">Mesh, Edge, Cloud.</h2>
        <ul className="checks" style={{ maxWidth: "70ch" }}>
          <li>
            <b>Tactile Mesh</b> — flexible peel-and-stick pressure-sensing sheet,
            shipped as a roll, cut to belt width on-site.
          </li>
          <li>
            <b>Tactile Edge</b> — small fanless inference appliance (Jetson Orin
            Nano class) that reads the mesh and runs anomaly scoring locally.
          </li>
          <li>
            <b>Tactile Cloud</b> — managed AI service that auto-calibrates from
            five known-good samples and continuously improves with fleet data.
          </li>
        </ul>
      </div>

      <p className="lede" style={{ marginTop: "2.5rem" }}>
        For pilot bookings, integration questions, or fab-grade installation
        support, visit{" "}
        <button
          type="button"
          onClick={() => openExternal("https://conet.studio")}
          style={{
            color: "var(--ink)",
            borderBottom: "1px solid var(--ink)",
            paddingBottom: "1px",
          }}
        >
          conet.studio
        </button>
        .
      </p>
    </div>
  );
}
