# 打包为 EXE

将项目打包为独立可执行文件，无需安装 Python 即可运行。

## 使用方法

在项目根目录下运行：

```bash
python package-exe/build.py gui      # GUI 版（默认）
python package-exe/build.py console  # 原版控制台入口
```

GUI 输出：`package-exe/dist/bili-danmaku-song-order.exe`。
控制台输出：`package-exe/dist/blive-vod.exe`。

## 分发

GUI 版双击 `bili-danmaku-song-order.exe` 运行；不需要 Python，前端及预设主题图片已嵌入 EXE。

发布 ZIP 命名为 `bili-danmaku-song-order-v<版本>-win-x64.zip`，内部目录也为 `bili-danmaku-song-order/`。应用图标源放 `web/assets/app-icon.png`（建议512×512以上正方形透明PNG）；构建自动生成16–256像素多尺寸ICO并嵌入GUI EXE，用户不必转换。尚未提供PNG时保留默认图标。

v0.1.0 使用旧程序名，不能自动安装改名后的更新包；此版升级需要手动下载新版ZIP，关闭旧程序后用新版EXE替换，保留config.json/song_blacklist.txt，删除旧EXE避免误启。已发布v0.1.0资产不覆盖，改名版从v0.1.1开始，更新协议版本升至2。

目标电脑需要 Windows 10/11 x64、WebView2 运行时，以及网易云音乐桌面客户端。
先手动退出正在运行的网易云，再点击点歌机顶栏的连接按钮启动控制模式；不自动结束播放器进程。
已验证网易云版本为 3.1.3.203419，其他版本需自行验证。控制通道仅限本机 127.0.0.1:9223。

控制台版仍使用落雪音乐桌面版 2.8.0+，需预先启动。

正式Release使用 `python tools/make_release.py --notes 更新说明文件` 白名单生成ZIP、版本清单、Ed25519签名与SHA256，不直接压缩dist整个目录。用户通过设置检查、下载和确认退出更新，保留一份上一版。签名密钥/回退/恢复流程见 [docs/updating.md](../docs/updating.md)。

## 注意事项

- 首次登录后配置保存到 EXE 同目录的 `config.json`，请放在可写目录。
- 黑名单可通过 GUI 设置编辑，保存到 EXE 同目录的 `song_blacklist.txt`；旧版中文文件首次使用时自动迁移，新旧同时存在时以英文文件为准，不覆盖。新用户不需要预先下载此文件。
- 打包使用 `onefile` 模式，启动时需解压内置资源，请耐心等待。
- 分发时附带 `LICENSE` 和 `THIRD_PARTY_NOTICES.md`；不要包含个人 `config.json`、Cookie、日志或本机黑名单。
- 更新时在原目录替换EXE即可保留旁边的配置和黑名单；不要把EXE放在Program Files等不可写目录，也不要直接在压缩包内运行。用户主题在 `%LOCALAPPDATA%\BiliSongdesk\themes`，不是EXE临时解压目录。
- 不需要关闭安全软件；如遇告警请先核对来源和文件哈希。
