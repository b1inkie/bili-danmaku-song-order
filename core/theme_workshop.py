"""Workshop bridge: file dialogs belong to the editor window, never accept JS file paths."""
import copy
import json
import threading
from pathlib import Path
import webview


class WorkshopApi:
    def __init__(self, manager):
        self._manager = manager
        self._window = None
        from core.theme_catalog import ThemeCatalog
        self._online = ThemeCatalog(manager)

    def online_theme_state(self):
        return self._online.snapshot()

    def refresh_online_themes(self):
        return self._online.refresh()

    def install_online_theme(self, theme_id, version):
        return self._online.install(theme_id, version)

    def bootstrap(self):
        return {"schema": self._manager.schema, "themes": self._manager.catalog(),
                "storage": str(self._manager.root), "fonts": self._installed_fonts()}

    def open_theme_directory(self):
        import os
        directory = self._manager.root / "installed"
        directory.mkdir(parents=True, exist_ok=True)
        os.startfile(str(directory))  # fixed local directory, never a frontend-supplied path
        return str(directory)

    def delete_theme(self, theme_id):
        return self._manager.delete(theme_id)

    def window_action(self, action):
        if self._window is None:
            return
        if action == "minimize":
            self._window.minimize()
        elif action == "maximize":
            from main_gui import window_maximized
            if window_maximized(self._window):
                self._window.restore()
            else:
                self._window.maximize()
        elif action == "close":
            self._window.destroy()
        else:
            raise ValueError("不支持的窗口操作")

    def window_geometry(self):
        from main_gui import _get_window_size, window_hwnd
        w, h = _get_window_size(window_hwnd(self._window))
        return {"w": w, "h": h}

    def resize_window(self, width, height, edge):
        from main_gui import FIX_MAP
        from webview.window import FixPoint
        if edge not in FIX_MAP:
            raise ValueError("无效缩放方向")
        width, height = int(width), int(height)
        if not 980 <= width <= 6000 or not 680 <= height <= 6000:
            raise ValueError("窗口尺寸超出范围")
        parts = FIX_MAP[edge].split("|")
        fix = getattr(FixPoint, parts[0])
        for part in parts[1:]:
            fix |= getattr(FixPoint, part)
        self._window.resize(width, height, fix)

    def _installed_fonts(self):
        """Enumerate on the WinForms UI thread; font files are never read/exported."""
        if hasattr(self, "_font_names"):
            return self._font_names
        names = []
        def collect():
            from System.Drawing.Text import InstalledFontCollection
            collection = InstalledFontCollection()
            try:
                names.extend(str(family.Name) for family in collection.Families)
            finally:
                collection.Dispose()
        try:
            form = self._window.native if self._window else None
            if form is not None and form.InvokeRequired:
                from System import Action
                form.Invoke(Action(collect))
            else:
                collect()
            self._font_names = sorted(set(name for name in names if name and len(name) <= 100
                                          and not any(ord(c) < 32 or ord(c) == 127 for c in name)), key=str.casefold)
        except Exception:
            return []  # keep default/custom saved font even if enumeration fails
        return self._font_names

    def _guide_text(self):
        """Self-contained AI instructions; no repository access or source tree required."""
        example = json.loads((self._manager.web / "themes/rose-nocturne.json").read_text("utf-8"))
        example.update(id="my-music-room", name="我的点歌室", author="", description="", version="1.0.0")
        example["text"] = {
            "name": "你的名字", "signature": "Your Name", "heading": "今夜，听你想听。",
            "subtitle": "把喜欢的旋律，留在这里。", "eyebrow": "MY MUSIC ROOM",
            "motto": "MUSIC FOR TONIGHT.", "vertical": "MUSIC · TONIGHT · YOU",
            "sceneNumber": "01", "sceneTitle": "MY MUSIC ROOM", "sectionNumber": "01"
        }
        example["character"]["image"] = "assets/character.png"
        prompt = (self._manager.web / "themes/ai-prompt.md").read_text("utf-8")
        return prompt.replace("{{THEME_JSON}}", "```json\n" + json.dumps(example, ensure_ascii=False, indent=2) + "\n```")

    def _copy_text(self, text):
        # WinForms clipboard requires STA; pywebview bridge methods run on worker threads.
        from System import Action
        from System.Windows.Forms import Clipboard
        form = self._window.native
        if form.InvokeRequired:
            form.Invoke(Action(lambda: Clipboard.SetText(text)))
        else:
            Clipboard.SetText(text)

    def copy_theme_guide(self):
        text = self._guide_text()
        self._copy_text(text)
        return {"copied": True, "characters": len(text)}
    def new_theme(self):
        return self._manager.new()

    def load_theme(self, theme_id):
        return self._manager.payload(self._manager.load(theme_id))

    def save_theme(self, config):
        return self._manager.save(config)

    def validate_theme(self, config):
        config = self._manager.validate(config)
        return self._manager.payload(config)

    def apply_theme(self, theme_id):
        return self._manager.select(theme_id)

    def choose_image(self):
        paths = self._window.create_file_dialog(webview.OPEN_DIALOG, allow_multiple=False,
                                                file_types=("图片 (*.png;*.jpg;*.jpeg;*.webp)",))
        if not paths:
            return None
        path = Path(paths[0])
        from core.theme_manager import MAX_FILE
        if path.stat().st_size > MAX_FILE:
            raise ValueError("单张图片不能超过12MB")
        reference = self._manager.optimize_image(path.read_bytes())
        config = self._manager.validate({"schemaVersion": 1, "id": "image-preview", "name": "preview", "template": "rose-nocturne"})
        config["character"]["image"] = reference
        return {"path": reference, "url": self._manager.payload(config)["assets"][reference]}

    def import_theme(self):
        paths = self._window.create_file_dialog(webview.OPEN_DIALOG, allow_multiple=False,
                                                file_types=("点歌台主题 (*.songtheme;*.zip)",))
        if not paths:
            return None
        return self._manager.import_pack(paths[0])

    def export_theme(self, theme_id):
        path = self._window.create_file_dialog(webview.SAVE_DIALOG, save_filename=theme_id + ".songtheme",
                                               file_types=("点歌台主题 (*.songtheme)",))
        if not path:
            return False
        return self._manager.export_pack(theme_id, path if isinstance(path, str) else path[0])


