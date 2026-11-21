/* B站点歌台 前端逻辑：状态拉取 + 事件轮询 + 界面渲染 */
"use strict";

const $ = (id) => document.getElementById(id);

const state = {
  account: null,
  roomid: "",
  listening: false,
  hasCookie: false,
  queue: [],      // {id, phase, name, singer, source, requester, manual, interval, ts}
  pendingSeq: {}, // "name|requester" -> id 关联 requested→queued
  seq: 0,
  playlist: null,
  playlistBusy: false,
  playlistRevision: 0,
  playlistStamp: "",
};

/* ---------------- 基础工具 ---------------- */

function escText(el, text) { el.textContent = text == null ? "" : String(text); return el; }

function el(tag, cls, text) {
  const n = document.createElement(tag);
  if (cls) n.className = cls;
  if (text != null) n.textContent = text;
  return n;
}

function fmtTime(ts) {
  const d = ts ? new Date(ts * 1000) : new Date();
  const p = (x) => String(x).padStart(2, "0");
  return `${p(d.getHours())}:${p(d.getMinutes())}:${p(d.getSeconds())}`;
}


function toast(text, kind) {
  const t = el("div", "toast" + (kind ? " " + kind : ""), text);
  $("toasts").appendChild(t);
  setTimeout(() => { t.style.opacity = "0"; t.style.transition = "opacity .3s"; }, 3200);
  setTimeout(() => t.remove(), 3600);
}

function api() { return !themePreview && window.pywebview && window.pywebview.api; }

function call(method, ...args) {
  const a = api();
  if (!a) { toast("界面尚未就绪", "err"); return Promise.reject(new Error("api not ready")); }
  return a[method](...args).catch((e) => { toast("操作失败: " + (e && e.message ? e.message : e), "err"); });
}

/* ---------------- 登录视图 ---------------- */

function loginView(show) { $("login-view").classList.toggle("hidden", !show); }

function setLoginText(t) { $("login-sub").textContent = t; }

function showQr(svgUrl) {
  $("qr-box").classList.remove("hidden");
  $("confirm-box").classList.add("hidden");
  $("qr-img").src = svgUrl;
  setLoginText("请用哔哩哔哩 APP 扫码登录");
}

function hideQr() { $("qr-box").classList.add("hidden"); }

function showConfirm(uname, uid) {
  $("qr-box").classList.add("hidden");
  $("confirm-box").classList.remove("hidden");
  escText($("confirm-uname"), uname);
  escText($("login-hint"), `UID: ${uid}`);
  setLoginText("是否使用该账号？");
}

/* ---------------- 顶栏状态 ---------------- */

function setConn(st, roomid) {
  const c = $("conn");
  c.dataset.state = st;
  const map = { open: "已连接", connecting: "连接中…", closed: "未连接" };
  escText($("conn-text"), map[st] || st);
  if (roomid) $("room-chip").textContent = "房间 " + roomid;
}

function setAccountChip() {
  $("account-chip").textContent = state.account ? state.account.uname : "未登录";
}

function setListenBtn() {
  const button = $("btn-listen");
  button.dataset.state = state.listening ? "ready" : "offline";
  button.setAttribute("aria-pressed", String(state.listening));
  button.title = state.listening ? "正在接收弹幕点歌，点击暂停" : "已暂停接收点歌，点击恢复";
  button.replaceChildren(el("span", "player-connection-dot"), el("span", null, state.listening ? "接单中 · 暂停" : "已暂停 · 恢复"));
  button.firstChild.setAttribute("aria-hidden", "true");
}


/* ---------------- 网易云真实歌单 ---------------- */

function addQueue(item) {
  state.queue.unshift(item);
  if (state.queue.length > 100) state.queue.length = 100;
  renderQueue();
}

function songDuration(seconds) {
  if (!Number.isFinite(seconds) || seconds <= 0) return "";
  return Math.floor(seconds / 60) + ":" + String(Math.floor(seconds % 60)).padStart(2, "0");
}

