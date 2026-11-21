# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

B站直播弹幕点歌机 — 监听B站直播间弹幕，通过 LX Music 桌面版的 Scheme URL 协议实现弹幕点歌/切歌功能。纯 Python 异步实现，Windows 环境运行。

## Commands

目录整理后以此为准：运行模块在core/，旧控制台多源/LX模块在legacy/，单测在tests/，原_verify_*.py现为scripts/verify/verify_*.py，旧冒烟在scripts/smoke/（可能登录，不自动跑），工具在tools/。下文历史测试文件名省略目录时均按此映射；不在根目录新增测试、诊断、工具或日志。日志/JSON报告写artifacts/verify/（Git忽略）。入口main_gui.py/main.py、bat及用户config.json/黑名单位置不变。

黑名单文件名以此为准：song_blacklist.txt（源码根目录/打包EXE旁），core/app_dir.get_blacklist_path首次使用时将旧中文文件原地重命名，已有英文文件不覆盖；新旧同时存在保留旧文件但只读英文文件。两种文件名均Git忽略，不随release分发。config.json位置不变；EXE目录必须可写，更新仅替换EXE保留数据。

真实更新：core/version.py统一版本和Ed25519公钥，core/updater.py独立线程/aiohttp无账号会话，从固定GitHub latest.json+.sig检查，启动5秒后/每4小时；core/update_protocol.py验证签名、版本平台、大小/哈希与ZIP白名单；web/updater.js驱动真实设置及角标。下载暂存.update/<token>，ready.json支持下次启动继续安装；core/update-helper.ps1握手后等退出，替换EXE/许可文件，GUI frontend_ready确认健康才保留backup上一版，失败恢复/中断恢复入口，不修改config/黑名单/主题，不关闭网易云。core/app_instance.py打包版同目录单实例。签名私钥DPAPI存在LOCALAPPDATA/BiliSongdesk-publisher，不入Git；tools/make_release.py白名单打包并签名。docs/updating.md记流程/限制。模拟更新只显式?updateDemo=1运行，主题?preview=1不启动更新。真实EXE隔离验证scripts/verify/build_update_fixture.py+verify_updater_install.py，启动仅--release-smoke-test不加载账号或播放器。

发布命名自待发布v0.1.1统一为bili-danmaku-song-order.exe，ZIP为bili-danmaku-song-order-v<版本>-win-x64.zip，包内同名目录；core/version.py APP_NAME/EXE_NAME统一，更新协议2防止v0.1.0旧更新器按旧名错误安装，旧版需手动升级一次，不覆盖已发布v0.1.0。用户数据目录不改。图标源web/assets/app-icon.png（用户提供，静态PNG建议512px正方形），package-exe/build.py构建生成16–256px ICO并传--icon；缺图时保留默认，不声称已更换图标。

```bash
# 安装依赖
pip install -r requirements.txt

# 启动程序
python main.py
python main.py 房间号

# 测试与语法检查
python -m unittest discover -s tests -v
python tools/check_syntax.py
python tools/theme_tool.py validate docs/themes/examples/rose-nocturne
```

## Architecture

### 核心流程

```
main.py (入口)
  → bili_login.ensure_login() — 登录B站（cookie加载/刷新/扫码）
  → blivedm.BLiveClient — WebSocket连接直播间，监听弹幕
  → MyHandler._on_danmaku() — 解析弹幕指令
  → 多源搜索 (kg > wy > tx) → song_handler → LX Music 播放
```

### GUI 架构（main_gui.py + web/ + core/）

```
pywebview 窗口（WebView2 渲染本地 web/ 前端）
  ├─ main_gui.py — js_api 桥：get_state/poll_events/confirm_use_account/switch_account/start_listen/stop_listen/request_song/skip_next/黑名单读写
  ├─ core/engine.py — 独立 asyncio 引擎：登录→后台弹幕指令→core/player 网易云客户端搜索/追加待播（实验性本机 CDP）
  ├─ core/events.py — EventBus：引擎线程 emit，GUI 线程 drain（前端 380ms 轮询 poll_events）
  └─ core/settings.py — config.json + 黑名单（每次实时读，热生效）
```

