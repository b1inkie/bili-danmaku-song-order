# -*- coding: utf-8 -*-
"""
应用目录工具 - 统一获取配置文件路径
打包后: exe 所在目录
开发时: 项目根目录（即 main.py 所在目录）
"""
import os
import sys
import threading

_blacklist_path_lock = threading.RLock()
DEFAULT_SONG_BLACKLIST = ("义勇军进行曲", "威风堂堂")


def get_app_dir() -> str:
    """获取应用目录（配置文件、黑名单等用户文件存放位置）"""
    if getattr(sys, 'frozen', False):
        # PyInstaller 打包后，exe 所在目录
        return os.path.dirname(sys.executable)
    else:
        # 开发环境，main.py 所在目录
        return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def get_config_path() -> str:
    """获取 config.json 完整路径"""
    return os.path.join(get_app_dir(), "config.json")


def get_blacklist_path() -> str:
    """英文文件名；旧版黑名单在首次使用时原地迁移，不覆盖已有新版。"""
    directory = get_app_dir()
    target = os.path.join(directory, "song_blacklist.txt")
    legacy = os.path.join(directory, ".A歌曲黑名单.txt")
    with _blacklist_path_lock:
        if not os.path.exists(target) and os.path.isfile(legacy):
            # Windows rename refuses an existing destination, protecting concurrent
            # startup. Propagate permission errors rather than silently losing data.
            try:
                os.rename(legacy, target)
            except FileExistsError:
                pass
        # Exclusive creation only: migrated/existing/explicitly emptied files stay intact.
        try:
            with open(target, "x", encoding="utf-8") as file:
                file.write("\n".join(DEFAULT_SONG_BLACKLIST) + "\n")
        except FileExistsError:
            pass
    return target


def get_web_dir() -> str:
    """获取 GUI 前端资源目录（打包时随 exe 携带）"""
    if getattr(sys, 'frozen', False):
        # onefile 模式解压在 _MEIPASS；onedir 模式与 exe 同级
        meipass = getattr(sys, '_MEIPASS', None)
        if meipass and os.path.isdir(os.path.join(meipass, 'web')):
            return os.path.join(meipass, 'web')
        return os.path.join(get_app_dir(), 'web')
    else:
        return os.path.join(get_app_dir(), 'web')