let songTipAnchor = null;
let songTipTimer = null;
function hideSongTip() {
  clearTimeout(songTipTimer);
  if (songTipAnchor) songTipAnchor.removeAttribute("aria-describedby");
  songTipAnchor = null;
  $("song-detail-tip")?.classList.add("hidden");
}
function showSongTip(anchor, item, snapshot) {
  hideSongTip();
  songTipAnchor = anchor;
  songTipTimer = setTimeout(() => {
    if (!anchor.isConnected) return;
    let tip = $("song-detail-tip");
    if (!tip) {
      tip = el("div", "song-detail-tip", "");
      tip.id = "song-detail-tip"; tip.setAttribute("role", "tooltip");
      $("app").appendChild(tip);
    }
    tip.replaceChildren(el("div", "song-tip-title", item.name));
    const details = [["歌手", item.singer || "未知"], ["点歌人", item.requester || "来源未记录"],
      ["时长", songDuration(item.duration) || "未知"], ["来源", "网易云音乐"],
      ["状态", item.id === snapshot.current ? (snapshot.playing ? "正在播放" : "已暂停") : "待播歌单"]];
    for (const [label, value] of details) {
      const line = el("div", "song-tip-field");
      line.append(el("span", "song-tip-label", label), el("span", "song-tip-value", value));
      tip.appendChild(line);
    }
    tip.classList.remove("hidden");
    anchor.setAttribute("aria-describedby", tip.id);
    const box = anchor.getBoundingClientRect();
    const width = tip.offsetWidth, height = tip.offsetHeight;
    const left = Math.max(12, Math.min(box.left, innerWidth - width - 12));
    let top = box.bottom + 8;
    if (top + height > innerHeight - 12) top = box.top - height - 8;
    tip.style.left = left + "px";
    tip.style.top = Math.max(12, top) + "px";
  }, 180);
}
window.addEventListener("resize", hideSongTip);
document.addEventListener("scroll", hideSongTip, true);
document.addEventListener("keydown", (event) => { if (event.key === "Escape") hideSongTip(); });
function renderQueue() {
  const list = $("queue-list");
  const scroll = list.scrollTop;
  hideSongTip();
  list.replaceChildren();
  const snapshot = state.playlist;
  const items = snapshot ? snapshot.items : [];
  $("queue-count").textContent = items.length + " 首";
  const current = items.find((item) => item.id === snapshot?.current);
  const toggle = $("btn-playlist-toggle");
  drawButtonLabel(toggle, current && snapshot.playing ? "pause" : "play");
  toggle.title = current && snapshot.playing ? "暂停播放" : "播放";
  toggle.setAttribute("aria-label", toggle.title);
  toggle.disabled = state.playlistBusy || !items.length;
  $("btn-playlist-clear").disabled = state.playlistBusy || !items.length;
  $("btn-skip").disabled = state.playlistBusy || items.length < 2;
  $("now-playing-name").textContent = current ? current.name : "尚未播放";
  $("now-playing-state").textContent = current ? (snapshot.playing ? "正在播放" : "已暂停") : "网易云实时歌单";
  $("now-playing").classList.toggle("is-playing", !!current && snapshot.playing);
  const pending = state.queue.filter((q) => q.phase === "requested").length;
  $("request-feedback").textContent = pending ? `${pending} 首歌曲正在搜索…` : "";
  if (!items.length) {
    const empty = el("div", "empty", snapshot ? "歌单还是空的" : "连接网易云后显示歌单");
    empty.appendChild(el("span", null, "弹幕发送「点歌 歌名 - 歌手」，歌手可省略；也可在下方点歌"));
    list.appendChild(empty);
    return;
  }
  items.forEach((item, index) => {
    const active = item.id === snapshot.current;
    const row = el("div", "queue-item playlist-row" + (active ? " current" : ""));
    row.dataset.songId = item.id;
    if (active) row.setAttribute("aria-current", "true");
    const icon = el("button", "q-icon song-toggle");
    icon.appendChild(drawIcon(active && snapshot.playing ? "pause" : "play"));
    icon.type = "button";
    icon.title = active && snapshot.playing ? "暂停" : active ? "继续播放" : "播放这首歌";
    icon.setAttribute("aria-label", icon.title + " · " + item.name);
    icon.disabled = state.playlistBusy;
    icon.onclick = () => editPlaylist(item.id, "toggle");
    row.appendChild(icon);
    const main = el("div", "q-main song-summary");
    main.tabIndex = 0;
    main.append(el("span", "q-title", item.name), el("span", "song-requester", item.requester || "来源未记录"));
    main.addEventListener("mouseenter", () => showSongTip(main, item, snapshot));
    main.addEventListener("mouseleave", hideSongTip);
    main.addEventListener("focus", () => showSongTip(main, item, snapshot));
    main.addEventListener("blur", hideSongTip);
    row.appendChild(main);
    const actions = el("div", "song-actions");
    [["up", "上移", "move", -1, index === 0], ["down", "下移", "move", 1, index === items.length - 1], ["ban", "拉黑歌曲", "blacklist", 0, false], ["trash", "从歌单删除", "delete", 0, false]].forEach(([glyph, label, command, direction, boundary]) => {
      const button = el("button", "song-action" + (command === "delete" ? " song-delete" : command === "blacklist" ? " song-blacklist" : ""));
      button.appendChild(drawIcon(glyph));
      button.type = "button"; button.title = label;
      button.setAttribute("aria-label", label + " · " + item.name);
      button.disabled = state.playlistBusy || boundary;
      button.onclick = async () => {
        if (command === "blacklist") { blacklistSong(item); return; }
        if (command === "delete" && active && !await ConfirmDialog.ask({title:"删除当前歌曲", message:"删除后网易云可能切换到其他歌曲，确定删除？", confirmText:"删除歌曲", danger:true})) return;
        editPlaylist(item.id, command, direction);
      };
      actions.appendChild(button);
    });
    row.appendChild(actions);
    list.appendChild(row);
  });
  list.scrollTop = scroll;
}