- 前端主题：近黑底 #0a0a0b + 卡片 + 胶囊按钮 + 毛玻璃弹窗（参考 agents-anywhere.com），B站粉 #fb7299 强调色，深浅色可切换
- 圆角窗口保留不透明 frameless + WinForms Form.Region；GDI 句柄需声明 64 位签名并释放。此前“透明窗口一定穿透/SetWindowRgn 被吞”的诊断证据不足，不作为平台事实；当前不重新启用透明窗口或 WS_THICKFRAME。拖拽监听绑定整个 .windowbar（pywebview-drag-region），顶栏按钮阻止 mousedown 冒泡。标题栏从窗口上沿开始，正中顶部缩放手柄禁用以避免抢占拖拽。
- 根目录只保留start_gui.bat启动GUI测试，旧两个中文bat已删除；脚本纯ASCII+CRLF（GBK兼容），不需要chcp。后续若bat包含中文必须用GBK或显式处理编码，避免cmd乱码。
- 登录交互（账号确认/二维码）通过事件总线流转，不弹浏览器；bili_login.py 不传钩子时保持原控制台行为
- GUI 是纯点歌机：普通弹幕不展示；现在为真实网易云歌单（非点播流水），每1.5秒同步 current/status/items，当前高亮，图标播放暂停，右侧排序/删除。经典深浅色无主播logo，OC仅Haruka主题。request_id 仍用于搜索中反馈/失败事件。core/playlist_runtime.py 允许列表动作；播放状态2=Playing、1=Pause。sortPlayingList options.offset是移除前插入边界：上移index-1，下移index+2；removeIds传完整item数组；播放指定曲用playing/playOneTrackInPlayingList；暂停/继续playing/pause和playing/resume。均真实验证且恢复原队列/曲目/暂停，进度未实现，不伪造。metadata 缺少歌手时通过客户端批量歌曲详情缓存补全。API所有播放器操作提交引擎同一事件循环，账号确认异步等待避免阻塞。14项单元测试，_verify_playlist_ui.py 9 populated layouts，_verify_playlist_live.py默认只读/--run真实操作。
- 消费队列：Settings.get/set_queue_policy持久化config.queue_policy(enabled默认false,maximum默认10,1–500含当前)。Player.queue_policy由Engine绑定，入队锁内检查容量/重复，客户端动作前再次检查数量/顺序模式/钩子租约。core/queue_runtime.py按AudioPlayer.subscribePlayStatus能力订阅end，只有info.code=0为自然结束；15秒租约、播放实例ID保护、暂停等待不误删；最后EOF先stop/clearPlayingInfo再移除避免循环旧歌。Engine后台每秒queue_tick，UI禁用可离线保存。playing/onUpdate+onSwitchPlayingMode设playOrder（switchPlayingMode从AI可能替换队列，故不用）。点歌台skip成功再删前曲；指定曲切换不消费。已超额只拒新点歌不截断。关闭不恢复旧模式。_verify_queue_live.py默认只读/--run真实验证并恢复队列当前状态模式，不恢复进度；test_queue_policy.py6项离线。
- 歌单条目新增禁止符号SVG拉黑按钮，Api.blacklist_song按真实快照ID解析歌名，core/settings.py追加去重并原子替换黑名单；不删队列/不切歌。GUI后台弹幕按输入完整名和搜索结果名二次拦截（同名歌手不区分），手动点歌仍绕过。设置可编辑解除，test_song_blacklist.py 7项离线测试，_verify_playlist_ui.py验证确认/取消/去重且播放不变。
- 主题系统：内置仅dark/light，haruka.css为玫瑰布局渲染器（非固定主题），不再附带Haruka OC。工坊新建无人物图草稿，主题为v1配置+静态PNG/JPEG/WebP，无JS/CSS/HTML/SVG/远程路径/字体文件；图片自动优化。WorkshopApi独立编辑窗，iframe ?preview=1模拟主窗/小窗、不连播放器，ThemeRuntime共用渲染。selection.json持久化已应用快照，保存与应用分离，主窗1秒/小窗1.5秒同步，坏主题回退dark。自定义主题可删除，当前删除回退dark；人物低于功能层且不按装饰栏裁剪。用户/AI教程docs/themes/README.md、FIELDS.md、Schema及示例；tools/theme_tool.py离线校验打包。在线库已支持，见下条；预览拖动、字体文件导入及动画仍未实现。
- 初始预设仅web/themes/presets.json中的黑睡莲和鹤望兰，按ID首次安装，不覆盖修改、不复活删除。黑睡莲保留id=black-lotus-violet-resonance，主题版本1.0.1。preset-haruka源目录与OC已移除；已有用户Haruka副本不自动操作。旧selection.active=haruka仅在存在已安装preset-haruka时迁移，否则回退dark。
- 主题素材存储以此条为准：每个installed/<id>/目录自含theme.json+assets/，不再使用公共素材运行时缓存；删除仅清理本主题图片，其他主题不受影响。ThemeManager启动复制旧root/assets至每个所有者及已应用快照所需图片，旧文件保留备份；storage-v2.json记录迁移完成，防本地图片缺失时从旧共享目录复活。未保存素材是进程临时目录，payload将任意原图名变为内容哈希引用避免复制主题时同名图片串用；save复制到自己的assets。AI提示词和README说明单文件夹交付，ZIP根仍直接theme.json+assets。不在用户文件夹写迁移标记，可直接单文件夹校验打包。
- 在线主题库：core/theme_catalog.py固定同仓库theme-assets预发布/catalog.json+.sig，Ed25519验证（复用更新公钥），仅允许本仓库版本化.songtheme、40MB及现有主题安全限制；隔离校验后安装，不自动应用，同ID永远另存副本。工坊左侧在线主题库手动刷新、显示版本/兼容性/进度、下载后可载入预览，关闭整窗停止未完成安装。online-installations.json仅来源记录。tools/make_theme_catalog.py生成确定性包和全量签名清单；tools/publish_theme_catalog.py --publish才上传，theme-assets必须Pre-release/make_latest=false，不影响程序releases/latest。发布先包后清单，不替换同版本不同内容包、不自动删旧包。文档docs/themes/ONLINE.md；test_theme_catalog.py和verify_theme_library.py用测试签名/mock HTTPS。旧EXE需升级一次获得入口，之后加主题无需更新EXE。已移除Haruka OC与preset-haruka目录，新建为无人物图模板，绝不恢复该图。
- 工坊新增左侧打开installed目录按钮（os.startfile固定路径）与删除当前已保存主题按钮（共享ConfirmDialog、草稿禁用、当前删除回退dark）。ThemeWorkshop窗frameless/easy_drag=False/shadow=False，复用main_gui.apply_round_region，workshop-window.js SVG标题栏+边缘缩放/980×680最小；最大化Region=None，恢复圆角，关闭未保存自定义确认。_verify_workshop.py验证原生Region/拖拽与按钮热区/最小布局/目录调用mock/删除取消确认/关闭取消；test_theme_manager.py27项。
- 原写死玫瑰文案现为theme.text.vertical/sceneNumber/sceneTitle/sectionNumber，分别竖排/人物区编号/人物区主题名/歌单装饰编号，各有fonts同名选择；默认空串隐藏，玫瑰模板/预设显式填ROSE。DOM用scene-index/scene-title独立叶节点，只textContent渲染，reset恢复可信原标记；斜杠由CSS生成，空串无孤立分隔。工坊十项显示文案，AI提示词/FIELDS/示例同步，不改用户已保存主题。
- AI提示词明确单个.songtheme含配置+图片且同时用于主窗和小窗；小窗仅capture.background/card/fontSize/compact及colors.text/muted/accent/border，不使用主窗OC/背景图/text/fonts/装饰；最低300×280/常规420×620。test_theme_manager验证提示词示例完整覆盖Schema及独立接收目录导出导入capture保留；_verify_theme_sync验证小窗实际配色/字号/精简变化；ThemeRuntime.reset清理themeCompact避免预览切换残留。
- 主题字体：根fonts对象name/signature/heading/subtitle/eyebrow/motto为单个本机字体家族名(≤100字符禁控制字符)，默认空串保留原模板，兼容旧v1配置。WorkshopApi.bootstrap通过WinForms InstalledFontCollection枚举字体名，工坊文案下各自下拉选择、不改编辑框字体；theme-runtime将名称转义为单个CSS引号家族+原模板回退，reset清除变量。不加载/导出字体文件，不支持远程字体；AI提示词、Schema、默认模板和docs同步。test_theme_manager新增字体往返，_verify_workshop验证选择/实时预览/输入框不变/应用保存/恢复。
- 直播捕捉小窗：core/capture_window.py 独立frameless不透明圆角窗，固定标题「B站点歌台 · 直播歌单」，延迟复用main_gui.apply_round_region，标题栏pywebview-drag-region，边缘JS缩放。CaptureApi只提供歌单读取及窗口属性/隐藏/缩放，不消费登录事件或提供播放器写动作。SVG工具栏：不透明度40–100%(WinForms Opacity/UI线程)、置顶(TopMost)、精简、定位当前、收起；本次运行内关闭重建保留偏好，不写磁盘。PlaylistFeed主窗/小窗共享1秒缓存，失败标记旧快照，主窗动作publish。1.5秒同步。主窗按钮召回/隐藏及重置位置，隐藏保留窗口，主窗退出销毁。test_capture_window.py14项单元测试；_verify_capture.py覆盖9主布局/9小布局、原生Region/Opacity/TopMost、工具栏和生命周期，不用CUA。捕捉软件是否采纳窗口Opacity须另行预览。
- GUI 播放器用网易云；原 main.py 控制台仍用落雪。core/player.py 本机 CDP 127.0.0.1:9223，需以控制模式启动，不杀进程/不导出 Cookie。已在本机 3.1.3.203419 真实验证搜索、追加入队不抢播、切歌；core/netease_runtime.py 能力扫描缓存 exports（含 prototype getStore/getDispatch），扫描 request factory 特征，不硬编码模块号。该版 store=13.a，request factory=8.a（仅诊断事实，不在实现写死）。搜索 /api/cloudsearch/pc，详情 /api/v3/song/detail；入队必须传 trackFrom.fromInfo.sourceData，否则客户端抛 TypeError。切歌用 playingList/jump2Track，发动作后轮询队列/当前 ID 确认。离线9项测试 test_gui_changes.py；真实测试 _verify_netease_live.py 默认只读，--queue/--skip 会影响播放器。
- 打包：package-exe/build.py，`gui` 模式 --windowed --onefile，web/ 通过 --add-data 打进 exe

