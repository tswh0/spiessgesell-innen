(() => {
  const el = document.getElementById("map");
  const dataEl = document.getElementById("shop-data");
  if (!el || !dataEl) return;

  const shops = JSON.parse(dataEl.textContent || "[]");
  const map = L.map(el, { scrollWheelZoom: true }).setView([52.5, 13.42], 12);

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
    const label = shop.score == null ? "+" : score(shop.score);
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
    }).addTo(map);
    marker.bindPopup(
      `<strong>${esc(shop.name)}</strong><br>` +
        `${score(shop.score)} · ${shop.count} Bewertung${shop.count === 1 ? "" : "en"}<br>` +
        `<a href="/laden/${encodeURIComponent(shop.slug)}">Ansehen</a>`
    );
    marker.on("popupopen", () => activate(shop.slug));
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