function applyPlaylist(snapshot) {
  if (!snapshot || !Array.isArray(snapshot.items)) throw new Error("网易云歌单数据无效");
  const stamp = JSON.stringify(snapshot);
  const previousCurrent = state.playlist?.current;
  state.playlist = snapshot;
  if (state.playlistStamp !== stamp) {
    state.playlistStamp = stamp;
    renderQueue();
    if (previousCurrent !== snapshot.current) {
      const current = $("queue-list").querySelector('[aria-current="true"]');
      if (current) $("queue-list").scrollTop = Math.max(0, current.offsetTop - $("queue-list").offsetTop - 16);
    }
  }
}

async function blacklistSong(item) {
  if (!api() || state.playlistBusy) return;
  if (!await ConfirmDialog.ask({title:"拉黑歌曲", message:`拉黑「${item.name}」？\n后续弹幕点播该完整歌名（包括同名不同歌手）将被拦截。\n不会删除队列或中断当前播放；可在设置的黑名单中解除。`, confirmText:"拉黑歌曲", danger:true})) return;
  if (state.playlistBusy) return;
  state.playlistBusy = true;
  state.playlistRevision++;
  renderQueue();
  try {
    const result = await api().blacklist_song(item.id);
    toast(result.added ? `已拉黑「${result.name}」，立即生效` : `「${result.name}」已在黑名单中`, "ok");
  } catch (error) {
    toast("拉黑失败：" + (error.message || error), "err");
  } finally {
    state.playlistBusy = false;
    state.playlistRevision++;
    renderQueue();
  }
}
async function clearPlaylist() {
  if (!api() || state.playlistBusy || !state.playlist?.items.length) return;
  const ids = state.playlist.items.map(item => item.id);
  if (!await ConfirmDialog.ask({title:"清空当前歌单", message:`确定清空网易云当前列表中的 ${ids.length} 首歌曲？\n这会移除待播曲目，可能停止当前播放；不会删除收藏或本地音乐文件。`, confirmText:"清空列表", danger:true})) return;
  if (state.playlistBusy) return;
  state.playlistBusy = true; state.playlistRevision++; renderQueue();
  try {
    applyPlaylist(await api().clear_playlist(ids));
    toast("当前歌单已清空", "ok");
  } catch (error) { toast("清空失败：" + (error.message || error), "err"); }
  finally { state.playlistBusy = false; state.playlistRevision++; renderQueue(); }
}
async function editPlaylist(songId, command, direction = 0) {
  if (!api() || state.playlistBusy) return;
  state.playlistBusy = true;
  state.playlistRevision++;
  renderQueue();
  try {
    const snapshot = await api().playlist_action(songId, command, direction);
    applyPlaylist(snapshot);
  } catch (error) {
    toast("歌单操作失败：" + (error.message || error), "err");
  } finally {
    state.playlistBusy = false;
    state.playlistRevision++;
    renderQueue();
    refreshPlayerStatus();
  }
}

/* ---------------- 事件处理 ---------------- */

