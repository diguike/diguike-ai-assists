# 讲解视频（科普 / 知识讲解）

主力片种：横屏 5～15 分钟（竖屏短版 1～3 分钟），Edge TTS 口播，每句口播带出一个画面元素，像对着 Keynote 边讲边点。默认风格 `shouxie`（手写）。

- 模板：`studio new <名字> '标题'`（横屏）或加 `--portrait`（竖屏）。
- 参考写法：`templates/landscape.py`、`templates/portrait.py`，以及 `templates/sample.py`（每个通用组件都有用法）。写新视频前先读一遍。
- 风格、口播习惯：`references/style.md`。能用的动作和配方：`references/atoms.md`。

## 1. 定选题和结构

**定风格**：默认用 `shouxie`，不用问。用户要别的风格、或者开新系列时，按 style.md「换风格」：跑 `studio styles gallery`（需要时加 `styles silent`）给用户看，提 2～3 个方案，每个一句话说清画面感觉，用户选定后写进 `use_theme()`。不要把上一个系列的风格默认带过来。用户有自己的频道名，就在 `use_theme()` 里写 `watermark`、`series`、`end_card`、`outro`。

然后定 15～30 页（竖屏短视频 5～10 页）的结构，用户点名要讲的问题每个都要有一页正面回答。常用骨架：
- 现象或痛点开场
- 是什么
- 历史 / 现状
- 怎么做
- 机制（为什么）
- 风险算账
- 3～4 条建议
- 总结一句话
- 片尾

## 2. 抓数据

数据从公开来源取，存到 `~/VideoStudio/episodes/<名字>/data/*.json`，图表和画面上的数字都从 json 读，不手填。每天会变的数据要记下抓取日期，来源写进 `META['notes']`。

## 3. 写稿和分镜

`studio new <名字>`，然后改 `episode.py`（通用写法见 SKILL.md「episode.py 怎么写」）：

- **页面**：`Slide(id, name=..., bg='white'|'cover', rate=, trans=, carry=)`。`name` 是口播稿里的小标题；`rate` 是单页语速，比如总结页 `'+12%'`。
- **组件**（`engine/deck.py`）：
  - 基础组件：`txt / box / title / question / chips / mindmap+node / table / img / cover / mark / line / arrow / cross / reg`；
  - 手写批注和手画标记：`hand / prompt / circle / underline / check / curve_arrow`；
  - 通用组件：`tag / hl / strike / stat / bars / steps / cards / quote`；
  - 片尾：`end_slide()`（默认「下期见」，`end_card` / `outro` 可换），也可以自己写一页收尾。
- **讲解里好用的动作**（配方见 atoms.md）：讲到一条时 `focus()` 其余变暗；结论 `zoom` 入场或 `punch()`；看图表细节时 `cam=` 推近再 `cam=0` 拉回；前后两页有联系用 `magic` 把元素接过去。一期里换页方式别全一样，也别每页都花哨。
- **音效**：默认按元素类型自动配。弹出→pop，框→tone，柱子→上行琶音，表格行→wipe，高亮框→swish，红叉→wrong，换页→whoosh。单个元素可以用 `sfx='chime'`（关键结论）、`'wrong'`（亏损）、`None`（静音）覆盖。
- **封面**：`COVERS = {'横版封面': cover_page(...), '竖版封面': cover_page(..., size=(1080, 1440))}`。
- **META**：`voice`（默认 `'zh-CN-YunxiNeural'` 云希，可换 `'zh-CN-XiaoxiaoNeural'` 等 Edge 音色）、`rate`（默认 `'+22%'`）、`pron`（`{词: 念法}`）、`asof`（数据日期）、`notes`（口播稿末尾的数据来源和发布前复核事项）。

每改一轮就跑 `studio <名字> stills`，看 `work/contact.jpg` 和 `work/layout.txt`：逐页查有没有重叠、截断、出界，以及字幕区是否被占（横屏底部约 100px，竖屏底部 20%）。用了转场、镜头或换了动效，先跑 `studio <名字> silent` 看动起来的样子。

## 4. 事实核查（必做，不能跳）

稿子写完、出片之前，按 `references/fact-check.md` 起一个**独立的**核查 agent 审稿，可以后台跑，同时做下一步。结论回来后逐条改（字幕和画面一起改），新发现的坑补进清单。

## 5. 配音和检查：`studio <名字> check`

每页把整段文本交给 Edge TTS 合成（需要联网），再按逐词时间戳把音频切到每个 beat 上。语速用 `rate`，默认 `+22%`。`work/lint.txt` 查两类问题：

- **多音字**（`MISMATCH`）：在 `META['pron']` 或 `engine/pron.py` 的 `LEXICON` 里加替换，比如 `成分股→成份股`。`unsure` 的去听一下。
- **断词**（`GROUPING`）：改稿换个说法，比如"博时标普500"改成"博时的标普500"。
- **数字念法**：lint 不一定抓得到，自己扫一遍稿子里的数字。单独的"12年"会被当成年份念成"一二年"，写 `tts='十二年'`；英文名写小写（`tts='video studio'`），否则可能被逐个字母念。
- 一个词反复念不对，别硬改念法，换个说法绕开。

## 6. 出片和质检

- 先用 `preview` 看一两段，再跑 `all`。
- 发布以后跑 `studio <名字> freeze`：`out/` 冻结，之后改稿重跑都写到 `work/out/`，已发布的成片、封面、字幕不会被覆盖。
- 成片在 `out/`：mp4、srt、口播稿.md、幻灯片 PDF、封面，以及 `音轨/`（配音、背景音乐、音效三轨分开，方便在剪辑软件里调平衡）。交付时告诉用户 mp4 的路径。
- 质检：从成片按句子时间抽帧拼图，看动画和字幕是否同步；看 `audio ok` 那行的电平：人声 -16 LUFS，背景音乐比人声低约 24 dB；看 `work/rhythm.txt`（会列出一页里超过 6 秒没有新元素的地方：念到哪行出哪行，或者拆页）。

## 经验（每做完一条，把用户反馈和踩到的坑记在这里）

- 背景音乐要很低，比人声低约 24 dB；没征得用户同意不要调大。
- 七个四字术语连着念，耳朵记不住。清单类内容放在画面上依次出现，口播只说"一共七步，都在这张图上"。
- 只 cut 换页会被节奏报告提示；有关联的两页用 `('through', id)` 推进上一页的关键词、`('iris', x, y)` 从流程图的那一步展开，读起来像从上一页长出来。
- 讲自己的工具或产品时，核查 agent 常能挑出十几处说过头的话（"同一套代码生成""每秒截 30 张图"这类），要逐条改，坑补进 fact-check.md。
- 自画的复杂插画（人物、凭证、场景）常常不好看、难辨认。优先用简单的折线图、柱状图、表格；复杂场景找现成图标或图片，核实来源和授权后用 `img`。更多动效、更短时长不等于改进，先检查含义和可辨认性。
- 提升观感先收紧讲述主线，再加图。用一个物件贯穿几页，每个动作对应正在说的原因；中途留一个判断题和思考停顿，结尾只留几条核对问题，少连续堆术语。缩短口播不删必要假设，不靠提高语速实现。
- 竖屏正文左右各留 144px（短视频平台全屏播放会裁掉两边约 100–110px）；画面跟着嘴走，一个框里的几行念到哪行出哪行，一页超过 6 秒没有新元素就补或拆页；`stills` 会改写 `out/` 里的封面，已发布的视频先 `freeze`。
