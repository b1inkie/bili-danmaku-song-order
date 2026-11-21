# 开发目录与验证

## 目录原则

- 根目录只放 `main_gui.py` / `main.py` 启动入口、启动bat、依赖和项目说明。
- `core/`：GUI运行引擎、B站登录、配置、网易云与主题模块。
- `legacy/`：原控制台使用的LX Music协议及多源搜索；不修改第三方 `blivedm/`。
- `tests/`：自动发现的离线单元测试，不访问真实账号或队列。
- `scripts/verify/`：WebView离线回归、默认只读的本机播放器验证。
- `scripts/smoke/`：早期诊断/桥接/引擎冒烟，部分会启动真实登录流程，只手动按需使用，不放入自动测试。
- `tools/`：主题校验打包、Schema维护及语法检查。
- `artifacts/verify/`：日志、诊断JSON等可再生输出，Git忽略。开发者请把重定向日志也写到这里。
- `package-exe/`：打包脚本、build/dist（忽略）。

账号配置 `config.json` 和黑名单 `song_blacklist.txt` 在源码根目录/打包exe旁。旧版中文黑名单首次使用时原地改名，已有英文文件优先且不覆盖；两种文件名Git忽略。已安装主题在 `%LOCALAPPDATA%/BiliSongdesk/themes`。根目录只保留 `start_gui.bat` 测试启动GUI，纯ASCII内容、CRLF换行，无中文编码依赖；原控制台使用 `python main.py`。

## 常用命令（源码根目录）

```powershell
python main_gui.py
python main.py 房间号
python -m unittest discover -s tests -v
python -m unittest tests.test_theme_manager -v
python tools/check_syntax.py
python tools/theme_tool.py validate docs/themes/examples/rose-nocturne
python tools/theme_tool.py pack 我的主题目录 我的主题.songtheme
```

主题工具也支持 `python -m tools.theme_tool ...`；相对输入/输出路径按调用者的工作目录解释。

## 界面离线回归

```powershell
New-Item -ItemType Directory -Force artifacts/verify | Out-Null
python scripts/verify/verify_workshop.py > artifacts/verify/workshop.log 2>&1
python scripts/verify/verify_theme_library.py > artifacts/verify/theme-library.log 2>&1
python scripts/verify/verify_theme_sync.py > artifacts/verify/theme-sync.log 2>&1
python scripts/verify/verify_capture.py > artifacts/verify/capture.log 2>&1
python scripts/verify/verify_playlist_ui.py
python scripts/verify/verify_compact_playlist.py
python scripts/verify/verify_settings.py
python scripts/verify/verify_update_preview.py
python scripts/verify/verify_themes.py
```

脚本按自身路径定位项目，可从其他工作目录通过绝对路径运行。WebView可能产生临时目录清理告警；区分告警与测试断言失败。不要并行启动多个桌面回归，避免窗口及运行时互相影响。

正常启动使用真实更新器 `core/updater.py` + `web/updater.js`，版本与发布流程见 [updating.md](updating.md)。纯前端模拟仅显式`?updateDemo=1`启用，供`verify_update_preview.py`离线回归；其0.1.0/0.2.0仍是测试数据，不参与正常启动。真实协议测试`tests/test_updater.py`；打包资源检查`verify_release_archive.py`；隔离实际EXE升级/回退/失败恢复运行`verify_updater_install.py`，均不登录账号或操作真实播放器。

## 本机网易云验证

```powershell
python scripts/verify/verify_netease_live.py
python scripts/verify/verify_playlist_live.py
python scripts/verify/verify_queue_live.py
```

默认只读。`verify_netease_live.py --queue/--skip`、另两者 `--run` 会改变真实队列/播放状态，必须明确授权并避开直播；不会恢复进度。不通过批量回归自动执行写测试。

## Schema维护与打包

`python tools/make_theme_schema.py` 会覆盖Schema和示例，仅维护者有意更新格式时使用；不要在测试中运行它。执行前提交回滚点，执行后核对所有字段、预设与AI提示词。

在线主题库：`core/theme_catalog.py`签名清单/受限下载，工坊`web/theme-library.*`手动刷新；`tests/test_theme_catalog.py`及`verify_theme_library.py`使用测试密钥/模拟网络，不上传。发布工具`tools/make_theme_catalog.py`生成全量清单和包，`tools/publish_theme_catalog.py --publish`才实际上传专用预发布（禁止标记Latest），步骤见[ONLINE.md](themes/ONLINE.md)。

```powershell
python package-exe/build.py gui
python package-exe/build.py console
```

构建根路径仍基于 `package-exe/build.py`，web与主题文档路径不变。结构整理回归会用mock检查PyInstaller命令，不自动安装/完整构建或启动登录。
