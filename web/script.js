(() => {
  "use strict";

  // Sticky topbar background swap once the user scrolls past the hero overlap.
  const topbar = document.getElementById("topbar");
  if (topbar) {
    const onScroll = () => {
      const stuck = window.scrollY > 24;
      topbar.classList.toggle("is-stuck", stuck);
    };
    document.addEventListener("scroll", onScroll, { passive: true });
    onScroll();
  }

  // Footer year.
  const yearEl = document.getElementById("year");
  if (yearEl) {
    yearEl.textContent = String(new Date().getFullYear());
  }

  // Form: prevent the placeholder Formspree action from actually submitting
  // during local development. Replace the action attribute with a real endpoint
  // before deploying.
  const form = document.querySelector(".form");
  if (form) {
    form.addEventListener("submit", (event) => {
      const action = form.getAttribute("action") || "";
      if (action.includes("replace-with-real-endpoint")) {
        event.preventDefault();
        const legal = form.querySelector(".form__legal");
        if (legal) {
          legal.textContent =
            "Thanks. The pilot intake endpoint is not wired up in this demo build — please email tactile@conet.studio.";
        }
      }
    });
  }
})();
