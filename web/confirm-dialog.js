/* Shared themed, async confirmation dialog. Uses textContent only. */
"use strict";
const ConfirmDialog = (() => {
  let pending = null;
  function ask({title = "确认操作", message, confirmText = "确认", danger = false}) {
    if (pending) return Promise.resolve(false);
    const previous = document.activeElement;
    const overlay = document.createElement("div"); overlay.className = "confirm-overlay";
    const card = document.createElement("section"); card.className = "confirm-card";
    card.setAttribute("role", "alertdialog"); card.setAttribute("aria-modal", "true");
    card.setAttribute("aria-labelledby", "confirm-dialog-title"); card.setAttribute("aria-describedby", "confirm-dialog-message");
    const heading = document.createElement("h2"); heading.id = "confirm-dialog-title"; heading.textContent = title;
    const body = document.createElement("p"); body.id = "confirm-dialog-message"; body.textContent = message;
    const actions = document.createElement("div"); actions.className = "confirm-actions";
    const cancel = document.createElement("button"); cancel.type = "button"; cancel.textContent = "取消";
    cancel.dataset.confirmCancel = "true";
    const accept = document.createElement("button"); accept.type = "button"; accept.textContent = confirmText;
    accept.dataset.confirmAccept = "true"; accept.className = danger ? "confirm-danger" : "confirm-primary";
    actions.append(cancel, accept); card.append(heading, body, actions); overlay.appendChild(card);
    return new Promise(resolve => {
      function finish(value) {
        if (!pending) return;
        pending = null; document.removeEventListener("keydown", keydown, true); overlay.remove();
        if (previous?.isConnected) previous.focus({preventScroll:true});
        resolve(value);
      }
      function keydown(event) {
        if (event.key === "Escape") { event.preventDefault(); event.stopImmediatePropagation(); finish(false); }
        else if (event.key === "Tab") {
          event.preventDefault(); (document.activeElement === cancel ? accept : cancel).focus();
        }
      }
      pending = finish;
      cancel.onclick = () => finish(false); accept.onclick = () => finish(true);
      overlay.onclick = event => { if (event.target === overlay) finish(false); };
      document.addEventListener("keydown", keydown, true);
      document.body.appendChild(overlay); cancel.focus({preventScroll:true});
    });
  }
  return {ask};
})();
