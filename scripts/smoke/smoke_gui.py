# -*- coding: utf-8 -*-
"""GUI 冒烟测试：启动引擎+窗口，8秒后自动关闭，打印期间收集到的引擎事件"""
import os
import sys
import threading

from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from _bootstrap import setup
PROJECT_ROOT, OUTPUT_DIR = setup()

import webview

from core.engine import Engine
import main_gui

AUTO_CLOSE_SEC = 8

engine = Engine()
api = main_gui.Api(engine)
engine.start()

collected = []


def tap_poll():
    """定时把事件取出来留档"""
    import time
    while True:
        for e in api.poll_events():
            keep = {k: (v[:40] + "..." if isinstance(v, str) and len(v) > 40 else v) for k, v in e.items()}
            collected.append(keep)
        time.sleep(0.3)


threading.Thread(target=tap_poll, daemon=True).start()

index_path = os.path.join(main_gui.get_web_dir(), "index.html")
window = webview.create_window(
    "B站点歌台 [SMOKE TEST]",
    url=index_path,
    js_api=api,
    width=1180, height=780,
    min_size=(920, 600),
    frameless=True,
    background_color="#0a0a0b",
    shadow=False,
    easy_drag=False,
)


def autoclose():
    import time
    time.sleep(AUTO_CLOSE_SEC)
    print("\n===== 引擎事件（冒烟期间） =====", flush=True)
    for e in collected:
        print(" *", e, flush=True)
    print(f"===== 共 {len(collected)} 条 =====", flush=True)
    engine.shutdown()
    window.destroy()


window.events.closing += engine.shutdown
threading.Thread(target=autoclose, daemon=True).start()

print("[SMOKE] 启动窗口，{}秒后自动关闭...".format(AUTO_CLOSE_SEC), flush=True)
webview.start()
print("[SMOKE] 窗口已关闭，测试结束", flush=True)
