/* Local vector icons, no icon font or network dependency. */
"use strict";
const IconPaths = Object.freeze({
  play: '<path d="M8 5.5 18 12 8 18.5Z" fill="currentColor" stroke="none"/>',
  pause: '<rect x="7" y="5" width="3.5" height="14" rx="1" fill="currentColor" stroke="none"/><rect x="13.5" y="5" width="3.5" height="14" rx="1" fill="currentColor" stroke="none"/>',
  up: '<path d="m7 10 5-5 5 5M12 5v14"/>',
  down: '<path d="m7 14 5 5 5-5M12 5v14"/>',
  trash: '<path d="M4 7h16M9 7V4h6v3M6 7l1 13h10l1-13M10 11v5M14 11v5"/>',
  ban: '<circle cx="12" cy="12" r="8"/><path d="m6.35 6.35 11.3 11.3"/>',
  close: '<path d="m6 6 12 12M18 6 6 18"/>',
  minimize: '<path d="M5 12h14"/>',
  maximize: '<rect x="5" y="5" width="14" height="14" rx="1.5"/>',
  restore: '<path d="M8 5V3h13v13h-2"/><rect x="3" y="8" width="13" height="13" rx="1.5"/>',
  next: '<path d="m5 5 10 7-10 7Z" fill="currentColor" stroke="none"/><path d="M18 5v14"/>',
  music: '<path d="M10 17V5l10-2v12M10 8l10-2"/><ellipse cx="6.5" cy="17.5" rx="3.5" ry="2.5"/><ellipse cx="16.5" cy="15.5" rx="3.5" ry="2.5"/>',
  plus: '<path d="M12 5v14M5 12h14"/>',
  opacity: '<circle cx="12" cy="12" r="8"/><path d="M12 4a8 8 0 0 1 0 16Z" fill="currentColor" stroke="none"/>',
  pin: '<path d="m8 4 8 0-1 6 3 4H6l3-4ZM12 14v7"/>',
  compact: '<path d="M5 6h14M5 12h14M5 18h14"/>',
  locate: '<circle cx="12" cy="12" r="6"/><circle cx="12" cy="12" r="2"/><path d="M12 2v3M12 19v3M2 12h3M19 12h3"/>',
});
function drawIcon(name) {
  const svg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
  svg.setAttribute("viewBox", "0 0 24 24");
  svg.setAttribute("class", "ui-icon");
  svg.setAttribute("fill", "none");
  svg.setAttribute("stroke", "currentColor");
  svg.setAttribute("stroke-width", "1.65");
  svg.setAttribute("stroke-linecap", "round");
  svg.setAttribute("stroke-linejoin", "round");
  svg.setAttribute("aria-hidden", "true");
  svg.setAttribute("focusable", "false");
  svg.dataset.icon = name;
  // Only fixed local geometry is inserted; no user-generated HTML.
  svg.innerHTML = IconPaths[name] || IconPaths.music;
  return svg;
}
function drawButtonLabel(button, icon, text) {
  button.replaceChildren(drawIcon(icon));
  if (text) {
    const label = document.createElement("span");
    label.textContent = text;
    button.appendChild(label);
  }
}
function initDrawnIcons() {
  document.querySelectorAll("[data-ui-icon]").forEach((node) => {
    node.replaceChildren(drawIcon(node.dataset.uiIcon));
  });
}
