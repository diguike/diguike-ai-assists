# video-studio-lite

用代码做中文视频的 Claude Code skill：每页画面是 HTML，口播驱动元素出场和动作，浏览器逐帧截图，合成 MP4，同时出字幕、封面、口播稿和分轨音频。能做讲解/科普、宣传片、大字口播、原理动画、情感短片。

- Windows、Mac 都能跑；不需要本地大模型，也不需要显卡。
- 配音用微软 Edge 的在线语音（免费，要联网），默认男声云希。
- 背景音乐和音效是代码现场合成的，没有版权问题。
- 自带 8 套风格（默认手写风），配色、字体、动效可以自由组合。

## 安装

只需要两样：[Claude Code](https://claude.com/claude-code) 和 [uv](https://docs.astral.sh/uv/)。ffmpeg 不用装（依赖里带了一个），浏览器用系统自带的 Edge 或 Chrome。

**1. 装 uv**

Windows（PowerShell）：

```powershell
powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
```

Mac：

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```

**2. 把这个文件夹放进 Claude Code 的 skills 目录**

把 `video-studio-lite` 整个文件夹复制到：

- Windows：`C:\Users\<你的用户名>\.claude\skills\video-studio-lite`
- Mac：`~/.claude/skills/video-studio-lite`

**3. 自检**

```bash
uv run ~/.claude/skills/video-studio-lite/studio.py selftest
```

第一次运行时 uv 会自动下载 Python 和依赖，需要一两分钟。最后看到 `selftest ok` 就装好了。Windows 上这条命令在 Git Bash 里运行（Claude Code 在 Windows 上用的也是 Git Bash）；在 PowerShell 里把 `~` 换成 `$HOME`。

## 用法

在 Claude Code 里直接说，比如：

- 「做一期视频，讲讲复利是什么，5 分钟，横屏」
- 「给我的项目做个 30 秒宣传片」（附上项目地址或介绍）
- 「做个竖屏大字口播：钱多久能翻一倍」

它会按 `SKILL.md` 的流程走：定片种和风格、写稿分镜、起一个独立的事实核查 agent、配音、检查读音、渲染出片。视频在 `~/VideoStudio/episodes/<名字>/out/` 里（Windows 上是 `C:\Users\<你>\VideoStudio\...`）。

也可以手动跑命令，`studio` 就是 `uv run <skill 目录>/studio.py`：

```bash
studio new 复利 '复利：时间的魔法'    # 新建一期（横屏讲解）
studio 复利 stills                    # 只出静态页，几秒钟
studio 复利 check                     # 配音 + 读音检查 + 时间轴
studio 复利 all                       # 出整片
studio styles gallery                 # 8 套风格的对照图
```

## 常见问题

- **配音报 403 / WSServerHandshakeError**：微软改了接口。把 `studio.py` 顶部依赖里的 `edge-tts==` 改成 [PyPI](https://pypi.org/project/edge-tts/) 上的最新版再跑。
- **没有 Edge 也没有 Chrome**：`studio install-browser` 装一个 Chromium。
- **视频目录想换地方**：设环境变量 `STUDIO_HOME`。默认故意不放在「文档」里，因为 Windows 上那里常被 OneDrive 同步，渲染时成千上万张帧文件会拖垮同步。
- **两台电脑出的图字形略有不同**：苹方、宋体是 Mac 的系统字体，Windows 上会换成微软雅黑、宋体。手写风用的霞鹜文楷随包带着，两边一样。

## 授权

代码按仓库根目录的 MIT 许可证。`assets/fonts/` 里的霞鹜文楷、得意黑按各自的 SIL Open Font License（许可证文件在同一目录）。
