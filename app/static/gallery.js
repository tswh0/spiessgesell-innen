(() => {
  const dialog = document.querySelector(".sg-gallery");
  const links = Array.from(document.querySelectorAll("[data-gallery]"));
  if (!dialog || !links.length) return;

  const image = dialog.querySelector(".sg-gallery__img");
  const count = dialog.querySelector("[data-gallery-count]");
  const caption = dialog.querySelector("[data-gallery-caption]");
  const close = dialog.querySelector("[data-gallery-close]");
  const previous = dialog.querySelector("[data-gallery-prev]");
  const next = dialog.querySelector("[data-gallery-next]");
  let index = 0;

  const show = (position) => {
    index = (position + links.length) % links.length;
    const link = links[index];
    image.src = link.dataset.full || link.href;
    image.alt = link.dataset.alt || "";
    caption.textContent = link.dataset.caption || "";
    count.textContent = `${index + 1} / ${links.length}`;
    previous.hidden = next.hidden = links.length < 2;
  };

  const open = (position) => {
    show(position);
    dialog.showModal();
    close.focus();
  };

  links.forEach((link, position) => {
    link.addEventListener("click", (event) => {
      if (event.metaKey || event.ctrlKey || event.shiftKey) return;
      event.preventDefault();
      open(position);
    });
  });

  close.addEventListener("click", () => dialog.close());
  previous.addEventListener("click", () => show(index - 1));
  next.addEventListener("click", () => show(index + 1));

  dialog.addEventListener("click", (event) => {
    if (event.target === dialog) dialog.close();
  });

  dialog.addEventListener("keydown", (event) => {
    if (event.key === "ArrowLeft") {
      event.preventDefault();
      show(index - 1);
    } else if (event.key === "ArrowRight") {
      event.preventDefault();
      show(index + 1);
    }
  });

  let startX = null;
  dialog.addEventListener("pointerdown", (event) => {
    startX = event.clientX;
  });
  dialog.addEventListener("pointerup", (event) => {
    if (startX === null) return;
    const distance = event.clientX - startX;
    startX = null;
    if (Math.abs(distance) > 45) show(index + (distance < 0 ? 1 : -1));
  });
})();
