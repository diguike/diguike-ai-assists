---
name: video-studio-lite
description: 用代码做中文视频的轻量工作室（Windows / Mac 都能跑，配音用 Edge TTS，不需要本地模型），几种片种共用一套引擎：讲解/科普视频（手写字幻灯片，每句口播带出一个画面元素）、宣传片/发布片/预告（无口播，跟着音乐，一镜到底、元素衔接、大字连击、光标操作演示）、大字口播/文字快闪（竖屏大字动效）、原理动画（科技原理/流程拆解：连续场景、镜头移动、物体拆开流动变形，不翻页）、情感短片（品牌片/回忆：光影、浮尘、衬线大字、遮幅颗粒）。从选题、调研、写稿、独立事实核查、配音、读音检查，到逐帧渲染、配乐音效，出 MP4、字幕、封面、口播稿。8 套风格预设，配色、字体、动效、转场、镜头可以自由组合，还能拆解参考片的节奏和配色。用户说"做一期视频""做个视频讲讲 X""做个科普视频""做个宣传片/预告片/发布视频""给我的项目做个视频""做个口播短视频""文字快闪""做个竖屏短视频""照这个参考片的感觉做""改一下那期视频""重新出片""换个风格/配色/画幅""动画活泼一点""不要 PPT 感""做个科技原理动画""做个情感向/品牌短片"，或提到 video-studio、studio 命令时使用；改已有视频（~/VideoStudio/episodes/<名字>/episode.py）也走这里。
---

# video-studio-lite

用代码做视频：每页画面是 HTML，口播（或音乐节拍）驱动元素出场和动作，浏览器逐帧截图，ffmpeg 合成 MP4。同一套积木（入场、动作、镜头、转场、声音）按片种组合，不只是幻灯片。

## 运行环境