function applyEvent(e) {
  switch (e.type) {
    case "login": {
      if (e.phase === "checking") { loginView(true); setLoginText("正在检查本地登录状态…"); }
      else if (e.phase === "confirm") { loginView(true); showConfirm(e.uname, e.uid); }
      else if (e.phase === "switching") { loginView(true); setLoginText("正在切换账号…"); hideQr(); }
      else if (e.phase === "ok") {
        state.account = { uname: e.uname, uid: e.uid };
        setAccountChip();
        hideQr();
        $("confirm-box").classList.add("hidden");
        loginView(false);
        toast("已登录：" + e.uname, "ok");
      } else if (e.phase === "guest") {
        state.account = null;
        setAccountChip();
        loginView(false);
        toast("未登录，弹幕用户名会打码显示", "err");
      }
      break;
    }
    case "qr": {
      if (e.action === "show") { loginView(true); e.svg ? showQr(e.svg) : setLoginText("二维码生成失败，请查看控制台日志"); }
      else hideQr();
      break;
    }
    case "need_roomid": {
      openSettings();
      toast("请先在设置中填写直播间房间号");
      break;
    }
    case "conn": {
      state.listening = e.state === "open";
      setConn(e.state, e.roomid || state.roomid);
      setListenBtn();
      if (e.state === "open") toast("已连接直播间 " + (e.roomid || state.roomid), "ok");
      if (e.state === "closed") toast("弹幕监听已断开");
      break;
    }
    case "danmaku": break; // 仅后台解析点歌，不展示普通弹幕
    case "song": {
      if (e.phase === "requested") {
        const key = e.request_id;
        const id = "q" + (++state.seq);
        state.pendingSeq[key] = id;
        addQueue({ id, phase: "requested", name: e.name, singer: e.singer, source: "", requester: e.requester, manual: e.manual, interval: "", ts: Date.now() / 1000 });
      } else {
        const key = e.request_id;
        const pendId = state.pendingSeq[key];
        if (pendId) {
          const idx = state.queue.findIndex((q) => q.id === pendId);
          if (idx >= 0) state.queue.splice(idx, 1);
          delete state.pendingSeq[key];
        }
        addQueue({ id: "q" + (++state.seq), phase: e.phase, error: e.error, name: e.name, singer: e.singer, source: e.source, requester: e.requester, manual: e.manual, interval: e.interval || "", ts: Date.now() / 1000 });
        if (e.phase === "queued") refreshPlayerStatus();
      }
      break;
    }
    case "song_blocked": toast(`「${e.name}」在黑名单中，已拦截（${e.requester}）`); break;
    case "skipped": toast("已切歌（" + e.by + "）"); refreshPlayerStatus(); break;
    case "log": {
      if (typeof e.text === "string" && e.text.indexOf("[错误]") >= 0) toast(e.text, "err");
      console.log(e.text);
      break;
    }
  }
}

function pollOnce() {
  const a = api();
  if (!a) return;
  a.poll_events().then((events) => {
    if (Array.isArray(events)) events.forEach(applyEvent);
    // 同步监听状态兜底
    return a.get_state().then((s) => {
      state.roomid = s.roomid || "";
      if (s.account) { state.account = s.account; setAccountChip(); }
      if (!s.listening && state.listening && $("conn").dataset.state === "open") {
        state.listening = false; setConn("closed"); setListenBtn();
      }
      if (!$("room-chip").textContent || $("room-chip").textContent === "房间 —") {
        $("room-chip").textContent = s.roomid ? "房间 " + s.roomid : "房间 —";
      }
    });
  }).catch(() => {});
}

/* ---------------- 设置弹窗 ---------------- */

function openSettings() {
  $("modal-settings").classList.remove("hidden");
  $("input-roomid").value = state.roomid || "";
  $("account-note").textContent = state.account
    ? `当前：${state.account.uname}（UID ${state.account.uid}）`
    : "当前：未登录（弹幕用户名会打码）";
  call("get_blacklist").then((t) => { $("input-blacklist").value = t || ""; });
  if (api()?.get_queue_policy) api().get_queue_policy().then(p => {
    $("queue-limit-enabled").checked = p.enabled;
    $("queue-limit-maximum").value = p.maximum;
  }).catch(e => toast("读取队列设置失败：" + (e.message || e), "err"));
  refreshPlayerStatus();
}

let playerReady = false;
let playerChecking = false;
let playerConnecting = false;

