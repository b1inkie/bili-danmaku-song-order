# -*- coding: utf-8 -*-
"""
打包脚本 - 将 blive-vod 打包为 exe
用法:
  python build.py          # 打包 GUI 版（main_gui.py，无控制台窗口）
  python build.py console  # 打包控制台版（main.py）
"""
import subprocess
import sys
import os

# 项目根目录（package-exe 的上级目录）
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_ROOT)
from core.version import VERSION, APP_NAME
DIST_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "dist")
BUILD_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "build")


def install_pyinstaller():
    """确保 PyInstaller 已安装"""
    try:
        import PyInstaller
        print(f"[打包] PyInstaller 版本: {PyInstaller.__version__}")
    except ImportError:
        print("[打包] 正在安装 PyInstaller...")
        subprocess.check_call([sys.executable, "-m", "pip", "install", "pyinstaller"])
        print("[打包] PyInstaller 安装完成")


def common_hidden_imports():
    return [
        "aiohttp",
        "asyncio",
        "http.cookies",
        "blivedm",
        "blivedm.clients",
        "blivedm.clients.web",
        "blivedm.clients.ws_base",
        "blivedm.models",
        "blivedm.models.web",
        "blivedm.handlers",
        "blivedm.utils",
    ]


def prepare_icon(source, target):
    """No placeholder icon: absent PNG keeps PyInstaller default until user supplies it."""
    if not source.is_file():
        return None
    from PIL import Image, ImageOps
    with Image.open(source) as image:
        if image.format != 'PNG' or getattr(image, 'n_frames', 1) != 1:
            raise ValueError('app-icon.png must be a static PNG')
        if image.width * image.height > 16_000_000:
            raise ValueError('App icon must not exceed 16 megapixels')
        rgba = ImageOps.exif_transpose(image).convert('RGBA')
        rgba.thumbnail((256, 256), Image.Resampling.LANCZOS)
        canvas = Image.new('RGBA', (256, 256))
        canvas.alpha_composite(rgba, ((256-rgba.width)//2, (256-rgba.height)//2))
        target.parent.mkdir(parents=True, exist_ok=True)
        canvas.save(target, format='ICO', sizes=[(16,16),(24,24),(32,32),(48,48),(64,64),(128,128),(256,256)])
    return target

def build(mode: str = "gui"):
    """执行打包。mode: 'gui' 或 'console'"""
    install_pyinstaller()

    if mode == "gui":
        main_script = os.path.join(PROJECT_ROOT, "main_gui.py")
        name = APP_NAME
        console_flag = "--windowed"   # GUI 版不弹控制台
    else:
        main_script = os.path.join(PROJECT_ROOT, "main.py")
        name = "blive-vod"
        console_flag = "--console"

    from pathlib import Path
    version_file = Path(BUILD_DIR) / "version-info.txt"
    version_file.parent.mkdir(parents=True, exist_ok=True)
    numbers = tuple(map(int, VERSION.split('.'))) + (0,)
    version_file.write_text("VSVersionInfo(ffi=FixedFileInfo(filevers=" + repr(numbers) + ",prodvers=" + repr(numbers) + ",mask=0x3f,flags=0,OS=0x40004,fileType=1,subtype=0,date=(0,0)),kids=[StringFileInfo([StringTable('040904B0',[StringStruct('FileDescription','Bili Songdesk'),StringStruct('FileVersion','" + VERSION + "'),StringStruct('ProductName','Bili Songdesk'),StringStruct('ProductVersion','" + VERSION + "')])]),VarFileInfo([VarStruct('Translation',[1033,1200])])])", encoding='utf-8')
    # Optional user PNG: generate Windows multi-size ICO without requiring conversion.
    icon = prepare_icon(Path(PROJECT_ROOT) / 'web/assets/app-icon.png', Path(BUILD_DIR) / 'app-icon.ico')
    args = [
        sys.executable, "-m", "PyInstaller",
        "--noconfirm",
        "--clean",
        # 单文件模式（只生成一个 exe）
        "--onefile",
        console_flag,
        "--version-file", str(version_file),
        # 程序名
        "--name", name,
        # 输出目录
        "--distpath", DIST_DIR,
        "--workpath", BUILD_DIR,
        # 指定 spec 文件目录
        "--specpath", os.path.dirname(os.path.abspath(__file__)),
    ]
    if mode == 'gui' and icon is not None:
        args += ['--icon', str(icon)]

    # 隐式导入
    for mod in common_hidden_imports():
        args += ["--hidden-import", mod]

    if mode == "gui":
        # GUI 版额外处理
        for mod in [
            "webview", "webview.platforms.edgechromium", "webview.platforms.winforms",
            "clr", "qrcode", "qrcode.image.svg",
            "core", "core.engine", "core.settings", "core.player",
            "core.danmaku_service", "core.events", "core.playlist_runtime", "core.queue_runtime",
            "core.capture_window",
            "core.theme_manager", "core.theme_workshop", "core.theme_catalog", "PIL.Image", "PIL.WebPImagePlugin", "jsonschema",
            "core.bili_login", "core.qr_page", "core.config", "core.song_commands", "core.app_dir",
            "core.updater", "core.update_protocol", "core.version", "cryptography.hazmat.primitives.asymmetric.ed25519",
        ]:
            args += ["--hidden-import", mod]
        # 前端资源打包进 exe（运行时解压到 _MEIPASS/web）
        web_dir = os.path.join(PROJECT_ROOT, "web")
        args += ["--add-data", f"{web_dir}{os.pathsep}web"]
        theme_docs = os.path.join(PROJECT_ROOT, "docs", "themes")
        args += ["--add-data", f"{theme_docs}{os.pathsep}docs/themes"]
        helper = os.path.join(PROJECT_ROOT, "core", "update-helper.ps1")
        args += ["--add-data", f"{helper}{os.pathsep}core"]

    # 主脚本
    args.append(main_script)

    print(f"[打包] 开始打包 {mode} 版（onefile 模式）...")
    print(f"[打包] 项目目录: {PROJECT_ROOT}")
    print(f"[打包] 输出目录: {DIST_DIR}")
    subprocess.check_call(args)

    print()
    print("=" * 50)
    print(f"[完成] 打包成功！")
    print(f"[输出] {os.path.join(DIST_DIR, name + '.exe')}")
    if mode == "gui":
        print("[说明] GUI 版首次启动自动生成 config.json 和黑名单文件")
        print("[说明] 运行需要系统 WebView2 运行时（Win10/11 一般自带）与网易云音乐桌面客户端")
    print("=" * 50)


if __name__ == "__main__":
    build(sys.argv[1] if len(sys.argv) > 1 else "gui")