- 下文的 `studio ...` 都是 `uv run "<本 skill 目录>/studio.py" ...`。加载 skill 时会给出它的 base directory，路径带空格要加引号。Windows 上 Claude Code 用 Git Bash，写法一样。
- 前置只有 [uv](https://docs.astral.sh/uv/) 和联网。第一次运行时 uv 会自动装 Python 和依赖（1～2 分钟），之后秒开。
- ffmpeg 不用装：依赖里带了 imageio-ffmpeg；系统里装了 ffmpeg 就优先用系统的。
- 浏览器用系统里的 Edge 或 Chrome；两个都没有时运行 `studio install-browser`。
- 出问题先跑 `studio selftest`。配音报 `403` / `WSServerHandshakeError`：微软改了接口，edge-tts 版本旧了，把 `studio.py` 顶部依赖里的 `edge-tts==` 改成 PyPI 上的最新版再跑。
- 视频目录在 `~/VideoStudio/episodes/<名字>/`，环境变量 `STUDIO_HOME` 可以改。故意不放在"文档"文件夹里：Windows 上那里常被 OneDrive 同步，成千上万张帧文件会把同步拖垮。
- 每个视频一个目录：`episode.py`、`data/`、可选 `assets/` 是源文件；`work/`（缓存和中间文件）、`out/`（成片）随时能重新生成。
- Windows 上成片如果正在播放器里打开，重新出片可能因为文件被占用而写不进去，先关掉播放器。

## 先判断片种，读对应手册

| 片种 | 手册 | 新建 | 典型 |
|---|---|---|---|
| 讲解 / 科普 | `playbooks/explainer.md` | `studio new <名字> '标题' [--portrait]` | 横屏 5～15 分钟，每句口播带出一个元素 |
| 宣传片 / 发布片 / 预告 / 栏目片头 | `playbooks/promo.md` | `studio new <名字> '标题' --kind promo` | 10～60 秒，无口播，跟着音乐，衔接和镜头 |
| 大字口播 / 文字快闪 | `playbooks/talk.md` | `studio new <名字> '标题' --kind talk` | 竖屏 30 秒～3 分钟，大字就是字幕 |
| 原理动画 / 科技原理拆解 / 流程讲解 | `playbooks/mechanism.md` | `studio new <名字> '标题' --kind mechanism` | 横屏 3～6 分钟；几个连续场景，镜头移动，同一个东西被拆开、流动、变形，不翻页 |
| 情感短片 / 品牌片 / 回忆 | `playbooks/film.md` | `studio new <名字> '标题' --kind film` | 横屏遮幅 30～90 秒，语速放慢；光、浮尘、一行行浮现的衬线大字，不配字幕 |

拿不准就问用户一句是哪种。用户要「不像 PPT」「科技原理的动画拆解」「情感向」时，是要换**片种**（原理动画、情感短片），不是只换配色。手册里有这个片种的流程、硬规则和「经验」区，先读完再动手。所有片种共用：
- `references/atoms.md`：能用的入场、动作、镜头、转场、声音，以及组合配方；
- `references/style.md`：默认风格、口播习惯、风格预设和部件（配色 / 字体 / 动效）；
- `references/fact-check.md`：讲知识的视频出片前必须起独立核查 agent；
- `templates/`：各片种模板，`sample.py` 是风格样片（每个通用组件都有用法）。

## 命令

```bash
studio new <名字> ['完整标题'] [--portrait] [--style 预设] [--kind explainer|promo|talk|mechanism|film]
studio list                                    # 列出所有视频
studio styles                                  # 风格预设和部件
studio styles gallery                          # 样片在每套预设下的对照图 -> ~/VideoStudio/work/styles/gallery.jpg
studio styles silent <预设> [motion=...]       # 样片动起来看（无配音）
studio ref <视频.mp4>                          # 拆参考片：动静节奏、剪辑点、爆发段、配色建议、样张
studio <名字> stills       # 只出静态页，几秒钟；同时写 layout.txt（出界、重叠、溢出、压字幕、文字进避让区）
studio <名字> silent [s05 s07]  # 不配音，按估算时长出无声动画 + 节奏报告：看转场、镜头、节奏、哪页超过 6 秒没出新东西
studio <名字> check        # 配音 + 多音字检查 + 时间轴 + 静态页 + 节奏报告：出片前必跑
studio <名字> preview s05 s07   # 只渲染几页，带声音
studio <名字> all          # 整片：配音很快（联网），逐帧渲染最费时间，片子越长越久
studio <名字> freeze       # 发布后冻结 out/：以后再跑 check / all 都写到 work/out/，不覆盖已发布的成片和封面
studio selftest            # 环境自检
studio install-browser     # 系统里没有 Edge / Chrome 时，装一个 Chromium
```

## episode.py 怎么写（所有片种一样）

```python
from deck import *
use_theme()                                   # 风格：预设和部件见 style.md
s = Slide('s01', name='小标题', trans='fade')  # 换页方式见 atoms.md
s.add(title('t', '标题'), txt('a', '一行字', 300))
s.beat('这句话是字幕也是配音。', ['t', 'a', (pulse('a'), 1.2)])   # 元素入场 + 动作
s.beat(None, [], dur=0.6)                     # 没有口播的节拍：画面自己走 0.6 秒
SLIDES = [s]
META = {'name': ..., 'title': ..., 'voice': 'zh-CN-YunxiNeural'}  # voice=None：无口播（宣传片）
```

- 每个元素都要挂在某个节拍上（入场），没挂上的会报 `static element`；动作对象（`pulse()`、`go()`……）每个只能用一次。
- 颜色用 `T.primary / T.secondary / T.muted / T.danger`，图表网格和刻度用 `T.grid / T.zero / T.axis`，不要写死色值，换风格时才会跟着变。
- 画面上的数字从 `data/*.json` 读，不手填；来源写进 `META['notes']`。
- 配音只有 Edge TTS（微软在线语音，免费，要联网；偶尔断流，引擎会自动重试，合成结果缓存在 `work/tts/`）。默认男声 `zh-CN-YunxiNeural`、语速 `+22%`；女声可换 `zh-CN-XiaoxiaoNeural`。
- `META` 常用键：`voice`（Edge 音色 / `None`）、`rate`（语速，默认 `'+22%'`；单页放慢用 `Slide(..., rate='+12%')`）、`pron`（念法替换）、`subs`（底部字幕，默认有口播就开）、`bgm`（配乐）、`bpm`、`asof`、`notes`、`lead` / `tail`（换页后到第一句、最后一句到换页的空白，默认各 0.45 秒）、`crf`（x264 画质，默认 18，开了胶片颗粒的主题默认 22）。

## 通用流程

1. **判断片种**，读手册。
2. **定风格**：默认 `shouxie` 手写风，不用问。用户要别的风格、开新系列、或者给了参考片时：`studio styles gallery` / `studio ref 参考.mp4` 给用户看，提 2～3 个方案（每个一句话说清画面感觉），用户选定后写进 `use_theme()`。不要把上一个系列的风格默认带过来。
3. **写稿和分镜**（按手册），每改一轮 `stills`，涉及动效 `silent`，看 `layout.txt` 和 `rhythm.txt`。
4. **事实核查**：讲知识的内容必须起独立核查 agent（`references/fact-check.md`），不能跳。纯宣传片也要核对画面上的说法和数字。
5. **配音和检查** `check`（有口播时）：看 `lint.txt`，多音字和数字念法最容易错。
6. **出片** `preview` → `all`，自己抽帧看过再交付。告诉用户 `out/` 里的文件：`<名字>.mp4`、`<名字>.srt`、`口播稿.md`、封面 png、`<名字>_幻灯片.pdf`、`音轨/`（配音、音乐、音效分轨）。同时说明改了什么、核查改了哪些事实、发布前要复核哪些会变的数据。
7. **沉淀**（每次都做）：把用户对这一条的反馈、踩到的坑写进对应手册的「经验」区；新的事实坑写进 `references/fact-check.md`；好用的新组合写进 `references/atoms.md` 的「配方」；风格偏好写进 `references/style.md`。这些都是本 skill 目录里的文件，越用越顺手。

## 连续动画（原理动画、情感短片用）

一页可以挂一个**场景**：`s.animate('''S => {...}''')`，每一帧按时间算出画面，不依赖上一帧。
- 卡时刻：`S.word('b2', '配音')` 是说到这个词的那一刻，`S.p(时刻, 秒数)` 是从那一刻起的进度。
- 镜头：`S.cam(世界, [[时刻, x, y, 倍数, 时长], …])`。
- 动作：`S.soft` / `S.line` / `S.stroke` / `S.along` / `S.morph` / `S.dust`。
- 音效：场景动作要配小音效时，用 `s.sound('b2', 'tone', word='配音')` 放上去。
- 画图部件在 `engine/kit.py`；全部接口见 `references/atoms.md`「连续动画（场景）」。
- 主题还可以加胶片效果：`use_theme(grain=, vignette=, letterbox=, drift=)`。

## 混音参数（META 可覆盖）

背景音乐和音效都是代码现场合成的，没有版权问题。

| 键 | 默认 | 说明 |
|---|---|---|
| `bgm` | True | `True` 合成的 lo-fi 电钢琴（76 BPM）；`'ambient'` 慢、无鼓（情感短片）；`'glass'` ambient 加一层轻琶音（原理动画）；`'pulse'` 推进型（`bpm`，默认 112）；用户提供的音乐文件路径；`False` 不要 |
| `bgm_lu` | -21 | 有口播时音乐相对人声（说话时再压 4 dB，实测约 -24 LU）。音乐要"非常低"，用户没要求不要调大 |
| `music_lu` | -3 | 无口播时音乐相对音效的基准（音乐是主角） |
| `duck_db` | 4 | 说话时音乐压低多少 |
| `sfx` / `sfx_db` | True / 0 | 音效开关 / 整体增益 |

## 引擎和扩展

- 引擎在 `engine/`：`build.py` 流水线，`deck.py` 组件和动作，`runtime.js` 浏览器端动画，`theme.py` 主题，`audio.py` 音乐音效，`qa.py` 节奏报告和参考片拆解。改完跑 `studio selftest`，再找一条做过的视频跑 `stills` 看有没有走样。
- **加一个新片种**：在 `templates/` 加模板（用 `studio new --kind` 能建出来），在 `playbooks/` 加手册（什么时候用、结构、流程、硬规则、经验区），在上面的表里加一行。
- 缺积木时加到引擎（入场在 `engine/runtime.js` 的 `apply`，动作在 `applyCues`，Python 接口在 `engine/deck.py`），在 atoms.md 登记。
- 做不了：**真人出镜口播**（引擎只渲染自己画的画面，不能导入拍摄素材剪辑）；**产品界面复刻**没有现成组件，用 `prompt()`、`cursor()` 和手写的 HTML 拼。