function setPlayerConnection(phase, message) {
  playerReady = phase === "ready";
  const labels = {ready: "网易云 · 已连接", offline: "网易云 · 未连接", checking: "网易云 · 检测中", connecting: "网易云 · 连接中"};
  const button = $("btn-player-connect");
  button.dataset.state = phase;
  button.title = message || labels[phase];
  button.disabled = phase === "connecting";
  $("player-connection-text").textContent = labels[phase];
  $("player-status").textContent = message || labels[phase];
  $("player-status").dataset.state = phase;
}

async function refreshPlayerStatus() {
  if (!api() || playerChecking || playerConnecting || state.playlistBusy) return;
  playerChecking = true;
  const revision = state.playlistRevision;
  try {
    const snapshot = await api().get_playlist();
    if (revision !== state.playlistRevision) return;
    applyPlaylist(snapshot);
    setPlayerConnection("ready", "网易云已连接 · 歌单实时同步");
    const modes = {playAi: "AI 模式", playRandom: "随机模式", playOne: "单曲循环", playOrder: "顺序播放", playLoop: "列表循环"};
    $("playlist-sync-note").textContent = "网易云同步 · " + (modes[snapshot.mode] || "当前播放模式");
  } catch (error) {
    if (revision !== state.playlistRevision) return;
    setPlayerConnection("offline", "网易云检测失败：" + (error.message || error));
    $("playlist-sync-note").textContent = "连接已断开 · 显示上次歌单";
  } finally { playerChecking = false; }
}

async function connectPlayer() {
  if (!api() || playerConnecting) return;
  if (playerReady) { await refreshPlayerStatus(); return; }
  playerConnecting = true;
  setPlayerConnection("connecting", "正在启动网易云控制模式…");
  try {
    const status = await api().launch_player();
    setPlayerConnection(status.ready ? "ready" : "connecting", status.message);
    if (!status.ready) toast(status.message);
  } catch (error) {
    const message = error.message || String(error);
    setPlayerConnection("offline", message);
    toast(message, "err");
  } finally {
    playerConnecting = false;
    await refreshPlayerStatus();
    setTimeout(refreshPlayerStatus, 2000);
  }
}
function closeSettings() { $("modal-settings").classList.add("hidden"); }

/* ---------------- 直播捕捉小窗 ---------------- */
let captureBusy = false;
function applyCaptureState(value) {
  if (!value || typeof value.visible !== "boolean") return;
  $("btn-capture-toggle").textContent = value.visible ? "收回小窗" : "召唤小窗";
  $("btn-capture-toggle").setAttribute("aria-pressed", String(value.visible));
}
async function refreshCaptureState() {
  if (!api()?.capture_state || captureBusy) return;
  try { applyCaptureState(await api().capture_state()); } catch (_) { /* 下一轮重试 */ }
}
async function captureAction(method) {
  if (captureBusy || !api()?.[method]) return;
  captureBusy = true;
  $("btn-capture-toggle").disabled = $("btn-capture-reset").disabled = true;
  try {
    applyCaptureState(await api()[method]());
    if (method === "reset_capture_position") toast("小窗位置已重置；尚未召唤时，下次将在默认位置打开");
  } catch (error) { toast("小窗操作失败：" + (error.message || error), "err"); }
  finally {
    captureBusy = false;
    $("btn-capture-toggle").disabled = $("btn-capture-reset").disabled = false;
  }
}
/* ---------------- 初始化 ---------------- */

