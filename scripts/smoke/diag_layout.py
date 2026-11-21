# -*- coding: utf-8 -*-
"""布局诊断：不依赖截图，检查 CSS 是否完整加载、关键元素几何是否正常、窗口区域是否裁剪错位。"""
import json
import os
import sys
import threading
import time

from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from _bootstrap import setup
PROJECT_ROOT, OUTPUT_DIR = setup()

import webview

import main_gui

PROBE = r"""
(() => {
  const r = {};
  // 1) CSS 是否完整加载（规则数量；样式崩坏时这个值会异常小）
  try {
    let n = 0;
    for (const ss of document.styleSheets) n += ss.cssRules.length;
    r.css_rules = n;
  } catch (e) { r.css_rules = "ERR " + e.message; }

  // 2) 关键元素几何
  const rect = (sel) => {
    const el = document.querySelector(sel);
    if (!el) return null;
    const b = el.getBoundingClientRect();
    return { x: Math.round(b.x), y: Math.round(b.y), w: Math.round(b.width), h: Math.round(b.height) };
  };
  for (const sel of ["#app", ".windowbar", ".drag-area", ".ticker", ".panels", ".queue-panel", ".dm-panel", ".actionbar", ".login-view", ".login-card"]) {
    r["geo_" + sel.replace(/[.#]/g, "")] = rect(sel);
  }

  // 3) 视口与文档
  r.viewport = { iw: window.innerWidth, ih: window.innerHeight, dw: document.documentElement.clientWidth, dh: document.documentElement.clientHeight };
  r.scroll = { x: window.scrollX, y: window.scrollY };

  // 4) #app 关键计算样式
  const cs = getComputedStyle(document.getElementById("app"));
  r.app_style = { display: cs.display, height: cs.height, radius: cs.borderRadius, bg: cs.backgroundColor.slice(0, 40) };

  // 5) 主题与最大化标记
  r.theme = document.documentElement.dataset.theme;
  r.maximized = document.documentElement.dataset.maximized;

  // 6) overflow 元素检测（谁把页面撑乱了）
  const bad = [];
  document.querySelectorAll("*").forEach((el) => {
    const b = el.getBoundingClientRect();
    if (b.width > 0 && (b.right > window.innerWidth + 8 || b.bottom > window.innerHeight + 8) && !el.classList.contains("rh")) {
      if (bad.length < 8) bad.push(el.tagName + "." + (el.className || "").toString().split(" ")[0] + " r=" + Math.round(b.right) + " b=" + Math.round(b.bottom));
    }
  });
  r.overflow_els = bad;

  // 7) 缩放手柄数量与位置
  r.handles = document.querySelectorAll(".rh").length;
  r.handle_n = rect(".rh-n");

  return JSON.stringify(r);
})()
"""

OUT = {}


def main():
    window = webview.create_window(
        "LAYOUT DIAG",
        url=os.path.join(main_gui.get_web_dir(), "index.html"),
        width=1180, height=780, min_size=(920, 600),
        frameless=True, background_color="#0a0a0b", shadow=False, easy_drag=False,
    )
    window.events.shown += lambda: main_gui.apply_round_region(window)
    window.events.resized += lambda w, h: main_gui.apply_round_region(window)

    def worker():
        time.sleep(3.2)
        try:
            raw = window.evaluate_js(PROBE)
            OUT["data"] = json.loads(raw) if isinstance(raw, str) else raw
        except Exception as e:
            OUT["error"] = str(e)
        window.destroy()

    threading.Thread(target=worker, daemon=True).start()
    webview.start()
    print(json.dumps(OUT.get("data") or OUT, ensure_ascii=False, indent=1)[:4000], flush=True)


if __name__ == "__main__":
    main()
