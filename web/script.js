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
})();
