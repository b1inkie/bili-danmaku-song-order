/* UI-only update rehearsal. No network, filesystem, shell, restart or bridge calls. */
"use strict";
class UpdatePreviewModel {
  static FIRST_CHECK_MS = 5000;
  static CHECK_INTERVAL_MS = 4 * 60 * 60 * 1000;
  constructor(changed, clock = globalThis) {
    this.changed = changed;
    this.clock = clock;
    this.operation = null;
    this.firstCheck = null;
    this.interval = null;
    this.scenario = "available";
    this.state = {phase: "idle", progress: 0, current: "0.1.0", latest: null,
      available: false, backup: null, checkedAt: null,
      message: "尚未检查。此处版本号和更新信息均为演示数据。"};
  }
  emit(change) { Object.assign(this.state, change); this.changed({...this.state}); }
  busy() { return ["checking", "downloading", "verifying", "installing"].includes(this.state.phase); }
  start() {
    if (this.firstCheck !== null || this.interval !== null) return;
    this.firstCheck = this.clock.setTimeout(() => {
      this.firstCheck = null;
      if (!this.busy() && this.state.phase !== "ready") this.check();
      this.interval = this.clock.setInterval(() => {
        if (!this.busy() && this.state.phase !== "ready") this.check();
      }, UpdatePreviewModel.CHECK_INTERVAL_MS);
    }, UpdatePreviewModel.FIRST_CHECK_MS);
  }
  later(callback, delay) {
    this.operation = this.clock.setTimeout(() => { this.operation = null; callback(); }, delay);
  }
  clearOperation() {
    if (this.operation !== null) this.clock.clearTimeout(this.operation);
    this.operation = null;
  }
  check() {
    if (this.busy() || this.state.phase === "ready") return;
    const scenario = this.scenario;
    this.emit({phase: "checking", message: "模拟检查中…不会访问 GitHub。"});
    this.later(() => {
      const checkedAt = new Date().toLocaleTimeString();
      if (scenario === "check-error") {
        this.emit({phase: "check-error", checkedAt, message: "模拟网络超时：保留已有检查结果，可重新检查。"});
      } else if (scenario === "latest" || this.state.current === "0.2.0") {
        this.emit({phase: "latest", checkedAt, latest: this.state.current, available: false,
          message: "模拟检查完成：当前已是最新版。"});
      } else {
        this.emit({phase: "available", checkedAt, latest: "0.2.0", available: true,
          message: "模拟发现 v0.2.0。可下载演示，或稍后处理。"});
      }
    }, 750);
  }
  download() {
    if (this.busy() || !this.state.available || this.state.phase === "ready") return;
    const shouldFail = this.scenario === "download-error";
    this.emit({phase: "downloading", progress: 0, message: "模拟下载中…不会下载任何文件。"});
    const step = () => {
      const progress = Math.min(100, this.state.progress + 10);
      if (shouldFail && progress >= 50) {
        this.emit({phase: "download-error", progress, message: "模拟下载失败：文件未写入，可重试或切换场景。"});
        return;
      }
      this.emit({progress});
      if (progress < 100) this.later(step, 180);
      else {
        this.emit({phase: "verifying", message: "模拟校验中…此步骤不代表真实签名或哈希校验。"});
        this.later(() => this.emit({phase: "ready", message: "模拟更新已就绪。可演示重启确认，不会退出程序。"}), 650);
      }
    };
    this.later(step, 180);
  }
  cancel() {
    if (!["downloading", "verifying"].includes(this.state.phase)) return;
    this.clearOperation();
    this.emit({phase: "available", progress: 0, message: "已取消模拟下载，没有更改程序文件。"});
  }
  install() {
    if (this.state.phase !== "ready") return;
    this.emit({phase: "installing", message: "模拟安装与启动确认…主窗、小窗及播放器均不会被关闭。"});
    this.later(() => this.emit({phase: "complete", current: "0.2.0", backup: "0.1.0",
      available: false, progress: 0, message: "演示完成：模拟版本已更新。真实程序与用户数据未改变。"}), 900);
  }
  rollback() {
    if (this.busy() || !this.state.backup) return;
    this.clearOperation();
    this.emit({phase: "idle", current: "0.1.0", backup: null, latest: null, available: false,
      progress: 0, message: "已模拟回退上一版。未执行任何文件替换或重启。"});
  }
  reset() {
    this.clearOperation();
    this.emit({phase: "idle", current: "0.1.0", latest: null, available: false, backup: null,
      progress: 0, checkedAt: null, message: "演示已重置，可重新检查。真实版本未改变。"});
  }
  stop() {
    this.clearOperation();
    if (this.firstCheck !== null) this.clock.clearTimeout(this.firstCheck);
    if (this.interval !== null) this.clock.clearInterval(this.interval);
    this.firstCheck = this.interval = null;
  }
}