function bindEvents() {
  // 拖拽区内的按钮不能把 mousedown 冒泡给 pywebview 的拖拽监听器。
  document.querySelectorAll(".windowbar button").forEach((button) => {
    button.addEventListener("mousedown", (event) => event.stopPropagation());
  });
  $("btn-player-connect").onclick = connectPlayer;
  $("btn-use-account").onclick = () => { $("confirm-box").classList.add("hidden"); setLoginText("正在进入…"); call("confirm_use_account", true); };
  $("btn-switch-account").onclick = () => { $("confirm-box").classList.add("hidden"); setLoginText("等待扫码…"); call("confirm_use_account", false); };

  $("btn-theme").onclick = () => {
    const open = $("theme-menu").classList.contains("hidden");
    $("theme-menu").classList.toggle("hidden", !open);
    $("btn-theme").setAttribute("aria-expanded", String(open));
    if (open && api()?.theme_catalog) refreshThemeCatalog().catch(e=>toast(e.message || String(e), "err"));
  };
  document.querySelectorAll("[data-theme-choice]").forEach((button) => {
    button.onclick = () => { setTheme(button.dataset.themeChoice); closeThemeMenu(); };
  });
  document.addEventListener("click", (event) => {
    if (!event.target.closest(".theme-picker")) closeThemeMenu();
  });
  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape") { closeThemeMenu(); closeSettings(); }
  });

  $("btn-settings").onclick = openSettings;
  $("btn-author-bilibili").onclick = () => call("open_author_bilibili");

  // 无边框窗口控制
  $("btn-min").onclick = () => call("win_minimize");
  $("btn-max").onclick = () => {
    const maximized = document.documentElement.dataset.maximized === "true";
    call(maximized ? "win_restore" : "win_maximize");
  };
  $("btn-close").onclick = () => call("win_close");
  $("btn-close-settings").onclick = closeSettings;
  $("modal-settings").addEventListener("click", (e) => { if (e.target === $("modal-settings")) closeSettings(); });

  $("btn-save-roomid").onclick = () => {
    const v = $("input-roomid").value.trim();
    call("start_listen", v).then(() => { state.roomid = v; closeSettings(); });
  };

  $("btn-rescan").onclick = () => {
    closeSettings();
    loginView(true);
    setLoginText("正在准备扫码…");
    call("switch_account");
  };

  $("btn-save-queue-policy").onclick = async () => {
    const enabled = $("queue-limit-enabled").checked;
    const maximum = Number($("queue-limit-maximum").value);
    if (!Number.isInteger(maximum) || maximum < 1 || maximum > 500) { toast("请输入1至500的整数", "err"); return; }
    if (enabled && !await ConfirmDialog.ask({title:"启用消费队列", message:`上限 ${maximum} 首，含当前歌曲。将切换为顺序播放，播完或点下一首后移除上一首；现有超额歌曲保留。是否启用？`,confirmText:"启用"})) return;
    const button = $("btn-save-queue-policy"); button.disabled = true;
    try {
      await api().save_queue_policy(enabled, maximum);
      toast(enabled ? "消费队列已启用，满额将拒绝新点歌" : "已关闭容量限制和自动清理", "ok");
    } catch(e) { toast("保存失败：" + (e.message || e), "err"); }
    finally { button.disabled = false; }
  };
  $("btn-save-blacklist").onclick = () => {
    call("save_blacklist", $("input-blacklist").value).then(() => toast("黑名单已保存，立即生效", "ok"));
  };

  $("btn-request").onclick = doRequest;
  $("btn-capture-toggle").onclick = () => captureAction("toggle_capture");
  $("btn-capture-reset").onclick = () => captureAction("reset_capture_position");
  $("input-song").addEventListener("keydown", (e) => { if (e.key === "Enter") doRequest(); });
  $("input-singer").addEventListener("keydown", (e) => { if (e.key === "Enter") doRequest(); });

  $("btn-skip").onclick = () => call("skip_next");
  $("btn-playlist-toggle").onclick = () => {
    const snapshot = state.playlist;
    if (!snapshot?.items.length) return;
    const current = snapshot.items.find(item => item.id === snapshot.current) || snapshot.items[0];
    editPlaylist(current.id, "toggle");
  };
  $("btn-playlist-clear").onclick = clearPlaylist;

  $("btn-listen").onclick = () => {
    if (state.listening) {
      call("stop_listen");
    } else {
      const roomid = state.roomid || $("input-roomid").value.trim();
      if (!roomid) { openSettings(); toast("请先填写直播间房间号"); return; }
      call("start_listen", roomid);
    }
  };

  $("room-chip").onclick = () => call("open_room_page");
}

/* ---------------- 无边框窗口缩放手柄 ---------------- */

