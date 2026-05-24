import { useEffect, useState } from "react";
import { Sidebar } from "./components/Sidebar";
import { LinesList } from "./pages/LinesList";
import { LineDetail } from "./pages/LineDetail";
import { CalibrationWizard } from "./pages/CalibrationWizard";
import { Settings } from "./pages/Settings";
import { About } from "./pages/About";
import { api } from "./lib/api";

export type Route = "lines" | "line-detail" | "calibrate" | "settings" | "about";

const BUILD_LABEL = "v0.1.0 · evt-dev";

export function App(): JSX.Element {
  const [route, setRoute] = useState<Route>("lines");
  const [openLineId, setOpenLineId] = useState<string | null>(null);
  const [lineCount, setLineCount] = useState(0);
  const [apiStatus, setApiStatus] = useState<"ok" | "boot" | "down">("boot");

  // Cheap health poll every 5s. Mainly so the sidebar status dot is honest —
  // a downed sidecar means data on the page is stale and the user should know.
  useEffect(() => {
    let cancelled = false;
    const check = async (): Promise<void> => {
      try {
        await api.health();
        if (!cancelled) setApiStatus("ok");
      } catch {
        if (!cancelled) setApiStatus("down");
      }
    };
    void check();
    const id = window.setInterval(() => void check(), 5_000);
    return () => {
      cancelled = true;
      window.clearInterval(id);
    };
  }, []);

  const navigate = (r: Route): void => {
    setRoute(r);
    if (r !== "line-detail") setOpenLineId(null);
  };

  let body: JSX.Element;
  let crumb: JSX.Element;

  switch (route) {
    case "line-detail":
      body =
        openLineId === null ? (
          <LinesList
            onOpen={(id) => {
              setOpenLineId(id);
              setRoute("line-detail");
            }}
            onCountChange={setLineCount}
          />
        ) : (
          <LineDetail
            lineId={openLineId}
            onBack={() => navigate("lines")}
          />
        );
      crumb = (
        <span className="topbar__crumb">
          Lines · <b>{openLineId ?? "—"}</b>
        </span>
      );
      break;
    case "calibrate":
      body = <CalibrationWizard />;
      crumb = (
        <span className="topbar__crumb">
          Calibration · <b>Wizard</b>
        </span>
      );
      break;
    case "settings":
      body = <Settings />;
      crumb = (
        <span className="topbar__crumb">
          Settings · <b>Local</b>
        </span>
      );
      break;
    case "about":
      body = <About />;
      crumb = (
        <span className="topbar__crumb">
          About · <b>Conet Tactile</b>
        </span>
      );
      break;
    case "lines":
    default:
      body = (
        <LinesList
          onOpen={(id) => {
            setOpenLineId(id);
            setRoute("line-detail");
          }}
          onCountChange={setLineCount}
        />
      );
      crumb = (
        <span className="topbar__crumb">
          Tactile Cloud · <b>Lines</b>
        </span>
      );
      break;
  }

  return (
    <div className="app">
      <Sidebar
        current={route === "line-detail" ? "lines" : route}
        onNavigate={navigate}
        lineCount={lineCount}
        apiStatus={apiStatus}
        buildLabel={BUILD_LABEL}
      />
      <main className="content">
        <header className="topbar">
          {crumb}
          <div className="topbar__actions">
            <button
              type="button"
              className="btn btn--ghost"
              onClick={() => navigate("calibrate")}
            >
              Start a pilot
              <span className="arrow" aria-hidden="true">
                {" →"}
              </span>
            </button>
          </div>
        </header>
        {body}
      </main>
    </div>
  );
}
