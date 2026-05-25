import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import { TitleBar } from "./components/TitleBar";
import { StatusBar } from "./components/StatusBar";
import { Toolbar } from "./components/Toolbar";
import { DeviceTree } from "./components/DeviceTree";

import { Overview } from "./pages/Overview";
import { EdgesList } from "./pages/EdgesList";
import { EdgeDetail } from "./pages/EdgeDetail";
import { ClaimsManager } from "./pages/ClaimsManager";
import { LinesList } from "./pages/LinesList";
import { LineDetail } from "./pages/LineDetail";
import { LineTune } from "./pages/LineTune";
import { MeshList } from "./pages/MeshList";
import { MeshFabric } from "./pages/MeshFabric";
import { RecipesList } from "./pages/RecipesList";
import { CalibrationWizard } from "./pages/CalibrationWizard";
import { Settings } from "./pages/Settings";
import { About } from "./pages/About";

import { api, apiBaseUrl } from "./lib/api";
import type { Edge, EdgeStatus, Line, MeshSegment } from "./lib/types";

export type Route =
  | "overview"
  | "edges"
  | "edge-detail"
  | "claims"
  | "lines"
  | "line-detail"
  | "line-tune"
  | "mesh"
  | "fabric"
  | "recipes"
  | "calibrate"
  | "settings"
  | "about";

const BUILD_LABEL = "v0.2.0 · industrial";
const INVENTORY_POLL_MS = 5_000;