function bindResizeHandles() {
  document.querySelectorAll(".rh").forEach((h) => {
    h.addEventListener("pointerdown", (ev) => {
      ev.preventDefault();
      h.setPointerCapture(ev.pointerId);
      const dir = h.dataset.rh;
      const sx = ev.screenX, sy = ev.screenY;
      let startW = 0, startH = 0, ready = false, queued = null, lastSend = 0;

      const a = window.pywebview && window.pywebview.api;
      if (!a) return;
      a.win_get_geom().then((g) => {
        startW = g.w; startH = g.h; ready = true;
        if (queued) { queued(); queued = null; }
      });

      const apply = (nx, ny) => {
        const now = performance.now();
        if (now - lastSend < 16) return;
        lastSend = now;
        const dx = nx - sx, dy = ny - sy;
        let w = startW, hh = startH;
        if (dir.includes("e")) w = startW + dx;
        if (dir.includes("w")) w = startW - dx;
        if (dir.includes("s")) hh = startH + dy;
        if (dir.includes("n")) hh = startH - dy;
        a.win_resize(Math.round(w), Math.round(hh), dir).catch(() => {});
      };

      h.onpointermove = (e2) => {
        if (!ready) { queued = () => apply(e2.screenX, e2.screenY); return; }
        apply(e2.screenX, e2.screenY);
      };
      const stop = () => { h.onpointermove = h.onpointerup = h.onpointercancel = null; };
      h.onpointerup = h.onpointercancel = stop;
    });
  });
}

function doRequest() {
  const name = $("input-song").value.trim();
  const singer = $("input-singer").value.trim();
  if (!name) { toast("请输入歌名"); return; }
  call("request_song", name, singer);
  $("input-song").value = "";
  $("input-singer").value = "";
}

function closeThemeMenu() {
  $("theme-menu").classList.add("hidden");
  closeThemeContext();
  $("btn-theme").setAttribute("aria-expanded", "false");
}

