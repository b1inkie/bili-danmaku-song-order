"""Validated data-only theme packs. No theme HTML/CSS/JS is executed."""
import base64
import copy
import hashlib
import io
import json
import os
from pathlib import Path, PurePosixPath
import re
import threading
import tempfile
import weakref
import shutil
import uuid
import zipfile

from PIL import Image, ImageOps
from jsonschema import Draft202012Validator
from core.app_dir import get_web_dir

MAX_FILE = 12 * 1024 * 1024
MAX_TOTAL = 40 * 1024 * 1024
MAX_PIXELS = 16_000_000
BUILTINS = ("dark", "light")
HARUKA_PRESET = "preset-haruka"
RESERVED_IDS = (*BUILTINS, "haruka")
IMAGE_PATH = re.compile(r"assets/[A-Za-z0-9_-]+\.(?:png|jpg|jpeg|webp)\Z")


def read_json(data):
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise ValueError(f"JSON字段重复：{key}")
            result[key] = value
        return result
    return json.loads(data, object_pairs_hook=pairs,
                      parse_constant=lambda x: (_ for _ in ()).throw(ValueError("不允许非有限数字")))


def _atomic(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + "." + uuid.uuid4().hex + ".tmp")
    try:
        tmp.write_bytes(data)
        os.replace(tmp, path)
    finally:
        tmp.unlink(missing_ok=True)