### 模块职责

- **main_gui.py / main.py** — GUI（网易云）/原控制台（落雪）启动入口
- **core/app_dir.py** — 源码根目录、打包资源与用户配置路径；不能按core目录存配置
- **core/bili_login.py / core/qr_page.py** — B站登录及原控制台二维码页
- **core/config.py / core/settings.py / core/song_commands.py** — 初始配置、持久化及统一指令
- **legacy/lxmusic.py / legacy/song_handler.py** — 控制台LX Scheme协议及结果转换
- **legacy/kg_search.py / wy_search.py / tx_search.py / search_common.py / search.py** — 控制台多源搜索
- **tests/** — 离线unittest；`python -m unittest discover -s tests -v`
- **scripts/verify/** — 界面离线验证和默认只读的真实播放器脚本；真实写动作必须显式参数
- **tools/** — theme_tool.py、make_theme_schema.py、check_syntax.py；文档见docs/development.md
- **blivedm/** — 第三方弹幕库，不修改

### 搜索模块标准返回格式

每个搜索模块的 `search_and_get_first()` 返回：
```python
{
    "source": "kg" | "wy" | "tx",
    "name": str, "singer": str, "songmid": str,
    "img": str, "albumId": str, "interval": str,  # mm:ss
    "albumName": str, "types": list, "hash": str
}
```

### 配置文件 config.json

运行时自动生成，包含 `roomid` 和 `cookies`（登录凭证）。已在 .gitignore 中。

### 弹幕指令

- `点歌 歌名 - 歌手` — 点歌，歌手可省略；分隔符为两侧有空格的半角 ` - `，歌名/歌手可含空格。GUI与控制台共用 song_commands.DIANGE_RE。
- `下一首` — 切歌（限房管）

## Key Conventions

- 所有网络请求使用 `aiohttp`，异步处理
- 与 LX Music 通信方式：生成 Scheme URL 后通过 `webbrowser.open()` 调用
- 搜索优先级固定为 kg → wy → tx，前一个有结果就不再查后续源
- 文件编码统一 UTF-8
- 项目语言为中文（注释、提示信息、文档）
