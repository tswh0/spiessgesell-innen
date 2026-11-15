(() => {
  const form = document.querySelector(".sg-reviewform");
  if (!form) return;

  const sliders = Array.from(form.querySelectorAll("[data-score]"));
  const overall = form.querySelector("[data-overall]");

  const render = () => {
    let sum = 0;
    sliders.forEach((slider) => {
      const output = slider.parentElement.querySelector("[data-output]");
      if (output) output.textContent = slider.value;
      sum += Number(slider.value);
    });
    if (overall && sliders.length) {
      overall.textContent = (sum / sliders.length).toFixed(1).replace(".", ",");
    }
  };

  sliders.forEach((slider) => slider.addEventListener("input", render));
  render();

  const input = form.querySelector("[data-photos]");
  const previews = form.querySelector("[data-previews]");
  if (!input || !previews) return;

  const MAX = 6;
  const count = form.querySelector("[data-filecount]");
  input.addEventListener("change", () => {
    previews.textContent = "";
    const files = Array.from(input.files || []).slice(0, MAX);
    if ((input.files || []).length > MAX) {
      const transfer = new DataTransfer();
      files.forEach((file) => transfer.items.add(file));
      input.files = transfer.files;
    }
    if (count) {
      count.textContent =
        files.length === 0
          ? "Keine Fotos"
          : `${files.length} Foto${files.length === 1 ? "" : "s"} gewählt`;
    }
    files.forEach((file) => {
      const tile = document.createElement("div");
      tile.className = "sg-preview";
      const img = document.createElement("img");
      img.alt = "";
      const url = URL.createObjectURL(file);
      img.src = url;
      img.addEventListener("load", () => URL.revokeObjectURL(url), { once: true });
      img.addEventListener("error", () => {
        URL.revokeObjectURL(url);
        tile.classList.add("sg-preview--file");
        tile.textContent = file.name;
      }, { once: true });
      tile.appendChild(img);
      previews.appendChild(tile);
    });
  });
})();