class ThemeManager:
    def __init__(self, root=None, install_presets=None):
        self.root = Path(root) if root else Path(os.environ.get("LOCALAPPDATA", Path.home())) / "BiliSongdesk" / "themes"
        self.web = Path(get_web_dir())
        self.schema = read_json((self.web / "theme.schema.json").read_text("utf-8"))
        self.validator = Draft202012Validator(self.schema)
        self.lock = threading.RLock()
        self.revision = uuid.uuid4().hex
        self.active = "dark"
        self._applied_config = None
        # Unsaved picker images belong to this editor session, not a shared installed cache.
        self._draft_root = Path(tempfile.mkdtemp(prefix="songdesk-theme-draft-"))
        self._draft_cleanup = weakref.finalize(self, shutil.rmtree, self._draft_root, True)
        try:
            stored = read_json((self.root / "storage-v2.json").read_text("utf-8"))
            self._local_themes = set(stored["themes"])
        except (OSError, ValueError, KeyError, TypeError):
            self._local_themes = set()
        self._migrate_legacy_assets()
        if install_presets is None:
            install_presets = root is None  # offline tools/tests must not install user presets
        if install_presets:
            self._install_presets_once()
        try:
            selection = read_json((self.root / "selection.json").read_text("utf-8"))
            active = selection["active"]
            if active == "haruka":
                # Preserve an already installed legacy copy, but never seed Haruka.
                if (self.root / "installed" / HARUKA_PRESET / "theme.json").is_file():
                    self.select(HARUKA_PRESET)
                else:
                    self.select("dark")
                return
            if active not in BUILTINS:
                installed = self.load(active)
                selected = self.validate(selection.get("config", installed))
                if selected["id"] != active:
                    raise ValueError("选择配置ID不一致")
                for reference in self.image_refs(selected): self._asset(reference, active)
                self._applied_config = selected
            self.active = active
        except (OSError, ValueError, KeyError, TypeError):
            pass

    def _install_presets_once(self):
        """Install each bundled preset once, preserving edits and deletions across updates."""
        marker = self.root / "presets-v1.json"
        installed = set()
        if marker.exists():
            data = read_json(marker.read_text("utf-8"))
            installed = set(data["installed"])
        manifest = read_json((self.web / "themes/presets.json").read_text("utf-8"))
        for theme_id in manifest["themes"]:
            self._id(theme_id)
            if theme_id in installed:
                continue
            destination = self._directory(theme_id) / "theme.json"
            if not destination.exists():
                source = self.web / "themes" / theme_id
                config = self.validate(read_json((source / "theme.json").read_text("utf-8")))
                if config["id"] != theme_id:
                    raise ValueError("预设主题ID与目录不一致")
                for key in ("character", "background"):
                    reference = config[key]["image"]
                    if reference:
                        config[key]["image"] = self.optimize_image((source / reference).read_bytes())
                self.save(config)
            installed.add(theme_id)
            _atomic(marker, json.dumps({"installed": sorted(installed)}).encode("utf-8"))

    def _directory(self, theme_id):
        installed = self.root / "installed"
        directory = installed / self._id(theme_id)
        if (installed.is_symlink() or directory.is_symlink()
                or not directory.resolve().is_relative_to(self.root.resolve())
                or directory.resolve().parent != installed.resolve()):
            raise ValueError("主题目录不安全")
        return directory

    def _mark_local(self, theme_id):
        self._local_themes.add(theme_id)
        _atomic(self.root / "storage-v2.json", json.dumps({"themes": sorted(self._local_themes)}).encode("utf-8"))

    def _migrate_legacy_assets(self):
        """Copy old shared assets into EACH owner directory; never delete legacy backups.

        Include the applied snapshot, which can reference older images than the saved draft.
        No runtime reads fall back to the legacy shared directory after this migration.
        """
        selected = None
        try:
            selected = read_json((self.root / "selection.json").read_text("utf-8")).get("config")
        except (OSError, ValueError, TypeError, AttributeError):
            pass
        for path in sorted((self.root / "installed").glob("*/theme.json")):
            try:
                directory = self._directory(path.parent.name)
                if directory.name in self._local_themes:
                    continue
                if path.is_symlink() or path.stat().st_size > 128 * 1024:
                    continue
                config = self.validate(read_json(path.read_text("utf-8")))
                if config["id"] != directory.name:
                    continue
                refs = set(self.image_refs(config))
                if isinstance(selected, dict) and selected.get("id") == config["id"]:
                    refs.update(self.image_refs(self.validate(selected)))
                for reference in refs:
                    target = directory / reference
                    if target.exists():
                        self._asset(reference, config["id"])
                        continue
                    old = self.root / reference
                    if (old.is_symlink() or old.parent.is_symlink() or not old.is_file()
                            or not old.resolve().is_relative_to(self.root.resolve()) or old.stat().st_size > MAX_FILE):
                        raise ValueError("旧主题素材缺失，保留原目录等待恢复")
                    if target.parent.is_symlink():
                        raise ValueError("主题素材目录不安全")
                    _atomic(target, old.read_bytes())
                self._mark_local(directory.name)
            except (OSError, ValueError, TypeError, KeyError):
                # Keep damaged themes intact for recovery; active selection falls back safely.
                continue

    def validate(self, config):
        try:
            encoded = json.dumps(config, ensure_ascii=False, allow_nan=False).encode("utf-8")
        except (ValueError, TypeError, RecursionError) as exc:
            raise ValueError("主题必须是有限数字组成的JSON对象") from exc
        if len(encoded) > 128 * 1024:
            raise ValueError("主题配置不能超过128KB")
        errors = sorted(self.validator.iter_errors(config), key=lambda e: str(list(e.path)))
        if errors:
            error = errors[0]
            raise ValueError("主题配置错误 · " + ".".join(map(str, error.path)) + ": " + error.message[:180])
        result = copy.deepcopy(config)
        def fill(value, schema):
            for key, spec in schema.get("properties", {}).items():
                if key not in value and "default" in spec:
                    value[key] = copy.deepcopy(spec["default"])
                if key in value and spec.get("type") == "object":
                    fill(value[key], spec)
        fill(result, self.schema)
        if not result["name"].strip():
            raise ValueError("主题名称不能为空")
        return result

    def _id(self, value):
        if not isinstance(value, str) or not re.fullmatch(r"[a-z][a-z0-9-]{2,47}", value) or value in RESERVED_IDS:
            raise ValueError("无效或保留的主题ID")
        return value

    def _asset(self, relative, theme_id=None, allow_draft=False):
        if not IMAGE_PATH.fullmatch(relative):
            raise ValueError("无效素材路径")
        base = self._draft_root if theme_id is None else self._directory(theme_id)
        path = base / relative
        if allow_draft and not path.exists() and theme_id is not None:
            return self._asset(relative)
        if (path.is_symlink() or path.parent.is_symlink() or not path.is_file()
                or not path.resolve().is_relative_to(base.resolve()) or path.stat().st_size > MAX_FILE):
            raise ValueError("素材不存在或不安全：" + relative)
        return path

    @staticmethod
    def image_refs(config):
        return [config[k]["image"] for k in ("character", "background") if config[k]["image"]]

    def optimize_image(self, data):
        """Accept PNG/JPEG/WebP; decode pixels and strip metadata; preserve alpha."""
        if len(data) > MAX_FILE:
            raise ValueError("单张图片不能超过12MB")
        try:
            with Image.open(io.BytesIO(data)) as source:
                if source.format not in ("PNG", "JPEG", "WEBP") or getattr(source, "n_frames", 1) != 1:
                    raise ValueError("只支持静态PNG/JPEG/WebP")
                if source.width * source.height > MAX_PIXELS:
                    raise ValueError("图片不能超过1600万像素")
                source.load()
                image = ImageOps.exif_transpose(source).convert("RGBA")
                image.thumbnail((2400, 2400), Image.Resampling.LANCZOS)
                output = io.BytesIO()
                image.save(output, format="WEBP", quality=94, method=4)
                clean = output.getvalue()
        except (OSError, Image.DecompressionBombError) as exc:
            raise ValueError("图片损坏或尺寸过大") from exc
        relative = "assets/" + hashlib.sha256(clean).hexdigest()[:32] + ".webp"
        with self.lock:
            _atomic(self._draft_root / relative, clean)
        return relative

    def new(self):
        config = read_json((self.web / "themes/rose-nocturne.json").read_text("utf-8"))
        config["id"] = "theme-" + uuid.uuid4().hex[:12]
        config["character"]["image"] = ""  # Template contains no bundled creator OC.
        return self.payload(self.validate(config))

    def load(self, theme_id):
        path = self._directory(theme_id) / "theme.json"
        if not path.resolve().is_relative_to(self.root.resolve()) or path.is_symlink() or path.stat().st_size > 128 * 1024:
            raise ValueError("主题文件异常")
        config = self.validate(read_json(path.read_text("utf-8")))
        if config["id"] != theme_id:
            raise ValueError("主题ID与目录不一致")
        for reference in self.image_refs(config):
            self._asset(reference, theme_id)
        return config

    def payload(self, config):
        assets = {}
        config = copy.deepcopy(config)
        for key in ("character", "background"):
            reference = config[key]["image"]
            if not reference:
                continue
            path = self._asset(reference, config["id"], allow_draft=True)
            data = path.read_bytes()
            # Content-address draft filenames so two independent themes may both
            # use assets/character.png without overwriting each other's editor copy.
            staged_ref = "assets/" + hashlib.sha256(data).hexdigest()[:32] + path.suffix
            _atomic(self._draft_root / staged_ref, data)
            config[key]["image"] = staged_ref
            mime = {".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".webp": "image/webp"}[path.suffix]
            assets[staged_ref] = "data:" + mime + ";base64," + base64.b64encode(data).decode("ascii")
        return {"config": config, "assets": assets}

    def save(self, config):
        with self.lock:
            config = self.validate(config)
            directory = self._directory(config["id"])
            sources = {ref: self._asset(ref, config["id"], allow_draft=True).read_bytes()
                       for ref in set(self.image_refs(config))}
            if (directory / "assets").is_symlink():
                raise ValueError("主题素材目录不安全")
            for reference, data in sources.items():
                target = directory / reference
                if target.is_symlink():
                    raise ValueError("主题素材路径不安全")
                _atomic(target, data)
            _atomic(directory / "theme.json",
                    (json.dumps(config, ensure_ascii=False, indent=2) + "\n").encode("utf-8"))
            self._mark_local(config["id"])
            return self.payload(config)

    def catalog(self):
        items = []
        for path in sorted((self.root / "installed").glob("*/theme.json")):
            try:
                c = self.load(path.parent.name)
                items.append({k: c[k] for k in ("id", "name", "author", "version")})
            except (ValueError, OSError, TypeError, KeyError):
                continue
        return items

    def delete(self, theme_id):
        """Remove the theme's own images only; never touch another theme or unrelated files."""
        with self.lock:
            directory = self._directory(theme_id)
            path = directory / "theme.json"
            installed = self.root / "installed"
            if (directory.is_symlink() or path.is_symlink()
                    or directory.resolve().parent != installed.resolve()
                    or not path.resolve().is_relative_to(self.root.resolve())):
                raise ValueError("主题路径不安全，无法删除")
            if not path.is_file():
                raise ValueError("主题不存在或已删除")
            if self.active == theme_id:
                self.select("dark")
            path.unlink()
            assets = directory / "assets"
            if assets.is_dir() and not assets.is_symlink():
                for image in assets.iterdir():
                    relative = "assets/" + image.name
                    if IMAGE_PATH.fullmatch(relative) and image.is_file() and not image.is_symlink():
                        image.unlink()
                try:
                    assets.rmdir()
                except OSError:
                    pass
            try:
                directory.rmdir()  # Only remove an empty directory, never unrelated files.
            except OSError:
                pass
            return {"deleted": theme_id, **self.state()}
    def select(self, theme_id):
        with self.lock:
            if theme_id == "haruka":
                theme_id = HARUKA_PRESET  # legacy callers; never recreate a deleted preset
            config = self.load(theme_id) if theme_id not in BUILTINS else None
            _atomic(self.root / "selection.json", json.dumps({"active": theme_id, "config": config}, ensure_ascii=False).encode("utf-8"))
            self._applied_config = config
            self.active = theme_id
            self.revision = uuid.uuid4().hex
            return self.state()

    def state(self, since=None, capture=False):
        with self.lock:
            result = {"id": self.active, "revision": self.revision}
            if since == self.revision:
                return result
            if self.active not in BUILTINS:
                try:
                    self.load(self.active)  # still detect deleted/corrupt installations
                    config = self._applied_config
                    result["payload"] = {"config": config, "assets": {}} if capture else self.payload(config)
                except (OSError, ValueError, KeyError, TypeError):
                    self.active = "dark"
                    self.revision = uuid.uuid4().hex
                    result = {"id": "dark", "revision": self.revision, "warning": "自定义主题损坏，已回退经典深色"}
            return result

    def import_pack(self, filename):
        """Validate the complete archive before importing. Never extract arbitrary paths."""
        if Path(filename).stat().st_size > MAX_TOTAL:
            raise ValueError("主题包本身不能超过40MB")
        with zipfile.ZipFile(filename) as archive:
            files = archive.infolist()
            if len(files) > 64 or sum(i.file_size for i in files) > MAX_TOTAL:
                raise ValueError("主题包最多64项、解压总量不超过40MB")
            names = set()
            for info in files:
                name = info.orig_filename
                if name != info.filename:
                    raise ValueError("主题包路径包含非法字符")
                p = PurePosixPath(name)
                if name in names or "\\" in name or ":" in name or p.is_absolute() or ".." in p.parts or info.flag_bits & 1:
                    raise ValueError("主题包包含不安全或重复路径")
                names.add(name)
                if (info.external_attr >> 16) & 0o170000 == 0o120000:
                    raise ValueError("主题包不能包含符号链接")
                if info.is_dir():
                    if name != "assets/": raise ValueError("只允许assets目录")
                    continue
                if name != "theme.json" and name != "preview.png" and not IMAGE_PATH.fullmatch(name):
                    raise ValueError("主题包只允许theme.json及本地图片：" + name)
                if info.file_size > MAX_FILE or (name == "theme.json" and info.file_size > 128 * 1024):
                    raise ValueError("主题包文件过大")
            config = self.validate(read_json(archive.read("theme.json").decode("utf-8-sig")))
            # Preserve ID for a new import, create a copy instead of overwriting existing themes.
            self._id(config["id"])
            if (self.root / "installed" / config["id"]).exists():
                config["id"] = "theme-" + uuid.uuid4().hex[:12]
                config["name"] = config["name"][:35] + " · 副本"
            images = {}
            for reference in self.image_refs(config):
                if reference not in names:
                    raise ValueError("主题包缺少素材：" + reference)
                images[reference] = archive.read(reference)
            for key in ("character", "background"):
                reference = config[key]["image"]
                if reference:
                    config[key]["image"] = self.optimize_image(images[reference])
            return self.save(config)

    def export_pack(self, theme_id, filename):
        config = self.load(theme_id)
        target = Path(filename)
        tmp = target.with_name(target.name + "." + uuid.uuid4().hex + ".tmp")
        try:
            with zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED) as archive:
                archive.writestr("theme.json", json.dumps(config, ensure_ascii=False, indent=2))
                for reference in sorted(set(self.image_refs(config))):
                    archive.write(self._asset(reference, theme_id), reference)
            os.replace(tmp, target)
        finally:
            tmp.unlink(missing_ok=True)
        return True
