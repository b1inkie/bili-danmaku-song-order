# -*- coding: utf-8 -*-
"""桥接冒烟：检查 pywebview 注入桥、前端初始化是否成功，5秒后自动关闭"""
import os
import sys
import threading
import time

from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from _bootstrap import setup
PROJECT_ROOT, OUTPUT_DIR = setup()

import webview

from core.engine import Engine
import main_gui

engine = Engine()
api = main_gui.Api(engine)
engine.start()

index_path = os.path.join(main_gui.get_web_dir(), "index.html")
window = webview.create_window(
    "B站点歌台 [BRIDGE TEST]",
    url=index_path,
    js_api=api,
    width=1180, height=780,
    min_size=(920, 600),
    background_color="#0a0a0b",
)

CHECK_JS = """
(() => {
  const r = {};
  r.pywebview = typeof window.pywebview;
  r.api = window.pywebview ? typeof window.pywebview.api : "none";
  r.get_state = (window.pywebview && window.pywebview.api) ? typeof window.pywebview.api.get_state : "none";
  r.readyState = document.readyState;
  r.connInit = document.getElementById("conn") ? document.getElementById("conn").dataset.state : "missing";
  r.jsErrors = window.__errs ? window.__errs.join(" | ") : "";
  r.theme = document.documentElement.dataset.theme;
  return JSON.stringify(r);
})()
"""

ERR_HOOK_JS = """
window.__errs = [];
window.onerror = function(msg, src, line) { window.__errs.push(msg + " @" + line); };
"""

results = {}


def checker():
    # 等 pywebviewready + DOM init
    time.sleep(3.0)
    try:
        window.evaluate_js(ERR_HOOK_JS)
        results["check"] = window.evaluate_js(CHECK_JS)
    except Exception as e:
        results["check"] = f"evaluate failed: {e}"
    try:
        window.evaluate_js("window.__state='pending'; window.pywebview.api.get_state().then(r => { window.__state = JSON.stringify(r); }).catch(e => { window.__state = 'ERR ' + e; })")
        time.sleep(1.2)
        results["state"] = str(window.evaluate_js("window.__state"))
    except Exception as e:
        results["state"] = f"state call failed: {e}"
    time.sleep(0.8)
    # 再看一眼有没有运行期错误
    results["errs2"] = window.evaluate_js("window.__errs ? window.__errs.join(' | ') : 'none'")
    print("\n===== 桥接检查 =====", flush=True)
    for k, v in results.items():
        print(f" {k}: {v}", flush=True)
    engine.shutdown()
    window.destroy()


window.events.closing += engine.shutdown
threading.Thread(target=checker, daemon=True).start()
print("[BRIDGE] 启动窗口，5秒后自动关闭...", flush=True)
webview.start()
print("[BRIDGE] 测试结束", flush=True)
