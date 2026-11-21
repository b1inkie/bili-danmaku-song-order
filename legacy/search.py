# -*- coding: utf-8 -*-
"""
多源搜索 - 酷狗 → 网易云 → QQ音乐，前一源有结果即停。
返回 (song_info|None, 来源标签)。
"""
from typing import Optional, Tuple

from legacy import kg_search, wy_search, tx_search

# 搜索优先级: 酷狗 > 网易云 > QQ音乐
SEARCH_SOURCES = (
    (kg_search, "酷狗"),
    (wy_search, "网易云"),
    (tx_search, "QQ音乐"),
)


async def search_first(name: str, singer: str = "") -> Tuple[Optional[dict], str]:
    """
    依次尝试各音源搜索，返回第一首的标准化 song_info 和来源标签。
    全部失败返回 (None, "")。
    """
    for module, label in SEARCH_SOURCES:
        try:
            song_info = await module.search_and_get_first(name, singer)
        except Exception as e:
            print(f"[搜索] {label}搜索异常: {e}")
            song_info = None
        if song_info:
            return song_info, label
    return None, ""
