/* =====================================================================
   Conet Tactile — product / checkout / activate / download page wiring
   No framework. Plain modules. The script auto-routes by document.body.
   ===================================================================== */

(function () {
  "use strict";

  const API_BASE_KEY = "conet-tactile.api-base";

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

  // ── scanner.html ─────────────────────────────────────────────
  async function wireScannerPage() {
    const submit = document.getElementById("buy-submit");
    if (!submit) return;
    const email = document.getElementById("buy-email");
    const qty = document.getElementById("buy-qty");
    const mockBanner = document.getElementById("buy-mock-banner");

    try {
      const catalog = await getJson("/v1/store/catalog");
      if (catalog.mock_mode && mockBanner) mockBanner.hidden = false;
    } catch (err) {
      console.warn("catalog fetch failed", err);
    }

    submit.addEventListener("click", async () => {
      setSubmitting(submit, true, "Creating checkout…");
      try {
        const body = {
          sku_id: "tactile_edge",
          quantity: parseInt(qty.value, 10) || 1,
        };
        if (email && email.value) body.customer_email = email.value;
        const successUrl = new URL("activate.html", window.location.href).toString();
        const cancelUrl = new URL("scanner.html", window.location.href).toString();
        body.success_url = successUrl;
        body.cancel_url = cancelUrl;
        const session = await postJson("/v1/store/checkout/hardware", body);
        window.location.assign(session.url);
      } catch (err) {
        console.error(err);
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
    const mockBanner = document.getElementById("activate-mock-banner");
    const priceEl = document.getElementById("sw-price");

    let plan;
    try {
      const catalog = await getJson("/v1/store/catalog");
      plan = catalog.software[0];
      if (priceEl) priceEl.textContent = String(plan.monthly_amount_usd);
      if (catalog.mock_mode && mockBanner) mockBanner.hidden = false;
    } catch (err) {
      console.warn("catalog fetch failed", err);
    }

    if (sessionId) {
      try {
        const order = await getJson("/v1/store/order/" + encodeURIComponent(sessionId));
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
      } catch (err) {
        console.error(err);
        setText("hw-order-status", "could not load");
      }
    } else {
      setText("hw-order-status", "no session id in URL");
    }

    submit.addEventListener("click", async () => {
      setSubmitting(submit, true, "Creating subscription…");
      try {
        const body = {
          plan_id: (plan && plan.id) || "tactile_cloud_pilot",
        };
        if (sessionId) body.hardware_session_id = sessionId;
        const orderEmail = document.getElementById("hw-order-email");
        if (orderEmail && orderEmail.textContent && orderEmail.textContent !== "—") {
          body.customer_email = orderEmail.textContent;
        }
        body.success_url = new URL("download.html", window.location.href).toString();
        body.cancel_url = window.location.href;
        const session = await postJson("/v1/store/checkout/software", body);
        window.location.assign(session.url);
      } catch (err) {
        console.error(err);
        setSubmitting(submit, false, "Activate trial");
        alert("Could not start subscription: " + err.message);
      }
    });
  }

  // ── download.html ────────────────────────────────────────────
  async function wireDownloadPage() {
    const winLink = document.getElementById("dl-windows");
    if (!winLink) return;
    const sessionId = qs("session_id");
    if (!sessionId) {
      setText("sub-id", "no session id in URL");
      return;
    }

    try {
      const order = await getJson("/v1/store/order/" + encodeURIComponent(sessionId));
      setText("sub-id", order.subscription || order.id);
      setText("sub-email", order.customer_email || "\u2014");
      const trialEnd = formatTrialEnd(order.trial_days);
      setText("sub-trial-end", trialEnd);
      setText("meta-trial-end", trialEnd);
      if (order.trial_days) {
        setText("meta-trial", order.trial_days + "\u00a0days");
      }
      if (order.downloads) {
        setHref("dl-windows", order.downloads.windows);
        setHref("dl-mac", order.downloads.mac);
        setHref("dl-linux", order.downloads.linux);
      } else {
        setText("sub-id", "trial not active");
      }
    } catch (err) {
      console.error(err);
      setText("sub-id", "could not load");
    }
  }

  // ── mock-checkout.html ───────────────────────────────────────
  async function wireMockCheckoutPage() {
    const form = document.getElementById("mc-form");
    if (!form) return;

    const sessionId = qs("session_id");
    if (!sessionId) {
      showMockError("Missing session id.");
      return;
    }

    let session;
    try {
      session = await getJson("/v1/store/mock/session/" + encodeURIComponent(sessionId));
    } catch (err) {
      console.error(err);
      showMockError("Could not load checkout session: " + err.message);
      return;
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
          '<li>Per-line calibration, drift detection, dashboards</li>' +
          '<li>Desktop installer link delivered on the next page</li>' +
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

    form.addEventListener("submit", async (e) => {
      e.preventDefault();
      const payBtn = document.getElementById("mc-pay");
      setSubmitting(payBtn, true, isSubscription ? "Starting trial…" : "Processing…");
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
    wireDownloadPage();
    wireMockCheckoutPage();
  });
})();
