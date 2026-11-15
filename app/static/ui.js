/* The phone menu is a sheet over the page: while it is open the page behind it is inert, so Tab stays
   in the menu instead of walking onto controls hidden under the scrim. Focus goes to the menu itself
   (not its first row, so no focus ring looks like a selected row); the first Tab reaches "Karte".
   system.js owns opening/closing; this only mirrors that state onto the rest of the document. */
(() => {
  const nav = document.querySelector(".nav");
  if (!nav) return;
  const main = document.querySelector("main");
  const footer = document.querySelector("footer.footer");
  const links = nav.querySelector(".nav__links");
  let wasOpen = false;

  const sync = () => {
    const open = nav.classList.contains("is-open");
    if (main) main.inert = open;
    if (footer) footer.inert = open;
    if (open && !wasOpen && links) {
      // after system.js has made the sheet visible
      requestAnimationFrame(() => links.focus({ preventScroll: true }));
    }
    wasOpen = open;
  };

  new MutationObserver(sync).observe(nav, { attributes: true, attributeFilter: ["class"] });
  sync();
})();
