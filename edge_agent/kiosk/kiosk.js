/* Conet Tactile — on-device kiosk.
 *
 * Runs inside the Chromium kiosk launched by conet-edge-kiosk.service.
 * Polls the local edge_agent at /kiosk/status every second and updates
 * the verdict + telemetry chips. Buttons are wired to local stubs
 * today; the next iteration will route them through edge_agent → the
 * /v1/calibrate and /v1/recipes endpoints in the FastAPI backend.
 */

(function () {
  "use strict";

  const POLL_MS = 1000;

  const $ = (id) => document.getElementById(id);

  function setText(id, value) {
    const el = $(id);
    if (el) el.textContent = value;
  }

  function formatMs(v) {
    if (v === null || v === undefined || isNaN(v)) return "—";
    if (v < 10) return v.toFixed(1);
    return Math.round(v).toString();
  }

  function formatFps(v) {
    if (v === null || v === undefined || isNaN(v)) return "—";
    return v.toFixed(0);
  }

  function tickClock() {
    const now = new Date();
    const hh = String(now.getHours()).padStart(2, "0");
    const mm = String(now.getMinutes()).padStart(2, "0");
    const ss = String(now.getSeconds()).padStart(2, "0");
    setText("kiosk-clock", hh + ":" + mm + ":" + ss);
  }

  function setNetworkOk() {
    setText("kiosk-network", "agent connected");
    const dot = $("status-dot");
    if (dot) {
      dot.classList.remove("kiosk__dot--warn", "kiosk__dot--bad");
    }
  }

  function setNetworkBad() {
    setText("kiosk-network", "agent unreachable");
    const dot = $("status-dot");
    if (dot) {
      dot.classList.add("kiosk__dot--bad");
      dot.classList.remove("kiosk__dot--warn");
    }
  }

  function render(status) {
    setText("kiosk-edge-id", status.edge_id || "edge-—");
    setText("kiosk-line-id", status.line_id || "line-—");
    setText("kiosk-version", status.agent_version || "—");
    setText("kiosk-port", status.scanner_port || "—");

    setText("kiosk-fps", formatFps(status.fps));
    setText("kiosk-frames", (status.frames_total || 0).toLocaleString());
    setText("kiosk-dropped", (status.frames_dropped || 0).toLocaleString());
    setText("kiosk-p50", formatMs(status.inference_p50_ms));
    setText("kiosk-p99", formatMs(status.inference_p99_ms));

    const verdictEl = $("kiosk-verdict");
    const verdict = (status.last_verdict || "—").toString();
    if (verdictEl) {
      verdictEl.textContent = verdict;
      const v = verdict.toLowerCase();
      if (v === "pass" || v === "ok") {
        verdictEl.dataset.verdict = "pass";
      } else if (v === "fail" || v === "reject") {
        verdictEl.dataset.verdict = "fail";
      } else {
        delete verdictEl.dataset.verdict;
      }
    }
    setText(
      "kiosk-score",
      typeof status.last_score === "number"
        ? status.last_score.toFixed(2)
        : "0.00"
    );
  }

  async function pollOnce() {
    try {
      const res = await fetch("/kiosk/status", { cache: "no-store" });
      if (!res.ok) throw new Error("status " + res.status);
      const body = await res.json();
      setNetworkOk();
      render(body);
    } catch (_err) {
      setNetworkBad();
    }
  }

  function wireButtons() {
    const click = (id, label) => {
      const btn = $(id);
      if (!btn) return;
      btn.addEventListener("click", () => {
        btn.disabled = true;
        const original = btn.textContent;
        btn.textContent = label + " · queued";
        setTimeout(() => {
          btn.disabled = false;
          btn.textContent = original;
        }, 1200);
      });
    };
    click("btn-calibrate", "Calibrate");
    click("btn-recipe", "Switch recipe");
    click("btn-ack", "Acknowledge");
  }

  document.addEventListener("DOMContentLoaded", function () {
    wireButtons();
    tickClock();
    pollOnce();
    setInterval(tickClock, 1000);
    setInterval(pollOnce, POLL_MS);
  });
})();