let customThemeCatalog = [], themeRevision = null, themeSyncBusy = false;
let applyingBackendTheme = false;
async function syncThemeState() {
  if (!api()?.theme_state || themeSyncBusy) return;
  themeSyncBusy = true;
  try {
    const result = await api().theme_state(themeRevision);
    if (result.revision === themeRevision) return;
    themeRevision = result.revision;
    applyingBackendTheme = true;
    if (result.payload) {
      ThemeRuntime.apply(result.payload);
      $("btn-theme").textContent = "主题";
      $("btn-theme").title = result.payload.config.name;
      document.querySelectorAll("[data-theme-choice]").forEach(b=>b.setAttribute("aria-checked",String(b.dataset.themeChoice===result.id)));
    } else setTheme(result.id);
    if (result.warning) toast(result.warning, "err");
    await refreshThemeCatalog();
  } catch(e) { toast("主题加载失败：" + (e.message || e), "err"); }
  finally { applyingBackendTheme = false; themeSyncBusy = false; }
}
let themeDeleteBusy = false;
function closeThemeContext() {
  $("theme-context-menu")?.remove();
}
function showThemeContext(event, theme) {
  event.preventDefault(); event.stopPropagation();
  closeThemeContext();
  const menu = el("div", "theme-context-menu");
  menu.id = "theme-context-menu"; menu.setAttribute("role", "menu");
  menu.setAttribute("aria-label", "主题操作 · " + theme.name);
  const remove = el("button", "theme-delete-action");
  remove.type = "button"; remove.setAttribute("role", "menuitem");
  drawButtonLabel(remove, "trash", "删除此主题");
  remove.disabled = themeDeleteBusy;
  remove.onclick = async e => {
    e.stopPropagation(); closeThemeContext();
    if (themeDeleteBusy || !api()?.delete_theme) return;
    const active = document.documentElement.dataset.customTheme === theme.id;
    if (!await ConfirmDialog.ask({title:"删除主题", message:`删除主题「${theme.name}」？${active ? "当前界面将切回经典深色。" : ""}删除后可通过主题包重新导入。`, confirmText:"删除主题", danger:true})) return;
    themeDeleteBusy = true;
    try {
      await api().delete_theme(theme.id);
      await syncThemeState();
      await refreshThemeCatalog();
      toast("主题已删除"); closeThemeMenu();
    } catch (error) { toast("删除失败：" + (error.message || error), "err"); }
    finally { themeDeleteBusy = false; }
  };
  menu.appendChild(remove); $("app").appendChild(menu);
  const anchor = event.currentTarget.getBoundingClientRect();
  const x = event.clientX || anchor.left, y = event.clientY || anchor.bottom;
  menu.style.left = Math.max(8, Math.min(x, innerWidth - menu.offsetWidth - 8)) + "px";
  menu.style.top = Math.max(8, Math.min(y, innerHeight - menu.offsetHeight - 8)) + "px";
  remove.focus({preventScroll:true});
}
window.addEventListener("resize", closeThemeContext);
document.addEventListener("scroll", closeThemeContext, true);
document.addEventListener("click", event => {
  if (!event.target.closest("#theme-context-menu")) closeThemeContext();
});
async function refreshThemeCatalog() {
  if (!api()?.theme_catalog) return;
  customThemeCatalog = await api().theme_catalog();
  document.querySelectorAll(".custom-theme-choice").forEach(b=>b.remove());
  customThemeCatalog.forEach(theme=>{
    const button = el("button", "custom-theme-choice", theme.name);
    button.dataset.themeChoice = theme.id; button.setAttribute("role", "menuitemradio");
    button.setAttribute("aria-checked", String(document.documentElement.dataset.customTheme===theme.id));
    button.onmousedown = e=>e.stopPropagation();
    button.title = theme.name + " · 右键删除";
    button.oncontextmenu = event => showThemeContext(event, theme);
    button.onclick = async()=>{
      try { await api().select_theme(theme.id); await syncThemeState(); closeThemeMenu(); }
      catch(e) { toast(e.message || String(e), "err"); }
    };
    $("btn-theme-workshop").before(button);
  });
}
function setTheme(theme) {
  const names = {dark: "经典 · 深色", light: "经典 · 浅色", haruka: "主题布局模板"};
  const selected = Object.hasOwn(names, theme) ? theme : "dark";
  ThemeRuntime.reset();
  document.documentElement.dataset.theme = selected;
  $("btn-theme").textContent = selected === "haruka" ? "玫瑰夜曲" : "主题";
  $("btn-theme").title = names[selected];
  document.querySelectorAll("[data-theme-choice]").forEach((button) => {
    button.setAttribute("aria-checked", String(button.dataset.themeChoice === selected));
  });
  try { localStorage.setItem("theme", selected); } catch (_) { /* 可在禁用存储时使用 */ }
  if (api()?.set_capture_theme) api().set_capture_theme(selected).catch(() => {});
  if (!applyingBackendTheme && api()?.select_theme && !themePreview) {
    api().select_theme(selected).then(syncThemeState).catch(e=>toast(e.message || String(e), "err"));
  }
}
function init() {
  let theme = "dark";
  try { theme = localStorage.getItem("theme") || "dark"; } catch (_) { /* 无持久存储 */ }
  applyingBackendTheme = true;
  setTheme(theme);
  applyingBackendTheme = false;
  setConn("closed");
  bindResizeHandles();
  bindEvents();
  initDrawnIcons();
  drawButtonLabel($("btn-request"), "plus", "点歌");
  drawButtonLabel($("btn-skip"), "next");
  setListenBtn();
  // 同步系统最大化/还原导致的图标变化（包括标题栏双击）。
  new MutationObserver(() => {
    drawButtonLabel($("btn-max"), document.documentElement.dataset.maximized === "true" ? "restore" : "maximize");
  }).observe(document.documentElement, {attributes: true, attributeFilter: ["data-maximized"]});
  renderQueue();
  $("btn-theme-workshop").onclick = () => { closeThemeMenu(); call("open_theme_workshop"); };
  if (themePreview) {
    applyPlaylist({current: "2", playing: true, mode:"playOrder", items:[
      {id:"1",name:"晴天",singer:"周杰伦",duration:269,requester:"观众小明"},
      {id:"2",name:"Lemon",singer:"米津玄師",duration:255,requester:"观众小花"},
      {id:"3",name:"夜に駆ける",singer:"YOASOBI",duration:261,requester:"手动点歌"}]});
    return;
  }

  window.addEventListener("pywebviewready", () => {
    const a = api();
    if (a.frontend_ready) a.frontend_ready().then(() => { window.__songdeskFrontendReady = true; }).catch(console.error);
    if (a.theme_state) { syncThemeState(); setInterval(syncThemeState, 1000); }
    else if (a.set_capture_theme) a.set_capture_theme(document.documentElement.dataset.theme).catch(() => {});
    refreshCaptureState();
    setInterval(refreshCaptureState, 1000);
    a.get_state().then((s) => {
      state.roomid = s.roomid || "";
      state.account = s.account;
      setAccountChip();
      if (s.roomid) setConn("closed", s.roomid);
    });
    setInterval(pollOnce, 380);
    pollOnce();
    refreshPlayerStatus();
    setInterval(refreshPlayerStatus, 1500);
  });
}

document.addEventListener("DOMContentLoaded", init);
