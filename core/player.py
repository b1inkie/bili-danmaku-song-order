# -*- coding: utf-8 -*-
"""网易云桌面适配器。本机 CDP 通道为实验性内部接口，不读取账号 Cookie。
参考：Seraph310/cloudmusic-desktop-mcp (MIT)，见 THIRD_PARTY_NOTICES.md。
"""
import asyncio
import json
import os
import re
import subprocess
from pathlib import Path
from urllib.parse import urlparse

import aiohttp

PORT = 9223
from core.netease_runtime import RUNTIME, STATE


class Player:
    def __init__(self):
        self._lock = asyncio.Lock()
        self._track_cache = {}
        self._metadata_retry = 0
        self._requesters = {}
        self.queue_policy = lambda: {"enabled": False, "maximum": 10}

    async def queue_tick(self, enabled):
        from core.queue_runtime import INSTALL, TICK, REMOVE_ENDED
        async with self._lock:
            if not enabled:
                await self._evaluate(RUNTIME + "(()=>{const q=window.__songdesk.consumer;if(q){q.active=false;q.events=[];}return true})()")
                return
            await self._evaluate(RUNTIME + INSTALL)
            data = await self._evaluate(RUNTIME + TICK.replace("ENABLED", "true"))
            if data.get("mode") != "playOrder":
                raise RuntimeError("未能设置顺序播放，消费队列未就绪")
            for event in data.get("events", []):
                result = await self._evaluate(RUNTIME + REMOVE_ENDED.replace("INPUT", json.dumps(event), 1))
                if result == "waiting":
                    continue
                if result == "sent":
                    for _ in range(15):
                        state = await self._evaluate(RUNTIME + STATE)
                        if int(event["id"]) not in state["queue"]:
                            break
                        await asyncio.sleep(.15)
                    else:
                        raise RuntimeError("未确认已播歌曲移除")
                await self._evaluate(RUNTIME + "(()=>{const q=window.__songdesk.consumer;q.events=q.events.filter(e=>e.seq!=="
                                     + str(int(event["seq"])) + ");return true})()")

    async def _remove_previous(self, song_id):
        await self._evaluate(RUNTIME + "(async()=>{const s=window.__songdesk.store;const state=s.getStore();"
                             "const item=state.playingList.curPlayingList.find(x=>Number(x.resourceId)===" + str(int(song_id)) + ");"
                             "if(item&&Number(state.playing.curPlaying?.resourceId)!==" + str(int(song_id)) + ")await s.getDispatch()({"
                             "type:'playingList/removeItemFromCurPlayingListByIds',payload:{removeIds:[item],triggerScene:'playingList'}});return true})()")
        for _ in range(15):
            state = await self._evaluate(RUNTIME + STATE)
            if int(song_id) not in state["queue"]:
                return
            await asyncio.sleep(.15)
        raise RuntimeError("切歌已生效，但上一首未确认移除")

    def record_request(self, song_id, requester):
        """当前会话点歌人；网易云原生队列没有此字段，不猜测历史来源。"""
        self._requesters[str(song_id)] = str(requester or "手动点歌")

    async def _evaluate(self, expression):
        timeout = aiohttp.ClientTimeout(total=12)
        try:
            async with aiohttp.ClientSession(timeout=timeout, trust_env=False) as session:
                async with session.get(f"http://127.0.0.1:{PORT}/json") as response:
                    targets = await response.json()
                target = next((t for t in targets if t.get("type") == "page"
                               and t.get("url", "").startswith("orpheus://")), None)
                if not target:
                    raise RuntimeError("未找到网易云播放器页面，客户端版本可能不兼容")
                url = target.get("webSocketDebuggerUrl", "")
                parsed = urlparse(url)
                if parsed.scheme != "ws" or parsed.hostname not in ("127.0.0.1", "localhost") or parsed.port != PORT:
                    raise RuntimeError("拒绝非本机播放器控制地址")
                async with session.ws_connect(url) as ws:
                    await ws.send_json({"id": 1, "method": "Runtime.evaluate", "params": {
                        "expression": expression, "returnByValue": True, "awaitPromise": True}})
                    while True:
                        message = await asyncio.wait_for(ws.receive_json(), timeout=12)
                        if message.get("id") != 1:
                            continue
                        result = message.get("result", {})
                        if message.get("error") or result.get("exceptionDetails"):
                            detail = result.get("exceptionDetails", {})
                            description = (detail.get("exception") or {}).get("description") or detail.get("text")
                            description = description or str(message.get("error", {}).get("message", "未知错误"))
                            raise RuntimeError("网易云控制失败：" + description[:500])
                        return result.get("result", {}).get("value")
        except (aiohttp.ClientError, asyncio.TimeoutError) as exc:
            raise RuntimeError("网易云控制通道未就绪：请先退出网易云，在设置中以控制模式启动") from exc

    async def status(self):
        try:
            state = await self._evaluate(RUNTIME + STATE)
            if not isinstance(state, dict) or not isinstance(state.get("queue"), list):
                raise RuntimeError("网易云版本不兼容：未能读取待播队列")
            return {"ready": True, "message": "网易云已连接 · 待播队列可用（实验性适配）"}
        except Exception as exc:
            return {"ready": False, "message": str(exc)}

    @staticmethod
    def executable():
        configured = os.environ.get("CLOUDMUSIC_EXE")
        if configured and Path(configured).is_file():
            return configured
        try:
            import winreg
            with winreg.OpenKey(winreg.HKEY_CLASSES_ROOT, r"orpheus\shell\open\command") as key:
                command = winreg.QueryValue(key, None)
            match = re.search(r'"([^\"]+\.exe)"', command, re.I)
            if match and Path(match.group(1)).is_file():
                return match.group(1)
        except OSError:
            pass
        raise RuntimeError("未检测到网易云安装路径，可设置 CLOUDMUSIC_EXE")

    async def launch(self):
        status = await self.status()
        if status["ready"]:
            return status
        # 不杀进程、不重启用户正在听歌的客户端。
        process = await asyncio.create_subprocess_exec(
            "tasklist", "/FI", "IMAGENAME eq cloudmusic.exe", "/FO", "CSV", "/NH",
            stdout=asyncio.subprocess.PIPE, creationflags=subprocess.CREATE_NO_WINDOW)
        output, _ = await process.communicate()
        if b'cloudmusic.exe' in output.lower():
            raise RuntimeError("请手动退出正在运行的网易云，再点击启动控制模式")
        executable = self.executable()
        subprocess.Popen([executable, "--remote-debugging-address=127.0.0.1",
                          f"--remote-debugging-port={PORT}"], cwd=str(Path(executable).parent))
        return {"ready": False, "message": "已启动网易云，稍后重新打开设置检测连接"}

    async def search(self, name, singer=""):
        params = {"s": f"{name} {singer}".strip(), "type": 1, "offset": 0, "limit": 5}
        result = await self._evaluate(RUNTIME + "window.__songdesk.request('/api/cloudsearch/pc')(" + json.dumps(params) + ")")
        songs = (result or {}).get("result", {}).get("songs", [])
        if not songs:
            raise RuntimeError("网易云没有搜索到歌曲")
        song = songs[0]
        artists = song.get("artists") or song.get("ar") or []
        return {"source": "wy", "songmid": str(song["id"]), "name": song.get("name", name),
                "singer": "/".join(a.get("name", "") for a in artists)}

    async def play_search_result(self, song_info):
        song_id = int(song_info["songmid"])
        if song_id <= 0 or song_info.get("source") != "wy":
            raise ValueError("仅接受网易云歌曲 ID")
        async with self._lock:
            details = await self._evaluate(RUNTIME + "window.__songdesk.request('/api/v3/song/detail')({c:"
                                           + json.dumps(json.dumps([{"id": song_id}])) + "})")
            tracks = details.get("songs", [])
            if not tracks or int(tracks[0].get("id", 0)) != song_id:
                raise RuntimeError("未获取到歌曲详情，未加入队列")
            before = await self._evaluate(RUNTIME + STATE)
            policy = self.queue_policy()
            if policy["enabled"] and len(before["queue"]) >= policy["maximum"]:
                raise RuntimeError(f"歌单已满（上限{policy['maximum']}首，含正在播放），本次点歌未加入")
            if policy["enabled"] and song_id in before["queue"]:
                raise RuntimeError("歌曲已在歌单中，请等待播放完成")
            payload = {"trackList": tracks, "trackFrom": {
                           "text": "点歌台", "href": "", "resourceType": "track", "scene": "search",
                           "fromInfo": {"originalScene": "search", "originalResourceType": "track",
                                        "computeSourceResourceType": "track", "sourceData": {}}},
                       "options": {"clear": False, "play": not before["queue"], "playId": song_id,
                                   "offset": len(before["queue"]) - 1},
                       "triggerScene": "search", "triggerAction": "addToPlayList"}
            guard = ""
            if policy["enabled"]:
                guard = ("const q=window.__songdesk.consumer;const s=window.__songdesk.store.getStore();"
                         "if(!q?.active||Date.now()>q.lease||s.playing.playingMode!=='playOrder')throw Error('消费队列未就绪，请稍后再试');"
                         "if(s.playingList.curPlayingList.length>=" + str(policy["maximum"]) + ")throw Error('歌单已满，本次点歌未加入');")
            await self._evaluate(RUNTIME + "(async()=>{" + guard + "await window.__songdesk.store.getDispatch()({type:"
                                 "'playingList/addItemToCurPlayingList',payload:" + json.dumps(payload) + "});return true})()")
            for _ in range(12):
                after = await self._evaluate(RUNTIME + STATE)
                if song_id in after["queue"]:
                    break
                await asyncio.sleep(0.15)
            else:
                raise RuntimeError("客户端没有确认歌曲入队，可能版本不兼容")
            return song_id

    async def skip_next(self):
        async with self._lock:
            before = await self._evaluate(RUNTIME + STATE)
            if self.queue_policy()["enabled"] and len(before["queue"]) == 1 and before["current"]:
                from core.playlist_runtime import ACTION
                payload = {"songId": str(before["current"]), "command": "delete", "direction": 0}
                await self._evaluate(RUNTIME + ACTION.replace("INPUT", json.dumps(payload), 1))
                for _ in range(20):
                    after = await self._evaluate(RUNTIME + STATE)
                    if not after["queue"]:
                        return after
                    await asyncio.sleep(.15)
                raise RuntimeError("未确认最后一首已移除")
            if len(before["queue"]) < 2:
                raise RuntimeError("队列不足两首，无法确认切歌")
            await self._evaluate(RUNTIME + "(async()=>{await window.__songdesk.store.getDispatch()({"
                                 "type:'playingList/jump2Track',payload:{flag:1,type:'ui',triggerScene:'playingList'}"
                                 "});return true})()")
            for _ in range(20):
                after = await self._evaluate(RUNTIME + STATE)
                if after["current"] and after["current"] != before["current"]:
                    if self.queue_policy()["enabled"] and before["current"]:
                        await self._remove_previous(before["current"])
                    return after
                await asyncio.sleep(0.15)
            raise RuntimeError("已发送切歌动作，但客户端未确认歌曲变化")

    async def playlist(self):
        from core.playlist_runtime import SNAPSHOT
        import time
        snapshot = await self._evaluate(RUNTIME + SNAPSHOT)
        missing = [x["id"] for x in snapshot["items"] if x["id"] not in self._track_cache
                   and (not x.get("singer") or not x.get("duration"))]
        if missing and time.monotonic() >= self._metadata_retry:
            try:
                ids = [{"id": int(value)} for value in missing[:100]]
                details = await self._evaluate(RUNTIME + "window.__songdesk.request('/api/v3/song/detail')({c:"
                                               + json.dumps(json.dumps(ids)) + "})")
                for track in details.get("songs", []):
                    self._track_cache[str(track["id"])] = {
                        "singer": " / ".join(a.get("name", "") for a in (track.get("ar") or track.get("artists") or [])),
                        "duration": round((track.get("dt") or track.get("duration") or 0) / 1000)}
                self._metadata_retry = time.monotonic() + 3
            except Exception:
                # 元数据失败不妨碍控制歌单，30秒后再试。
                self._metadata_retry = time.monotonic() + 30
        for item in snapshot["items"]:
            cached = self._track_cache.get(item["id"], {})
            item["singer"] = item.get("singer") or cached.get("singer", "")
            item["duration"] = item.get("duration") or cached.get("duration", 0)
            item["requester"] = self._requesters.get(item["id"], "")
        return snapshot

    async def clear_playlist(self, expected_ids):
        """Clear only after confirmation; reject if queue changed while the dialog was open."""
        from core.playlist_runtime import ACTION
        if (not isinstance(expected_ids, list) or not expected_ids
                or any(not isinstance(value, str) or not value.isascii() or not value.isdigit()
                       or int(value) <= 0 for value in expected_ids)):
            raise ValueError("无效的待清空歌单")
        async with self._lock:
            before = await self.playlist()
            if [item["id"] for item in before["items"]] != expected_ids:
                raise RuntimeError("歌单已变化，请重新确认清空")
            expression = ACTION.replace("INPUT", json.dumps({"songId": "", "command": "clear", "direction": 0, "expectedIds": expected_ids}), 1)
            await self._evaluate(RUNTIME + expression)
            for _ in range(20):
                after = await self.playlist()
                if not after["items"]:
                    return after
                await asyncio.sleep(0.15)
            raise RuntimeError("网易云未确认清空歌单，请检查客户端")
    async def playlist_action(self, song_id, command, direction=0):
        from core.playlist_runtime import ACTION
        song_id = str(song_id)
        if not song_id.isascii() or not song_id.isdigit() or int(song_id) <= 0:
            raise ValueError("无效的网易云歌曲 ID")
        if command not in ("toggle", "move", "delete"):
            raise ValueError("不支持的歌单操作")
        if command == "move" and (type(direction) is not int or direction not in (-1, 1)):
            raise ValueError("排序方向必须为 -1 或 1")
        async with self._lock:
            before = await self.playlist()
            ids = [item["id"] for item in before["items"]]
            if song_id not in ids:
                raise RuntimeError("歌曲已不在歌单")
            index = ids.index(song_id)
            expected = ids[:]
            if command == "move":
                target = index + direction
                if not 0 <= target < len(ids):
                    raise RuntimeError("歌曲已在歌单边界")
                expected[index], expected[target] = expected[target], expected[index]
            payload = json.dumps({"songId": song_id, "command": command, "direction": direction})
            await self._evaluate(RUNTIME + ACTION.replace("INPUT", payload, 1))
            for _ in range(20):
                after = await self.playlist()
                current_ids = [item["id"] for item in after["items"]]
                if command == "delete" and song_id not in current_ids:
                    return after
                if command == "move" and current_ids == expected:
                    return after
                if command == "toggle" and after["current"] == song_id:
                    was_current = before["current"] == song_id
                    if after["playing"] == (not before["playing"] if was_current else True):
                        return after
                await asyncio.sleep(0.15)
            raise RuntimeError("网易云未确认歌单操作，请查看客户端状态后再试")
