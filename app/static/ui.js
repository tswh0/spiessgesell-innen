/* The phone menu is a sheet over the page: while it is open the page behind it is inert, so Tab stays
   in the menu instead of walking onto controls hidden under the scrim. Focus goes to the menu itself
   (not its first row, so no focus ring looks like a selected row); the first Tab reaches "Karte".
   system.js owns opening/closing; this only mirrors that state onto the rest of the document. */
(() => {
  const nav = document.querySelector(".nav");
  if (!nav) return;
  const main = document.querySelector("main");
  const links = nav.querySelector(".nav__links");
  const toggle = nav.querySelector(".nav__toggle");
  let wasOpen = false;

  const sync = () => {
    const open = nav.classList.contains("is-open");
    if (main) main.inert = open;
    // the X is not the hamburger: its name has to say what the next press does
    if (toggle) toggle.setAttribute("aria-label", open ? "Menü schließen" : "Menü");
    if (open && !wasOpen && links) {
      // after system.js has made the sheet visible
      requestAnimationFrame(() => links.focus({ preventScroll: true }));
    }
    wasOpen = open;
  };

  new MutationObserver(sync).observe(nav, { attributes: true, attributeFilter: ["class"] });
  sync();
})();

/* the edit page's delete step: the summary opens the confirmation; "Behalten" closes it again and
   returns focus to the summary, so the keyboard stays where the choice was made */
(() => {
  document.addEventListener("click", (event) => {
    const cancel = event.target.closest("[data-delete-cancel]");
    if (!cancel) return;
    const details = cancel.closest("details");
    if (!details) return;
    details.open = false;
    details.querySelector("summary")?.focus();
  });
})();
