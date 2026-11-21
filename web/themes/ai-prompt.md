请根据我随后提供的风格要求和 PNG 素材，制作一套可直接导入「B站点歌台」的主题。你不需要程序源码，按下面的文件格式制作即可。请交付成品，不要只给设计建议，也不要让我安装开发环境。

【具体做法】
1. 从素材提取配色，保证歌名和按钮清楚可读。主界面固定为“人物装饰栏＋标题、歌单、点歌操作区”，可以左右互换；直播小窗只显示歌单，使用独立配色。
2. 制作 UTF-8 的 theme.json，按下方完整示例修改。只允许已有字段；schemaVersion 固定为 1，template 固定为 rose-nocturne。主题名、人物名、签名和标题按我的要求替换，不要照搬示例名称。
3. 每个主题单独建立一个文件夹，文件夹名建议与id一致，例如 my-music-room/。该文件夹内放 theme.json 和自己的 assets/，不引用其他主题或公共素材目录。我提供的 OC 保存为 my-music-room/assets/character.png，保持透明底，不必转 WebP；可选背景为同目录 assets/background.png。theme.json里的引用仍写 assets/character.png、assets/background.png（相对本主题文件夹），不要写my-music-room前缀。没有对应素材时image填空字符串，不要虚构文件。程序导入时自动优化图片。
4. 交付完整的主题文件夹；另外将里面的 theme.json 和引用的图片直接放在 ZIP 根目录，压缩为“主题名.songtheme”（普通.zip也能导入），ZIP内不要再套一层主题文件夹。这个单文件必须同时包含配置和素材，别人收到后直接导入就能用，不依赖你的本机路径。不能只将JSON改后缀，也不能只给一张效果图。
5. 检查 JSON 能解析、数值在范围内、素材存在且全部在本主题文件夹内后，交付主题文件夹和主题包，并简短说明“主题 → 主题工坊 → 导入主题包 → 保存并应用”。你没有运行目标程序时，不要声称已在程序中验证。若你无法生成文件，则输出完整 theme.json 和图片摆放说明，不要伪造下载链接。

【目录：一个主题一个文件夹】
my-music-room/
├─ theme.json
└─ assets/
   ├─ character.png
   └─ background.png（可选）

分享包 我的主题.songtheme（ZIP）中直接是上述 theme.json 和 assets/，不包含外层 my-music-room/。所有图片路径相对于theme.json，不能借用其他主题文件夹的图片。

【完整 theme.json 示例】
{{THEME_JSON}}

【字段含义和允许范围】
- 根字段：id 为3–48字符的小写字母开头的英文/数字/连字符，不用 dark、light、haruka（保留兼容标识）；name 为主题名，非空且≤40字；author≤60字，description≤300字，version≤30字。schemaVersion、id、name、template 必填；其余可省略，使用示例中的默认数值/配色。图片默认为空；工坊默认“这里是名字”“这里是主标题”等只用于教程，请替换为本主题的文案，不保留占位文字。
- colors：background主背景、card卡片、input输入框、text正文、secondary次要文字、muted辅助文字、accent强调色、button按钮底色、buttonText按钮文字、border描边。所有颜色只能是六位 #RRGGBB；不能填 rgba、渐变表达式或CSS。
- text：name人物中文名≤24字；signature英文/手写签名≤32字；heading主标题≤32字；subtitle副标题≤60字；eyebrow标题上方小字≤60字；motto签名说明≤80字；vertical左/右人物栏竖排装饰≤60字；sceneNumber人物区底部装饰编号≤12字；sceneTitle人物区底部主题名≤60字；sectionNumber歌单标题前装饰编号≤12字。这些均是主题的一部分，请按本主题风格填写，不能沿用玫瑰英文。编号不是播放序号或歌曲数量，可填其他短文字；后四项省略或填空串隐藏。分隔符由程序生成，不手填斜杠。均为纯文字，不写HTML。
- fonts：与text相同的十个键，可独立指定一个本机字体家族名称（≤100字符，不能有控制字符），例如heading填“微软雅黑”、signature填“Georgia”。空串或省略保留模板字体；用户未安装则自动回退。只能写名称，不写CSS字体列表/路径/URL，不打包字体文件。
- character：image为包内图片路径或空串；scale为模板缩放倍数0.5–1.6，以人物底部中心缩放，1为模板大小；x为人物中心在装饰栏宽度中的百分比15–85，50居中；y为相对模板的CSS像素偏移-100–100，正数向上；flip为是否左右翻图；visible为是否显示图片。OC不按人物栏裁剪，可延伸到其他元素下方，人物与装饰始终在功能区下层且不拦点击。
- background：image为背景图路径或空串；dim为暗化强度0–1，0不暗化、1全黑。scale为0.5–3倍，默认1，以居中cover铺满为基准绕中心缩放；x/y为-1000–1000 CSS像素，默认0，正值向右/向下，位移不随缩放倍增。缩小/移出露出主题底色，仅主窗背景图生效，不影响人物或功能区。
- layout：characterSide只取left或right；characterRatio为人物栏占比0.28–0.43；introHeight为标题区高度90–140 CSS px（窗口高度≤680时最多100px）；cardOpacity为卡片不透明度0.4–1。按最低920×600预留功能空间，不设计任意新布局。
- decorations：glow光晕强度0–1；rings圆环开关；fade人物底部淡出强度0–1；signature中英文签名开关。开关只能填true/false。
- capture：必须为直播歌单小窗单独搭配background底色、card卡片色（均#RRGGBB），fontSize为列表基础字号12–18 CSS px，compact为默认精简开关（隐藏歌手等次要信息）。小窗正文用colors.text，辅助信息用colors.muted，当前歌曲/按钮强调用colors.accent，描边用colors.border；其他主窗专用颜色不直接控制小窗。小窗不显示人物OC、背景图、text/fonts文案或主窗装饰，也不使用background的缩放/平移。不要虚构小窗图片、字体、布局字段。透明度/置顶是用户窗口设置，不由主题决定。主窗和小窗使用同一个theme.json和同一个主题包，无需另做小窗包。

【主窗与小窗自检】
检查主窗最低920×600以及1180×780的文字/按钮对比度；小窗按420×620、最低300×280考虑可读性，测试compact两种状态。若不能运行目标程序，只做配置/素材检查并明确未实机预览，不伪造测试结论。保留功能状态文字与图标的辨识度，不用装饰英文代替真实歌曲数量。
【素材和交付限制】
只用静态 PNG/JPEG/WebP；保留透明底。单图≤12MB且≤1600万像素，包≤64项、总量≤40MB，theme.json≤128KB。素材路径为 assets/ 下的单层英文/数字/下划线/连字符文件名，扩展名小写 png/jpg/jpeg/webp，路径≤160字符。禁止远程地址、绝对路径、..、脚本、HTML、CSS、SVG、字体文件及账号数据。只使用我提供或有授权的素材；不要假设可以访问任何本机文件。主题不能更改播放器功能、窗口拖拽、按钮行为或连接状态颜色。

接下来是我的风格要求与素材：