if (typeof module !== "undefined" && module.exports) module.exports = {UpdatePreviewModel};
if (typeof document !== "undefined") {
  window.UpdatePreview = (() => {
    let model;
    const get = id => document.getElementById(id);
    const labels = {idle: "未检查", checking: "检查中", available: "发现新版", latest: "已是最新版",
      downloading: "下载中", verifying: "校验中", ready: "等待重启", installing: "模拟安装中",
      complete: "演示完成", "check-error": "检查失败", "download-error": "下载失败"};
    function render(s) {
      const badge = get("settings-update-badge"), button = get("btn-settings");
      badge.classList.toggle("hidden", !s.available);
      badge.dataset.ready = String(s.phase === "ready");
      button.setAttribute("aria-label", s.available ? "设置，有模拟更新" : "设置");
      button.title = s.available ? (s.phase === "ready" ? "模拟更新已就绪" : "有模拟新版本") : "设置";
      get("update-demo-current").textContent = "v" + s.current + "（模拟）";
      get("update-demo-latest").textContent = s.latest ? "v" + s.latest + "（模拟）" : "—";
      get("update-demo-backup").textContent = s.backup ? "v" + s.backup + "（模拟备份）" : "无";
      get("update-demo-time").textContent = s.checkedAt || "尚未检查";
      const status = get("update-demo-status");
      status.textContent = labels[s.phase]; status.dataset.phase = s.phase;
      get("update-demo-message").textContent = s.message;
      get("update-demo-notes").classList.toggle("hidden", !s.available);
      get("update-demo-progress-box").classList.toggle("hidden", !["downloading", "verifying"].includes(s.phase));
      get("update-demo-progress").value = s.progress;
      get("update-demo-percent").textContent = s.progress + "%";
      get("update-demo-check").disabled = model.busy() || s.phase === "ready";
      get("update-demo-download").classList.toggle("hidden", !s.available || s.phase === "ready");
      get("update-demo-download").disabled = model.busy();
      get("update-demo-download").textContent = s.phase === "download-error" ? "重试模拟下载" : "模拟下载";
      get("update-demo-cancel").classList.toggle("hidden", !["downloading", "verifying"].includes(s.phase));
      get("update-demo-install").classList.toggle("hidden", s.phase !== "ready");
      get("update-demo-rollback").disabled = !s.backup || model.busy();
      get("update-demo-scenario").disabled = model.busy() || s.phase === "ready";
      get("update-demo-reset").disabled = s.phase === "installing";
    }
    function init() {
      const query = new URLSearchParams(location.search);
      if (!query.has("updateDemo") || query.has("preview") || !get("update-demo")) return;
      get('update-mode-tag').textContent='模拟预览';
      get('update-mode-notice').textContent='仅展示更新流程，版本号和进度均为模拟；不会下载、替换文件或重启。';
      get('update-demo-scenarios').classList.remove('hidden');
      model = new UpdatePreviewModel(render);
      get("update-demo-scenario").onchange = e => { model.scenario = e.target.value; model.reset(); };
      get("update-demo-check").onclick = () => model.check();
      get("update-demo-download").onclick = () => model.download();
      get("update-demo-cancel").onclick = () => model.cancel();
      get("update-demo-reset").onclick = () => model.reset();
      get("update-demo-install").onclick = async () => {
        if (model.state.phase !== "ready") return;
        if (await ConfirmDialog.ask({title: "模拟重启更新", confirmText: "演示更新",
          message: "这里只预览更新确认流程，不会退出或重启程序，不会替换 EXE。\n真实更新尚未接入 GitHub Release。"})) model.install();
      };
      get("update-demo-rollback").onclick = async () => {
        if (!model.state.backup || model.busy()) return;
        if (await ConfirmDialog.ask({title: "模拟回退上一版", confirmText: "演示回退",
          message: "仅恢复本次演示的版本数字，不读取备份、不替换文件，也不会更改配置、黑名单和主题。"})) model.rollback();
      };
      model.emit({}); model.start();
      window.addEventListener("pagehide", () => model.stop(), {once:true});
    }
    return {init, get model() { return model; }};
  })();
  document.addEventListener("DOMContentLoaded", () => window.UpdatePreview.init());
}