class ThemeWorkshop:
    def __init__(self, manager):
        self.manager = manager
        self.window = None
        self.lock = threading.Lock()
        self.stopping = False

    def open(self):
        from core.app_dir import get_web_dir
        with self.lock:
            if self.stopping:
                return False
            if self.window is None:
                api = WorkshopApi(self.manager)
                window = webview.create_window("主题工坊 · 玫瑰夜曲模板", str(Path(get_web_dir()) / "workshop.html"),
                                               js_api=api, width=1280, height=850, min_size=(980, 680),
                                               background_color="#151219", frameless=True,
                                               easy_drag=False, shadow=False)
                api._window = self.window = window
                def shape():
                    from main_gui import apply_round_region, window_maximized
                    if self.window is not window:
                        return
                    maximized = window_maximized(window)
                    apply_round_region(window, maximized=maximized)
                    if window.events.loaded.is_set():
                        window.evaluate_js("document.documentElement.dataset.maximized=" +
                                           json.dumps(str(maximized).lower()))
                window.events.shown += shape
                window.events.loaded += shape
                window.events.resized += lambda width, height: shape()
                def closed():
                    api._online.close()
                    if self.window is window:
                        self.window = None
                window.events.closed += closed
            else:
                self.window.show()
                self.window.restore()
        return True

    def shutdown(self):
        self.stopping = True
        if self.window is not None:
            self.window.destroy()
            self.window = None
