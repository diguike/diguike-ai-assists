# diguike-ai-assists

递归客的 AI 工具箱：自己日常在用、整理成可以公开的 skill 和小工具。每个都尽量轻：装好就能用，Windows 和 Mac 都能跑，不依赖本地大模型。

## Skills

| 名字 | 做什么 |
|---|---|
| [video-studio-lite](skills/video-studio-lite/) | 用代码做中文视频：讲解/科普、宣传片、大字口播、原理动画、情感短片。Edge 在线配音，代码合成配乐音效，出 MP4、字幕、封面、口播稿 |

## Plugins

| 名字 | 做什么 |
|---|---|
| [dsh-xhs-cards](plugins/dsh-xhs-cards/) | DeepSeek Harness 插件：一句话做小红书 3:4 图文，还能串成竖屏小视频；标题超字数、开头是套话会被硬拦下，让 AI 自己改。一个文件，也是学写插件的例子 |

## 怎么装一个 skill

skill 是给 [Claude Code](https://claude.com/claude-code) 用的文件夹。把 `skills/` 下对应的文件夹复制到 `~/.claude/skills/`（Windows 是 `C:\Users\<你的用户名>\.claude\skills\`），再按它自己的 README 做一遍自检。

## 授权

代码按 [MIT](LICENSE)。各 skill 里随附的第三方素材（比如字体）按各自的许可证，许可证文件和素材放在一起。
