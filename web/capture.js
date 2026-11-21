"use strict";
const $ = id => document.getElementById(id);
let stamp = "", currentId = null, busy = false;
function node(tag, cls, text) {
  const element = document.createElement(tag);
  if (cls) element.className = cls;
  if (text != null) element.textContent = String(text);
  return element;
}
let captureThemeRevision = null;
function renderCapture(view) {
  const active = view.customTheme;
  if (active?.payload) {
    if (captureThemeRevision !== active.revision) { ThemeRuntime.apply(active.payload, true); captureThemeRevision = active.revision; }
  } else {
    if (captureThemeRevision !== null) { ThemeRuntime.reset(); delete document.body.dataset.themeCompact; captureThemeRevision = null; }
    const theme = ["dark", "light", "haruka"].includes(active?.id || view.theme) ? (active?.id || view.theme) : "dark";
    document.documentElement.dataset.theme = theme;
  }
  if (view.window && !controlBusy && !opacitySending) applyPreferences(view.window);
  const snapshot = view.snapshot;
  const items = Array.isArray(snapshot?.items) ? snapshot.items : [];
  const current = items.find(item => item.id === snapshot?.current);
  const connected = view.connected === true;
  document.body.dataset.playing = String(!!current && connected && snapshot.playing);
  $("current-state").textContent = !connected ? (snapshot ? "已断开 · 上次播放" : "等待连接网易云") : current ? (snapshot.playing ? "正在播放" : "已暂停") : "尚未播放";
  $("current-name").textContent = current?.name || "尚未播放";
  $("current-singer").textContent = current?.singer || "";
  $("song-count").textContent = items.length + " 首";
  $("connection-note").textContent = view.message || (connected ? "网易云实时歌单" : "等待连接网易云");
  const nextStamp = JSON.stringify([snapshot, connected]);
  if (stamp === nextStamp) return;
  stamp = nextStamp;
  const list = $("songs"), scroll = list.scrollTop;
  list.replaceChildren();
  if (!items.length) list.appendChild(node("li", "empty", connected ? "歌单还是空的" : "连接网易云后显示歌单"));
  items.forEach((item, index) => {
    const active = item.id === snapshot.current;
    const row = node("li", "song" + (active ? " current" : ""));
    row.dataset.songId = item.id;
    if (active) row.setAttribute("aria-current", "true");
    const number = node("span", "song-number");
    if (active) number.appendChild(drawIcon(connected && snapshot.playing ? "play" : "pause"));
    else number.textContent = String(index + 1).padStart(2, "0");
    row.appendChild(number);
    const info = node("div", "song-info");
    info.appendChild(node("span", "song-name", item.name || "未知歌曲"));
    info.appendChild(node("span", "song-detail", [item.singer, item.requester && "点歌：" + item.requester].filter(Boolean).join(" · ")));
    row.appendChild(info);
    list.appendChild(row);
  });
  if (currentId !== snapshot?.current) {
    currentId = snapshot?.current;
    const row = list.querySelector('[aria-current="true"]');
    if (row) list.scrollTop = Math.max(0, row.offsetTop - list.offsetTop - 8);
  } else list.scrollTop = scroll;
}
async function refreshCapture() {
  if (busy || !window.pywebview?.api) return;
  busy = true;
  const revision = preferenceRevision;
  try {
    const view = await window.pywebview.api.get_view();
    if (revision !== preferenceRevision) delete view.window;
    renderCapture(view);
  }
  catch (_) {
    document.body.dataset.playing = "false";
    $("current-state").textContent = "同步中断 · 上次播放";
    $("connection-note").textContent = "同步中断 · 显示上次歌单";
  } finally { busy = false; }
}
let controlBusy = false, opacitySending = false, opacityQueued = null, messageTimer;
let preferenceRevision = 0;
let preferences = {opacity: 100, pinned: false, compact: false};
function toolMessage(text) {
  clearTimeout(messageTimer); $("tool-message").textContent = text;
  messageTimer = setTimeout(() => { $("tool-message").textContent = ""; }, 3500);
}
function applyPreferences(value) {
  preferences = value;
  document.body.dataset.compact = String(value.compact);
  $("opacity-label").textContent = value.opacity + "%";
  $("opacity-output").textContent = value.opacity + "%";
  $("opacity-range").value = value.opacity;
  $("btn-pin").setAttribute("aria-pressed", String(value.pinned));
  $("btn-pin").title = value.pinned ? "取消置顶" : "置顶小窗";
  $("btn-compact").setAttribute("aria-pressed", String(value.compact));
}
async function changePreference(method, value) {
  if (!window.pywebview?.api || controlBusy) return;
  controlBusy = true;
  preferenceRevision++;
  try { applyPreferences(await window.pywebview.api[method](value)); }
  catch (error) { toolMessage(error.message || String(error)); }
  finally { controlBusy = false; preferenceRevision++; }
}
async function changeOpacity(value) {
  opacityQueued = Number(value);
  if (opacitySending || !window.pywebview?.api) return;
  opacitySending = true;
  preferenceRevision++;
  try {
    while (opacityQueued !== null) {
      const next = opacityQueued; opacityQueued = null;
      const result = await window.pywebview.api.set_opacity(next);
      applyPreferences(result);
    }
  } catch (error) { toolMessage(error.message || String(error)); }
  finally { opacitySending = false; preferenceRevision++; }
}
function closeOpacity() {
  $("opacity-panel").classList.add("hidden");
  $("btn-opacity").setAttribute("aria-expanded", "false");
}
function bindTools() {
  initDrawnIcons();
  if (themePreview) return;
  $("btn-opacity").onclick = () => {
    const open = $("opacity-panel").classList.toggle("hidden") === false;
    $("btn-opacity").setAttribute("aria-expanded", String(open));
  };
  $("opacity-range").oninput = (event) => changeOpacity(event.target.value);
  document.querySelectorAll("[data-opacity]").forEach(b => { b.onclick = () => changeOpacity(b.dataset.opacity); });
  $("btn-pin").onclick = () => changePreference("set_pinned", !preferences.pinned);
  $("btn-compact").onclick = () => changePreference("set_compact", !preferences.compact);
  $("btn-current").onclick = () => {
    closeOpacity(); const row = $("songs").querySelector('[aria-current="true"]');
    if (row) $("songs").scrollTop = Math.max(0, row.offsetTop - $("songs").offsetTop - 8);
    else toolMessage("当前没有正在播放的歌曲");
  };
  $("btn-hide").onclick = async () => {
    closeOpacity();
    try { await window.pywebview.api.hide_window(); } catch(e) { toolMessage(e.message || String(e)); }
  };
  document.addEventListener("click", e => {
    if (!e.target.closest("#opacity-panel,#btn-opacity")) closeOpacity();
  });
  document.addEventListener("keydown", e => { if (e.key === "Escape") closeOpacity(); });
  document.querySelectorAll("[data-edge]").forEach(handle => {
    handle.addEventListener("pointerdown", async event => {
      if (!window.pywebview?.api) return;
      event.preventDefault(); handle.setPointerCapture(event.pointerId);
      const x = event.screenX, y = event.screenY, edge = handle.dataset.edge;
      let geom = null, queued = null, sending = false;
      const send = async () => {
        if (sending || !geom || !queued) return;
        sending = true;
        try {
          while (queued) {
            const [px, py] = queued; queued = null;
            const width = Math.max(300, Math.min(5000, geom.w + (edge.includes("e") ? px-x : edge.includes("w") ? x-px : 0)));
            const height = Math.max(280, Math.min(5000, geom.h + (edge.includes("s") ? py-y : edge.includes("n") ? y-py : 0)));
            await window.pywebview.api.resize_window(Math.round(width), Math.round(height), edge);
          }
        } catch(e) { toolMessage(e.message || String(e)); }
        finally { sending = false; }
      };
      handle.onpointermove = e => { queued = [e.screenX, e.screenY]; send(); };
      const stop = e => {
        if (e.type === "pointerup") { queued = [e.screenX, e.screenY]; send(); }
        handle.onpointermove = handle.onpointerup = handle.onpointercancel = null;
      };
      handle.onpointerup = handle.onpointercancel = stop;
      try { geom = await window.pywebview.api.get_geometry(); send(); }
      catch(e) { toolMessage(e.message || String(e)); }
    });
  });
}
document.addEventListener("DOMContentLoaded", bindTools);
if (themePreview) document.addEventListener("DOMContentLoaded", () => renderCapture({theme:"haruka",connected:true,message:"预览 · 模拟歌单",snapshot:{current:"2",playing:true,items:[{id:"1",name:"晴天",singer:"周杰伦"},{id:"2",name:"Lemon",singer:"米津玄師"}]}}));
window.addEventListener("pywebviewready", () => {
  if (themePreview) return;
  refreshCapture();
  setInterval(refreshCapture, 1500);
});
