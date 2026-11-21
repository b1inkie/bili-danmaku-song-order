# 完整字段、默认值与单位

除根部 schemaVersion/id/name/template 外，字段均可省略。对象省略等同于空对象，子字段按下表补齐。未知字段报错。

| 字段 | 类型 / 限制 | 默认值 |
|---|---|---|
| `schemaVersion` | 常量 = 1 | `"必填，无默认值"` |
| `id` | string；格式 `^[a-z][a-z0-9-]{2,47}$` | `"必填，无默认值"` |
| `name` | string，最多40字符 | `"我的主题"` |
| `author` | string，最多60字符 | `""` |
| `description` | string，最多300字符 | `""` |
| `version` | string，最多30字符 | `"1.0.0"` |
| `template` | 常量 = rose-nocturne | `"必填，无默认值"` |
| `colors.background` | string；格式 `^#[0-9a-fA-F]{6}$` | `"#110e14"` |
| `colors.card` | string；格式 `^#[0-9a-fA-F]{6}$` | `"#201820"` |
| `colors.input` | string；格式 `^#[0-9a-fA-F]{6}$` | `"#2a2028"` |
| `colors.text` | string；格式 `^#[0-9a-fA-F]{6}$` | `"#f5e9dc"` |
| `colors.secondary` | string；格式 `^#[0-9a-fA-F]{6}$` | `"#c7acaf"` |
| `colors.muted` | string；格式 `^#[0-9a-fA-F]{6}$` | `"#a38690"` |
| `colors.accent` | string；格式 `^#[0-9a-fA-F]{6}$` | `"#dc8c9b"` |
| `colors.button` | string；格式 `^#[0-9a-fA-F]{6}$` | `"#edd7c2"` |
| `colors.buttonText` | string；格式 `^#[0-9a-fA-F]{6}$` | `"#39202b"` |
| `colors.border` | string；格式 `^#[0-9a-fA-F]{6}$` | `"#4c333e"` |
| `text.name` | string，最多24字符 | `"这里是名字"` |
| `text.signature` | string，最多32字符 | `"这里是签名"` |
| `text.heading` | string，最多32字符 | `"这里是主标题"` |
| `text.subtitle` | string，最多60字符 | `"这里是副标题"` |
| `text.eyebrow` | string，最多60字符 | `"这里是引导语"` |
| `text.motto` | string，最多80字符 | `"这里是签名说明"` |
| `text.vertical` | string，人物栏竖排装饰，最多60字符 | `""`（隐藏） |
| `text.sceneNumber` | string，人物区底部装饰编号，最多12字符 | `""`（隐藏） |
| `text.sceneTitle` | string，人物区底部主题名，最多60字符 | `""`（隐藏） |
| `text.sectionNumber` | string，歌单前装饰编号，最多12字符 | `""`（隐藏） |
| `fonts.name` | string，字体家族名≤100字符，禁控制字符 | `""`（模板中文名字体） |
| `fonts.signature` | string，同上 | `""`（模板英文签名字体） |
| `fonts.heading` | string，同上 | `""`（模板标题字体） |
| `fonts.subtitle` | string，同上 | `""`（界面默认字体） |
| `fonts.eyebrow` | string，同上 | `""`（界面默认字体） |
| `fonts.motto` | string，同上 | `""`（界面默认字体） |
| `fonts.vertical` | string，字体家族名≤100字符，禁控制字符 | `""`（界面默认字体） |
| `fonts.sceneNumber` | string，同上 | `""`（Georgia / serif） |
| `fonts.sceneTitle` | string，同上 | `""`（界面默认字体） |
| `fonts.sectionNumber` | string，同上 | `""`（Georgia / serif） |
| `character.image` | string，最多160字符；格式 `^$|^assets/[A-Za-z0-9_-]+\.(png|jpg|jpeg|webp)$` | `""` |
| `character.scale` | number [0.5, 1.6]；模板倍数 | `1` |
| `character.x` | number [15, 85]；装饰栏宽度% | `50` |
| `character.y` | number [-100, 100]；CSS px | `0` |
| `character.flip` | boolean | `false` |
| `character.visible` | boolean | `true` |
| `background.image` | string，最多160字符；格式 `^$|^assets/[A-Za-z0-9_-]+\.(png|jpg|jpeg|webp)$` | `""` |
| `background.dim` | number [0, 1] | `0.65` |
| `background.scale` | number [0.5, 3]，以居中cover铺满为基准的倍数 | `1` |
| `background.x` | number [-1000, 1000]，CSS px，正值向右 | `0` |
| `background.y` | number [-1000, 1000]，CSS px，正值向下 | `0` |
| `layout.characterSide` | 枚举left / right | `"left"` |
| `layout.characterRatio` | number [0.28, 0.43]；装饰栏占比 | `0.43` |
| `layout.introHeight` | number [90, 140]；CSS px | `118` |
| `layout.cardOpacity` | number [0.4, 1] | `0.72` |
| `decorations.glow` | number [0, 1] | `0.3` |
| `decorations.rings` | boolean | `true` |
| `decorations.fade` | number [0, 1] | `0.9` |
| `decorations.signature` | boolean | `true` |
| `capture.background` | string；格式 `^#[0-9a-fA-F]{6}$` | `"#1b141e"` |
| `capture.card` | string；格式 `^#[0-9a-fA-F]{6}$` | `"#2b1b28"` |
| `capture.fontSize` | number [12, 18]；CSS px | `14` |
| `capture.compact` | boolean | `false` |

## 语义补充

`colors` 全部为六位十六进制，背景/卡片/输入框/正文/次要文字/辅助文字/强调色/按钮/按钮文字/边框依次独立控制。
`text` 对应人物中文名、英文签名、主标题、副标题、英文引导语、签名说明，以及竖排装饰、人物区编号、人物区主题名、歌单装饰编号。后四项省略默认隐藏，避免旧的非玫瑰主题继承写死英文；玫瑰模板/随程序预设显式配置玫瑰文案。编号仅装饰，与歌曲数量和播放顺序无关。所有文案支持空串隐藏，纯文本不支持HTML，斜杠分隔由程序自动添加。
`fonts` 与 `text` 十个键一一对应；每项为一个本机字体家族名，不是CSS列表、路径或URL。空串/省略保留模板默认，缺字体自动回退；不嵌入或导出字体文件，输入框字体不随之改变。
`character.image`、`background.image` 空字符串为无图；仅包内静态图片，不接受URL或本机绝对路径。
`decorations.signature=false`隐藏中英文签名及其说明；`character.visible=false`只隐藏图片，装饰不受影响。
`capture.compact=true`为主题默认精简显示，本机工具栏精简开关可以进一步启用；主题不覆盖置顶/不透明度。
坐标、缩放、素材限制及主窗/小窗差异见 [README](README.md#5-布局与坐标语义)。
