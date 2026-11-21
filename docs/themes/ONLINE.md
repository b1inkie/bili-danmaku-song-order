# 同仓库在线主题库

在线主题不随 EXE 更新。主题工坊 → **在线主题库** → 刷新 → 下载主题；安装后点“载入刚安装的主题”预览，再自行保存并应用。下载不会退出程序、修改账号或操作网易云。

## 用户侧规则

- 同一个 GitHub 仓库：`b1inkie/bili-danmaku-song-order`，不需要另建仓库。
- 专用 `theme-assets` Release 必须是 **Pre-release**，不可标记 Latest，不参与程序自动升级。
- 客户端读取固定 `releases/download/theme-assets/catalog.json` 与 `.sig`，验证发布者 Ed25519 签名后列出主题。
- 清单包含 ID、名称、作者、描述、主题版本、格式版本、最低程序版本、下载地址、大小与 SHA256。列表文字用纯文本显示，不执行远程HTML或JS。
- 每个包必须为该 Release 中的 `<主题ID>-<版本>.songtheme`。不接受前端提供的任意网址或保存路径。
- 主题包仍是现有 `theme.json + assets/` ZIP 格式；最大40MB、64项、单图12MB/1600万像素等原限制不变。
- 下载后先校验大小/哈希，并在隔离临时目录解码校验，再安装到用户自己的主题目录。
- **安装不自动应用**。已有同ID主题不会覆盖，另存副本（新ID）；新版也是副本，不会丢失旧版或用户修改。
- 本机来源记录为 `themes/online-installations.json`，仅用于显示本地已下载版本，不授权替换用户文件。
- 删除过的主题不会因刷新重新安装；下载必须主动点击。关闭整个工坊会停止后续安装，已完成安装的主题保留。
- 网络/签名失败显示原因，保留当前已验证列表，不影响本地主题；未发布清单时明确显示“在线主题库尚未发布”。不伪造在线结果。
- 第一版手动刷新，无后台自动推送、预览封面、主题角标、静默覆盖或一键替换旧主题。
- 不支持当前主题格式或最低程序版本过高的主题会禁用下载，提示先更新点歌台。

**现有旧 EXE 不会自动获得这个入口**：需要先升级到含主题库功能的程序一次，之后新增主题无需更新 EXE。源码 `start_gui.bat` 重启即使用本地的新代码。

## 发布者：首次发布与新增主题

确认图片允许分发。**禁止恢复已经移除的 Haruka OC**，不能从旧安装或旧包中拿该图作为模板。

1. 在工坊制作并导出 `.songtheme`，或准备独立文件夹 `theme.json + assets/`。
2. 为每套主题填写稳定 `id`，`version` 用三段数字（如 `1.0.0`）。内容变化必须提升主题版本，不复用已发布的包名。
3. 在发布机器上生成全量清单与签名包（以下只写本地文件，不上传）：

   ```powershell
   python tools/make_theme_catalog.py `
     --theme web/themes/black-lotus-violet-resonance `
     --theme web/themes/strelizia-twilight-resonance `
     --output artifacts/theme-library
   ```

   `--theme` 可多次传入，也可用导出的 `.songtheme` 路径。**每次传完整的在架主题集合**，不是只传新加的一套；省略的主题将不在新版清单列出，但不会删用户已安装主题。

   默认最低程序版本取当前 `core/version.py`；如确实兼容更早的含在线主题库版本，可显式 `--minimum-app-version 0.1.1`。这不是允许不含在线入口的旧EXE自动安装。

4. 检查输出：

   ```text
   artifacts/theme-library/
   ├─ catalog.json
   ├─ catalog.json.sig
   ├─ black-lotus-violet-resonance-1.0.0.songtheme
   └─ strelizia-twilight-resonance-1.0.0.songtheme
   ```

5. 发布到当前仓库（此命令会真实上传，必须显式确认）：

   ```powershell
   python tools/publish_theme_catalog.py artifacts/theme-library --publish
   ```

   使用系统 Git credential helper 中的 GitHub 凭据，不把 Token 放进命令、主题或仓库。工具仅操作 `theme-assets` 专用预发布：不存在时建草稿，上传全部主题包并核对GitHub哈希，然后替换清单签名和清单，最后公开为 Pre-release、`make_latest=false`。已有同名但不同内容的主题包会拒绝上传，需要提升主题版本。

6. 用新程序主题库真实刷新并下载，检查配置/图片完整及预览效果。发布工具的上传成功不等于用户网络下载一定成功。

只发布主题不需要修改EXE、不需要打程序版本号、不动程序的 `latest.json` 或正式Release。

## 密钥与发布一致性

复用当前发布者 Ed25519 密钥，私钥保存在发布者 Windows 用户的 `%LOCALAPPDATA%/BiliSongdesk-publisher/update-signing-key.dpapi`，不进入Git或主题包。客户端只带公钥；不要生成新密钥替换原有发布者身份。DPAPI文件须妥善备份并考虑其用户/机器绑定，不能当普通便携私钥随意迁移。

- 包文件名按ID+版本固定，已发布包不可原地修改；可保留旧附件供旧清单下载。
- 清单是可更新的全量列表，最多200套。打包结果使用固定ZIP时间戳和顺序，相同输入重复构建字节一致。
- 上传顺序是包 → 签名 → 清单。GitHub不能原子替换两个附件，更新中的短暂签名不匹配会使刷新安全失败，稍后重试；不会降级为无签名安装。
- `publish_theme_catalog.py`不自动删除旧包，避免仍持有旧清单的客户端断链。下架主题可从全量清单移除，但不要悄悄用新内容替换其旧附件。
- 不做抗回滚的远程单调版本保证；本地已编辑主题保护通过“只另存不覆盖”实现。

## 开发验证

```powershell
python -m unittest tests.test_theme_catalog -v
python scripts/verify/verify_theme_library.py
python scripts/verify/verify_workshop.py
```

以上用临时目录、测试签名密钥和模拟HTTPS，不触碰账号/播放器，不上传任何Release。发布端另有模拟API测试，检查只创建预发布、禁止替换同名不同内容包、上传后不标记Latest。
