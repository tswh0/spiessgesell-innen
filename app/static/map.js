(() => {
  const el = document.getElementById("map");
  const dataEl = document.getElementById("shop-data");
  if (!el || !dataEl) return;

  const shops = JSON.parse(dataEl.textContent || "[]");
  const map = L.map(el, { scrollWheelZoom: true, zoomControl: false }).setView([52.5, 13.42], 12);
  L.control.zoom({ zoomInTitle: "Vergrößern", zoomOutTitle: "Verkleinern" }).addTo(map);

  L.tileLayer("https://tile.openstreetmap.org/{z}/{x}/{y}.png", {
    maxZoom: 19,
    attribution:
      '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>',
  }).addTo(map);

  const score = (value) =>
    value == null ? "–" : Number(value).toFixed(1).replace(".", ",");
  const esc = (value) => String(value).replace(/[&<>"']/g, (char) => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
  })[char]);

  const markers = new Map();
  const points = [];

  shops.forEach((shop) => {
    const label = shop.score == null ? "Neu" : score(shop.score);
    const icon = L.divIcon({
      className: "",
      html: `<span class="sg-pin${shop.score == null ? " is-empty" : ""}${shop.best ? " is-best" : ""}">${label}</span>`,
      iconSize: [44, 44],
      iconAnchor: [22, 22],
      popupAnchor: [0, -20],
    });
    const marker = L.marker([shop.lat, shop.lng], {
      icon,
      title: shop.name,
      alt: shop.name,
      keyboard: true,
    }).addTo(map);
    const markerEl = marker.getElement();
    const pin = markerEl?.querySelector(".sg-pin");
    if (markerEl) {
      const value = shop.score == null
        ? "Noch keine Bewertung"
        : `${score(shop.score)} von 10, ${shop.count} Bewertung${shop.count === 1 ? "" : "en"}`;
      markerEl.setAttribute("aria-label", `${shop.name}, ${value}`);
    }
    const meta = shop.score == null
      ? "Noch keine Bewertung"
      : `${score(shop.score)} · ${shop.count}&nbsp;Bewertung${shop.count === 1 ? "" : "en"}`;
    marker.bindPopup(
      `<strong>${esc(shop.name)}</strong>` +
        `${meta}<br>` +
        `<a href="/laden/${encodeURIComponent(shop.slug)}">Ansehen</a>`
    );
    marker.on("popupopen", (event) => {
      const close = event.popup.getElement()?.querySelector(".leaflet-popup-close-button");
      if (close) {
        close.setAttribute("aria-label", "Schließen");
        close.setAttribute("title", "Schließen");
      }
      pin?.classList.add("is-active");
      activate(shop.slug);
    });
    marker.on("popupclose", () => {
      pin?.classList.remove("is-active");
      document.querySelectorAll(".sg-card.is-active").forEach((card) => card.classList.remove("is-active"));
    });
    markers.set(shop.slug, marker);
    points.push([shop.lat, shop.lng]);
  });

  if (points.length === 1) map.setView(points[0], 15);
  if (points.length > 1) map.fitBounds(points, { padding: [40, 40], maxZoom: 14 });

  function activate(slug) {
    document.querySelectorAll(".sg-card").forEach((card) => {
      card.classList.toggle("is-active", card.dataset.slug === slug);
    });
    const card = document.querySelector(`.sg-card[data-slug="${CSS.escape(slug)}"]`);
    if (card) card.scrollIntoView({ block: "nearest", behavior: "smooth" });
  }

  document.querySelectorAll(".sg-card").forEach((card) => {
    const slug = card.dataset.slug;
    const marker = markers.get(slug);
    if (!marker) return;
    card.addEventListener("mouseenter", () => marker.setZIndexOffset(1000));
    card.addEventListener("mouseleave", () => marker.setZIndexOffset(0));
    card.addEventListener("focus", () => marker.setZIndexOffset(1000));
    card.addEventListener("blur", () => marker.setZIndexOffset(0));
  });
})();
