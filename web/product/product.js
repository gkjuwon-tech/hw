/* =====================================================================
   Conet Tactile — product / checkout / activate page wiring.
   No framework. Plain modules. The script auto-routes by document.body.

   There is **no separate desktop installer to download**: the operator
   UI is pre-installed on the Tactile Edge appliance's integrated touch
   display and runs as a Chromium kiosk against the local edge_agent.
   The old download.html page has been removed; the subscription
   success_url now lands on activate.html instead.
   ===================================================================== */

(function () {
  "use strict";

  const API_BASE_KEY = "conet-tactile.api-base";
  const LOCAL_SESSION_PREFIX = "conet-tactile.local-session:";

  // The marketing site is served statically; the backend runs on
  // localhost:8000 in dev and at https://api.conet.studio in production.
  // The deployer may override the base by setting localStorage
  // 'conet-tactile.api-base' to a full URL (no trailing slash).
  function apiBase() {
    try {
      const stored = window.localStorage.getItem(API_BASE_KEY);
      if (stored) return stored;
    } catch (_) {
      // localStorage unavailable (private mode) — fall through to default.
    }
    if (window.location.hostname === "localhost" || window.location.hostname === "127.0.0.1") {
      return "http://localhost:8000";
    }
    return "https://api.conet.studio";
  }

  function qs(name) {
    return new URLSearchParams(window.location.search).get(name);
  }

  // ── offline fallback ───────────────────────────────────────── *
  //
  //   The marketing site is published as a static bundle and the live
  //   backend at api.conet.studio is not always reachable from preview
  //   deployments, CodeSandbox embeds, the user's phone on a corporate
  //   network with TLS interception, etc. When the checkout fetch fails
  //   with a network-level error (Safari surfaces this as the cryptic
  //   "Load failed") we don't want to wedge the order flow — we want to
  //   step the visitor through a fully client-side mock so they can see
  //   exactly what the production checkout looks like.
  //
  //   We persist the synthesized session blob in sessionStorage keyed
  //   by the local session id, then route the visitor through
  //   mock-checkout.html / activate.html with a ?local=1 flag that
  //   tells each page to read from sessionStorage instead of the
  //   backend.

  function isNetworkError(err) {
    // fetch() rejects with TypeError on network failure across every
    // major engine: "Failed to fetch" (Chrome / Firefox), "Load failed"
    // (Safari), "NetworkError" (older WebKit). Treat any TypeError or
    // any message that doesn't look like an HTTP status as a network
    // failure that should be retried as an offline mock.
    if (!err) return true;
    if (err instanceof TypeError) return true;
    const msg = String(err.message || err);
    if (/Failed to fetch/i.test(msg)) return true;
    if (/Load failed/i.test(msg)) return true;
    if (/NetworkError/i.test(msg)) return true;
    if (/network error/i.test(msg)) return true;
    return false;
  }

  function randomToken() {
    if (window.crypto && typeof window.crypto.randomUUID === "function") {
      return window.crypto.randomUUID().replace(/-/g, "").slice(0, 16);
    }
    return Math.random().toString(36).slice(2, 10) + Date.now().toString(36);
  }

  function makeLocalSessionId(mode) {
    return "cs_local_" + (mode || "x") + "_" + randomToken();
  }

  function isLocalSessionId(id) {
    return typeof id === "string" && id.indexOf("cs_local_") === 0;
  }

  function saveLocalSession(id, blob) {
    try {
      window.sessionStorage.setItem(LOCAL_SESSION_PREFIX + id, JSON.stringify(blob));
    } catch (_) {
      // sessionStorage unavailable — the fallback is best-effort.
    }
  }

  function loadLocalSession(id) {
    try {
      const raw = window.sessionStorage.getItem(LOCAL_SESSION_PREFIX + id);
      return raw ? JSON.parse(raw) : null;
    } catch (_) {
      return null;
    }
  }

  function updateLocalSession(id, patch) {
    const current = loadLocalSession(id) || {};
    saveLocalSession(id, Object.assign({}, current, patch));
  }

  function isOfflineMode() {
    return qs("local") === "1" || isLocalSessionId(qs("session_id"));
  }

  function offlineHardwareSession(body) {
    const id = makeLocalSessionId("hw");
    const unitCents = 129000;
    const qty = body.quantity || 1;
    const blob = {
      id: id,
      mode: "payment",
      status: "open",
      paid: false,
      customer_email: body.customer_email || "",
      amount_total: unitCents * qty,
      trial_days: 30,
      created_at: new Date().toISOString(),
      shipping_details: null,
      line_items: [
        {
          name: "Tactile\u00a0Edge",
          quantity: qty,
          unit_amount_usd: 1290,
        },
      ],
    };
    saveLocalSession(id, blob);
    return blob;
  }

  function offlineSoftwareSession(body) {
    const id = makeLocalSessionId("sw");
    const blob = {
      id: id,
      mode: "subscription",
      status: "open",
      paid: false,
      customer_email: body.customer_email || "",
      hardware_session_id: body.hardware_session_id || null,
      amount_total: 0,
      trial_days: 30,
      created_at: new Date().toISOString(),
      line_items: [
        {
          name: "Tactile\u00a0Cloud \u00b7 Pilot",
          quantity: 1,
          unit_amount_usd: 49,
          trial_days: 30,
        },
      ],
    };
    saveLocalSession(id, blob);
    return blob;
  }

  function offlineMockUrl(id) {
    return "mock-checkout.html?session_id=" + encodeURIComponent(id) + "&local=1";
  }

  function formatUsd(cents) {
    if (cents == null) return "USD\u00a00.00";
    const dollars = (cents / 100).toFixed(2);
    return "USD\u00a0" + Number(dollars).toLocaleString("en-US", { minimumFractionDigits: 2 });
  }

  function formatTrialEnd(days) {
    if (!days) return "—";
    const end = new Date(Date.now() + days * 24 * 60 * 60 * 1000);
    return end.toLocaleDateString(undefined, {
      year: "numeric",
      month: "short",
      day: "numeric",
    });
  }

  function setText(id, value) {
    const el = document.getElementById(id);
    if (el) el.textContent = value;
  }

  function setHref(id, value) {
    const el = document.getElementById(id);
    if (el && value) el.setAttribute("href", value);
  }

  async function postJson(path, body) {
    const resp = await fetch(apiBase() + path, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body || {}),
    });
    if (!resp.ok) {
      const detail = await resp.text().catch(() => resp.statusText);
      throw new Error("POST " + path + " failed: " + resp.status + " " + detail);
    }
    return resp.json();
  }

  async function getJson(path) {
    const resp = await fetch(apiBase() + path);
    if (!resp.ok) {
      throw new Error("GET " + path + " failed: " + resp.status);
    }
    return resp.json();
  }

  function setSubmitting(button, isSubmitting, label) {
    if (!button) return;
    button.disabled = isSubmitting;
    const span = button.querySelector(".submit__label, .buy__submit-label");
    if (span && label) span.textContent = label;
  }

  function setHidden(id, hidden) {
    const el = document.getElementById(id);
    if (el) el.style.display = hidden ? "none" : "";
  }

  // ── footer ───────────────────────────────────────────────────
  function wireFooter() {
    const year = document.getElementById("year");
    if (year) year.textContent = String(new Date().getFullYear());
  }

  // ── scanner.html ──────────────────────────────
  async function wireScannerPage() {
    const submit = document.getElementById("buy-submit");
    if (!submit) return;
    const email = document.getElementById("buy-email");
    const qty = document.getElementById("buy-qty");
    const mockBanner = document.getElementById("buy-mock-banner");

    let backendReachable = true;
    try {
      const catalog = await getJson("/v1/store/catalog");
      if (catalog.mock_mode && mockBanner) mockBanner.hidden = false;
    } catch (err) {
      console.warn("catalog fetch failed", err);
      if (isNetworkError(err)) {
        backendReachable = false;
        // When the live backend is unreachable the order flow becomes a
        // client-only demo; surface the mock banner so the visitor
        // knows up-front that no real card will be charged.
        if (mockBanner) mockBanner.hidden = false;
      }
    }

    function startOfflineCheckout(body) {
      const session = offlineHardwareSession(body);
      window.location.assign(offlineMockUrl(session.id));
    }

    submit.addEventListener("click", async () => {
      setSubmitting(submit, true, "Creating checkout…");
      const body = {
        sku_id: "tactile_edge",
        quantity: parseInt(qty.value, 10) || 1,
      };
      if (email && email.value) body.customer_email = email.value;
      body.success_url = new URL("activate.html", window.location.href).toString();
      body.cancel_url = new URL("scanner.html", window.location.href).toString();

      if (!backendReachable) {
        startOfflineCheckout(body);
        return;
      }

      try {
        const session = await postJson("/v1/store/checkout/hardware", body);
        window.location.assign(session.url);
      } catch (err) {
        console.error(err);
        if (isNetworkError(err)) {
          // Backend was healthy on catalog read but is now unreachable
          // (or never had the checkout endpoint deployed). Fall through
          // to the client-only flow instead of stranding the visitor.
          startOfflineCheckout(body);
          return;
        }
        setSubmitting(submit, false, "Continue to checkout");
        alert("Could not start checkout: " + err.message);
      }
    });
  }

  // ── activate.html ────────────────────────────────────────────
  async function wireActivatePage() {
    const submit = document.getElementById("activate-submit");
    if (!submit) return;

    const sessionId = qs("session_id");
    const offline = isOfflineMode();
    const mockBanner = document.getElementById("activate-mock-banner");
    const priceEl = document.getElementById("sw-price");

    let plan = {
      id: "tactile_cloud_pilot",
      monthly_amount_usd: 49,
      trial_days: 30,
    };
    let backendReachable = !offline;

    if (!offline) {
      try {
        const catalog = await getJson("/v1/store/catalog");
        plan = catalog.software[0] || plan;
        if (catalog.mock_mode && mockBanner) mockBanner.hidden = false;
      } catch (err) {
        console.warn("catalog fetch failed", err);
        if (isNetworkError(err)) {
          backendReachable = false;
          if (mockBanner) mockBanner.hidden = false;
        }
      }
    } else {
      if (mockBanner) mockBanner.hidden = false;
    }

    if (priceEl && plan && plan.monthly_amount_usd != null) {
      priceEl.textContent = String(plan.monthly_amount_usd);
    }

    function renderOrder(order) {
      setText("hw-order-id", order.id);
      setText("hw-order-status", order.paid ? "paid" : (order.status || "pending"));
      setText("hw-order-email", order.customer_email || "\u2014");
      const ship = order.shipping_details;
      const shipText =
        ship && ship.address
          ? [
              ship.name,
              ship.address.line1,
              ship.address.line2,
              ship.address.city,
              ship.address.state,
              ship.address.postal_code,
              ship.address.country,
            ]
              .filter(Boolean)
              .join(", ")
          : "\u2014";
      setText("hw-order-ship", shipText);
      if (order.amount_total) {
        setText("hw-order-total", formatUsd(order.amount_total));
        setText("hero-total", formatUsd(order.amount_total));
      } else {
        setText("hw-order-total", "\u2014");
      }
      if (plan && plan.trial_days) {
        setText("hero-trial-end", formatTrialEnd(plan.trial_days));
      }
    }

    if (sessionId) {
      if (isLocalSessionId(sessionId)) {
        const order = loadLocalSession(sessionId);
        if (order) {
          renderOrder(order);
        } else {
          setText("hw-order-status", "session not found");
        }
      } else {
        try {
          const order = await getJson("/v1/store/order/" + encodeURIComponent(sessionId));
          renderOrder(order);
        } catch (err) {
          console.error(err);
          setText("hw-order-status", isNetworkError(err) ? "backend unreachable" : "could not load");
        }
      }
    } else {
      setText("hw-order-status", "no session id in URL");
    }

    function startOfflineSubscription(body) {
      const session = offlineSoftwareSession(body);
      window.location.assign(offlineMockUrl(session.id));
    }

    submit.addEventListener("click", async () => {
      setSubmitting(submit, true, "Activating Edge Care…");
      const body = {
        plan_id: (plan && plan.id) || "edge_care_basic",
      };
      if (sessionId) body.hardware_session_id = sessionId;
      const orderEmail = document.getElementById("hw-order-email");
      if (orderEmail && orderEmail.textContent && orderEmail.textContent !== "—") {
        body.customer_email = orderEmail.textContent;
      }
      // No separate download page — the on-device software ships
      // pre-installed on the appliance's integrated touch display, so
      // we land back on activate.html with the trial-active state.
      body.success_url = new URL("activate.html", window.location.href).toString();
      body.cancel_url = window.location.href;

      if (!backendReachable || isLocalSessionId(sessionId)) {
        startOfflineSubscription(body);
        return;
      }

      try {
        const session = await postJson("/v1/store/checkout/software", body);
        window.location.assign(session.url);
      } catch (err) {
        console.error(err);
        if (isNetworkError(err)) {
          startOfflineSubscription(body);
          return;
        }
        setSubmitting(submit, false, "Activate Edge Care");
        alert("Could not start subscription: " + err.message);
      }
    });
  }

  // The old wireDownloadPage() that pointed at exe / dmg / AppImage
  // installers is gone — the operator UI ships pre-installed on the
  // Tactile Edge appliance's integrated touch display. The activate
  // page is now the post-checkout landing page for both hardware and
  // Edge Care subscriptions.

  // ── mock-checkout.html ───────────────────────────────────────
  async function wireMockCheckoutPage() {
    const form = document.getElementById("mc-form");
    if (!form) return;

    const sessionId = qs("session_id");
    if (!sessionId) {
      showMockError("Missing session id.");
      return;
    }

    const isLocal = isLocalSessionId(sessionId) || qs("local") === "1";

    let session = null;
    if (isLocal) {
      session = loadLocalSession(sessionId);
      if (!session) {
        showMockError(
          "Local session not found in this tab. Start the order from the scanner page."
        );
        return;
      }
    } else {
      try {
        session = await getJson("/v1/store/mock/session/" + encodeURIComponent(sessionId));
      } catch (err) {
        console.error(err);
        if (isNetworkError(err)) {
          showMockError(
            "Backend unreachable \u2014 start the order from the scanner page to use the offline mock."
          );
          return;
        }
        showMockError("Could not load checkout session: " + err.message);
        return;
      }
    }

    const isSubscription = session.mode === "subscription";
    const item = (session.line_items && session.line_items[0]) || {};

    setText("mc-mode-kicker", isSubscription ? "Subscription · monthly" : "Order · one-time");
    setText("mc-item-name", item.name || "Order");

    if (isSubscription) {
      setText("mc-amount", "USD\u00a00.00");
      setText(
        "mc-line-unit",
        "Trial " + (item.trial_days || 30) + " days, then USD\u00a0" + item.unit_amount_usd + " / month"
      );
      setText("mc-pay-label", "Start free trial");
      [
        "mc-ship-title",
        "mc-name-row",
        "mc-phone-row",
        "mc-line1-row",
        "mc-city-row",
        "mc-postal-row",
        "mc-country-row",
      ].forEach((id) => setHidden(id, true));
      const bullets = document.getElementById("mc-bullets");
      if (bullets) {
        bullets.innerHTML =
          '<li>First ' +
          (item.trial_days || 30) +
          ' days free \u2014 cancel any time</li>' +
          '<li>Over-the-air updates to the on-device kiosk software</li>' +
          '<li>Per-cell drift detection synced to your Tactile Cloud workspace</li>' +
          '<li>Replacement Tactile Mesh rolls shipped on schedule</li>' +
          '<li>Card required so the line does not stop at trial end</li>';
      }
    } else {
      const total = session.amount_total || (item.unit_amount_usd || 0) * 100 * (item.quantity || 1);
      setText("mc-amount", formatUsd(total));
      setText(
        "mc-line-unit",
        (item.quantity || 1) + "\u00a0×\u00a0USD\u00a0" + (item.unit_amount_usd || 0).toLocaleString("en-US")
      );
      setText("mc-pay-label", "Pay " + formatUsd(total));
    }

    function completeLocal() {
      const email = document.getElementById("mc-email");
      const patch = {
        paid: true,
        status: "paid",
        customer_email: (email && email.value) || session.customer_email || "buyer@example.com",
      };
      if (!isSubscription) {
        patch.shipping_details = {
          name: (document.getElementById("mc-name") || {}).value || "",
          address: {
            line1: (document.getElementById("mc-line1") || {}).value || "",
            city: (document.getElementById("mc-city") || {}).value || "",
            postal_code: (document.getElementById("mc-postal") || {}).value || "",
            country: (document.getElementById("mc-country") || {}).value || "",
          },
        };
      }
      updateLocalSession(sessionId, patch);
      // Both hardware and Edge Care flows now land on activate.html;
      // the page picks the right copy based on session.mode.
      const nextPage = "activate.html";
      window.location.assign(
        nextPage + "?session_id=" + encodeURIComponent(sessionId) + "&local=1"
      );
    }

    form.addEventListener("submit", async (e) => {
      e.preventDefault();
      const payBtn = document.getElementById("mc-pay");
      setSubmitting(payBtn, true, isSubscription ? "Starting trial…" : "Processing…");

      if (isLocal) {
        completeLocal();
        return;
      }

      try {
        const body = {
          session_id: sessionId,
          customer_email: document.getElementById("mc-email").value || "buyer@example.com",
        };
        if (!isSubscription) {
          body.name = document.getElementById("mc-name").value;
          body.phone = document.getElementById("mc-phone").value;
          body.line1 = document.getElementById("mc-line1").value;
          body.city = document.getElementById("mc-city").value;
          body.postal_code = document.getElementById("mc-postal").value;
          body.country = document.getElementById("mc-country").value;
        }
        const result = await postJson("/v1/store/mock/complete", body);
        window.location.assign(result.redirect_url);
      } catch (err) {
        console.error(err);
        if (isNetworkError(err)) {
          // The session was created against a real backend that has
          // since dropped offline. Best-effort: persist the form data
          // to sessionStorage so the activate / download pages can
          // pick up where we left off via the same local fallback.
          saveLocalSession(sessionId, Object.assign({}, session, { paid: true, status: "paid" }));
          const nextPage = "activate.html";
          window.location.assign(
            nextPage + "?session_id=" + encodeURIComponent(sessionId) + "&local=1"
          );
          return;
        }
        setSubmitting(
          payBtn,
          false,
          isSubscription ? "Start free trial" : "Pay"
        );
        showMockError(err.message || "checkout failed");
      }
    });
  }

  function showMockError(msg) {
    const el = document.getElementById("mc-error");
    if (el) {
      el.textContent = msg;
      el.hidden = false;
    }
  }

  // ── boot ─────────────────────────────────────────────────────
  document.addEventListener("DOMContentLoaded", function () {
    wireFooter();
    wireScannerPage();
    wireActivatePage();
    wireMockCheckoutPage();
  });
})();