export function App(): JSX.Element {
  const [route, setRoute] = useState<Route>("overview");
  const [openLineId, setOpenLineId] = useState<string | null>(null);
  const [openEdgeId, setOpenEdgeId] = useState<string | null>(null);

  const [apiStatus, setApiStatus] = useState<"ok" | "boot" | "down">("boot");
  const [apiBase, setApiBase] = useState<string>("…");

  const [edges, setEdges] = useState<Edge[]>([]);
  const [lines, setLines] = useState<Line[]>([]);
  const [meshes, setMeshes] = useState<MeshSegment[]>([]);

  const [now, setNow] = useState<Date>(() => new Date());
  const pollRef = useRef<number | null>(null);

  // Resolve the sidecar host once for the title bar readout.
  useEffect(() => {
    void apiBaseUrl().then(setApiBase);
  }, []);

  // Wall-clock tick for the status bar (1 Hz is more than enough — the
  // metric numbers come from telemetry, not this).
  useEffect(() => {
    const id = window.setInterval(() => setNow(new Date()), 1_000);
    return () => window.clearInterval(id);
  }, []);

  // Single poll loop that refreshes API health + the device inventory.
  // We deliberately keep it dead simple: every N seconds, refetch the
  // three lists and the health endpoint. Per-resource live streaming
  // (SSE) layers on top of this inside the detail pages.
  const refresh = useCallback(async (): Promise<void> => {
    try {
      await api.health();
      setApiStatus("ok");
    } catch {
      setApiStatus("down");
      return;
    }
    const [eList, lList, mList] = await Promise.all([
      api.listEdges().catch(() => [] as Edge[]),
      api.listLines().catch(() => [] as Line[]),
      api.listMeshes().catch(() => [] as MeshSegment[]),
    ]);
    setEdges(eList);
    setLines(lList);
    setMeshes(mList);
  }, []);

  useEffect(() => {
    void refresh();
    pollRef.current = window.setInterval(() => void refresh(), INVENTORY_POLL_MS);
    return () => {
      if (pollRef.current !== null) {
        window.clearInterval(pollRef.current);
        pollRef.current = null;
      }
    };
  }, [refresh]);

  const navigate = useCallback((r: Route): void => {
    setRoute(r);
    if (r !== "line-detail" && r !== "line-tune") setOpenLineId(null);
    if (r !== "edge-detail") setOpenEdgeId(null);
  }, []);

  const openLine = useCallback((id: string): void => {
    setOpenLineId(id);
    setRoute("line-detail");
  }, []);

  const tuneLine = useCallback((id: string): void => {
    setOpenLineId(id);
    setRoute("line-tune");
  }, []);

  const openEdge = useCallback((id: string): void => {
    setOpenEdgeId(id);
    setRoute("edge-detail");
  }, []);

  // Pick a "primary" edge for the title-bar/status-bar global indicators.
  // Heuristic: the currently opened edge, or the first online edge, or
  // simply the first known edge.
  const primaryEdge = useMemo<Edge | null>(() => {
    if (openEdgeId) {
      return edges.find((e) => e.id === openEdgeId) ?? null;
    }
    return (
      edges.find((e) => e.status === "online") ??
      edges.find((e) => e.status === "degraded") ??
      edges[0] ??
      null
    );
  }, [edges, openEdgeId]);

  const edgeStatus: EdgeStatus | "boot" =
    apiStatus === "boot"
      ? "boot"
      : primaryEdge
        ? primaryEdge.status
        : "offline";

  let body: JSX.Element;
  let crumb: JSX.Element;
  switch (route) {
    case "overview":
      body = (
        <Overview
          edges={edges}
          lines={lines}
          meshes={meshes}
          apiStatus={apiStatus}
          onOpenEdge={openEdge}
          onOpenLine={openLine}
        />
      );
      crumb = <span>OVERVIEW</span>;
      break;
    case "edges":
      body = <EdgesList edges={edges} onOpen={openEdge} onRefresh={refresh} onGoToClaims={() => navigate("claims")} />;
      crumb = <span>EDGES</span>;
      break;
    case "edge-detail":
      body =
        openEdgeId === null ? (
          <EdgesList edges={edges} onOpen={openEdge} onRefresh={refresh} onGoToClaims={() => navigate("claims")} />
        ) : (
          <EdgeDetail
            edgeId={openEdgeId}
            onBack={() => navigate("edges")}
          />
        );
      crumb = (
        <span>
          EDGES · <b>{openEdgeId ?? "—"}</b>
        </span>
      );
      break;
    case "lines":
      body = <LinesList lines={lines} onOpen={openLine} onTune={tuneLine} apiError={apiStatus === "down"} />;
      crumb = <span>LINES</span>;
      break;
    case "line-detail":
      body =
        openLineId === null ? (
          <LinesList lines={lines} onOpen={openLine} onTune={tuneLine} apiError={apiStatus === "down"} />
        ) : (
          <LineDetail
            lineId={openLineId}
            onBack={() => navigate("lines")}
          />
        );
      crumb = (
        <span>
          LINES · <b>{openLineId ?? "—"}</b>
        </span>
      );
      break;
    case "mesh":
      body = <MeshList meshes={meshes} lines={lines} edges={edges} />;
      crumb = <span>MESH SEGMENTS</span>;
      break;
    case "fabric":
      body = <MeshFabric edges={edges} lines={lines} meshes={meshes} onRefresh={refresh} />;
      crumb = <span>MESH FABRIC</span>;
      break;
    case "claims":
      body = <ClaimsManager onRefresh={refresh} />;
      crumb = <span>EDGE CLAIMS</span>;
      break;
    case "recipes":
      body = <RecipesList lines={lines} />;
      crumb = <span>RECIPES</span>;
      break;
    case "line-tune":
      body =
        openLineId === null ? (
          <LinesList lines={lines} onOpen={openLine} onTune={tuneLine} apiError={apiStatus === "down"} />
        ) : (
          <LineTune lineId={openLineId} onBack={() => navigate("lines")} />
        );
      crumb = (
        <span>
          TUNE · <b>{openLineId ?? "—"}</b>
        </span>
      );
      break;
    case "calibrate":
      body = <CalibrationWizard lines={lines} edges={edges} />;
      crumb = <span>TEACH</span>;
      break;
    case "settings":
      body = <Settings apiBase={apiBase} apiStatus={apiStatus} />;
      crumb = <span>SETTINGS</span>;
      break;
    case "about":
      body = <About />;
      crumb = <span>ABOUT</span>;
      break;
    default:
      body = (
        <Overview
          edges={edges}
          lines={lines}
          meshes={meshes}
          apiStatus={apiStatus}
          onOpenEdge={openEdge}
          onOpenLine={openLine}
        />
      );
      crumb = <span>OVERVIEW</span>;
      break;
  }

  const selection =
    route === "edge-detail" && openEdgeId !== null
      ? ({ kind: "edge", id: openEdgeId } as const)
      : route === "line-detail" && openLineId !== null
        ? ({ kind: "line", id: openLineId } as const)
        : null;

  return (
    <div className="app">
      <TitleBar
        hostname={apiBase}
        buildLabel={BUILD_LABEL}
        edgeStatus={edgeStatus}
      />
      <div className="app__body">
        <aside className="sidebar">
          <div className="sidebar__bar">
            <h3 className="h3">Devices</h3>
            <button
              type="button"
              className="btn btn--ghost"
              onClick={() => void refresh()}
              title="Refresh inventory"
            >
              ↻
            </button>
          </div>
          <DeviceTree
            edges={edges}
            lines={lines}
            meshes={meshes}
            selection={selection}
            onSelectEdge={openEdge}
            onSelectLine={openLine}
            onSelectMesh={() => navigate("mesh")}
          />
          <div className="sidebar__foot">
            <span>BUILD</span>
            <span className="build">{BUILD_LABEL}</span>
          </div>
        </aside>
        <main className="content">
          <Toolbar
            current={route}
            onNavigate={navigate}
            crumb={crumb}
          />
          {body}
        </main>
      </div>
      <StatusBar
        apiStatus={apiStatus}
        edge={primaryEdge}
        edgeStatus={edgeStatus}
        now={now}
      />
    </div>
  );
}
