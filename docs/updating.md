# 更新与发布

## 用户操作

- `设置 → 版本与更新`显示真实版本；界面启动5秒后检查，随后每4小时检查，亦可手动检查。失败不弹窗打断直播。
- 便携EXE版下载后验证签名/哈希，再由用户确认退出安装；源码模式不自动覆盖源码。
- 请解压到可写目录，保留主程序名 `bili-danmaku-song-order.exe`。更新依赖Windows PowerShell 5.1，安全软件或组织策略可能阻止助手，失败时原程序不会主动退出。
- 更新只替换 `bili-danmaku-song-order.exe`、`LICENSE`、`THIRD_PARTY_NOTICES.md`。ZIP命名 `bili-danmaku-song-order-v<版本>-win-x64.zip`，包内目录 `bili-danmaku-song-order/`。配置和黑名单留在EXE旁，用户主题仍在LOCALAPPDATA，不迁移或删除。
- v0.1.0的旧更新器只认旧EXE名，因此改名版使用更新协议2，旧版会提示手动下载，不会尝试安装不兼容包。首次改名升级请退出旧程序、下载新ZIP、保留用户数据并移除旧EXE；不要覆盖已发布版本资产。
- `backup/`存一份上一版及校验信息；不要把个人文件放到此保留目录。正常完成只留当前+上一版两个EXE，下载/恢复期间可能短暂有更多临时副本。
- 回退后暂缓提示被退回的版本，更高版本仍检查。首版配置保持向后兼容；未来不兼容迁移必须单独增加数据备份与版本迁移，当前机制不回滚用户数据。
- 新版启动确认指WebView页面和Python桥准备完成，不要求登录B站或连接网易云；不表示所有业务功能都已自动验收。

## 中断恢复

主程序还能打开时，设置会提示未完成事务，并提供“恢复中断的更新”。关闭其他同目录实例、保存工坊修改再确认。恢复仅移动校验通过的原程序文件，不修改用户数据。

若主程序无法运行：
1. 退出同目录所有点歌台进程，不关闭网易云。
2. 备份完整便携目录，尤其 `config.json`、`song_blacklist.txt`；主题在LOCALAPPDATA另行保留。
3. `.update/pending.json`中的token对应 `.update/<token>/`，`previous-current/`是更新前文件；`previous-backup/`是更早的备份，`plan.json`含版本和文件SHA256，`state.json`含阶段。
4. 校验计划与旧版哈希后恢复 `previous-current/` 的主程序和许可文件。不要将 `.update/` 或 `backup/`作为普通主题目录清理。
5. 如果不熟悉恢复，下载本仓库完整Release解压到新目录，再复制自己的配置/黑名单，旧目录先保留。

程序不会强杀启动超时但仍存活的新版进程；该情况需要先关闭新版再恢复。磁盘故障、权限或安全软件拦截不能保证自动恢复成功，务必保留事务文件用于人工恢复。

## 发布者流程

1. 修改 `core/version.py`，运行全套单测及WebView回归。
2. `.build-venv/Scripts/python.exe -X utf8 package-exe/build.py gui`构建EXE。
3. `.build-venv/Scripts/python.exe scripts/verify/verify_release_archive.py`核对嵌入资源。
4. 运行隔离便携A→B→A及恢复测试：`python scripts/verify/build_update_fixture.py`（需PyInstaller）；`python scripts/verify/verify_updater_install.py`。
5. `python tools/make_release.py --notes artifacts/verify/release-notes.md`生成ZIP、`latest.json`、`latest.json.sig`和`SHA256SUMS.txt`。
6. 创建与版本匹配的 `vX.Y.Z` GitHub Release，上传全部资产，确认后发布。更新器读取 `/releases/latest/download/latest.json`及签名，预发布/草稿不作为稳定更新源。
7. 从公开地址回读清单验证签名和下载校验，再确认客户端真实检查结果。

签名使用Ed25519，公钥内置在 `core/version.py`。私钥由发布者本机Windows DPAPI保护，路径 `%LOCALAPPDATA%/BiliSongdesk-publisher/update-signing-key.dpapi`，不在仓库或发布包中。发布者需在安全位置另外备份私钥；DPAPI文件绑定Windows用户，不能直接复制到其他机器使用。丢失私钥后不能无缝签署旧客户端信任的更新，必须先规划密钥迁移，不能绕过验证。

下载会话独立于账号Cookie，会访问GitHub获取清单；不发送账号、房间号或歌单。HTTPS+Ed25519验证清单来源，SHA256校验完整包及每个文件。拒绝越界ZIP、额外数据文件、链接、重复路径和异常大小。Windows程序本身尚未Authenticode代码签名，与更新清单签名是两回事，SmartScreen可能提示。

## 开发预览

`web/update-preview.js`只在显式 `?updateDemo=1`启用，供`verify_update_preview.py`离线回归。正常启动使用`web/updater.js`和后端真实状态，不展示虚构新版或模拟进度。主题工坊`?preview=1`两种更新逻辑都不启动。
