# dsh-xhs-cards

DeepSeek Harness（大肥鱼）插件：一句话把内容做成小红书 3:4 图文，还能串成竖屏小视频。也是一个学写插件的小例子，一个文件，三件事：

1. **提示词**：告诉 AI 有这个插件，什么时候用。
2. **路口**：标题超 20 字、开头是「家人们」这类套话，在工具执行前直接拦下，把理由退给 AI，让它改完再来。Skill 只能嘱咐，插件能硬拦，这是两者最大的差别。
3. **工具**：`xhs_cards` 出图，`xhs_video` 串成视频。

## 需要

- DeepSeek Harness 0.2.2-rc.1 及以上（0.2.x），Node 24.9 及以上，pnpm
- 本机有 Chrome 或 Edge（出图用）；要视频再装 ffmpeg

## 装和卸

```sh
dsh plugin --profile web add "github:diguike/diguike-ai-assists#path:plugins/dsh-xhs-cards"
dsh web
```

也可以把这个文件夹下载到本地，再 `dsh plugin --profile web add ./dsh-xhs-cards`。

然后跟它说：「把这篇文章做成小红书图文，再串成小视频」。图在工作目录的 `xhs-output/` 下。

不想要了：

```sh
dsh plugin --profile web remove dsh-xhs-cards
```

## 改规则

字数上限和禁用开头在 `cordis.patch.yml` 里，改完重启。配色有 `paper`、`sky`、`ink`，跟 AI 说就行。版式在 `index.js` 的 `page()` 里，可以直接让 AI 帮你改。

## 安全提醒

插件和 DeepSeek Harness 跑在同一个进程里，不受工作区沙箱限制，能碰到你能碰到的文件和密钥。这一点所有第三方插件都一样，包括这个。装之前先看代码，这个插件的代码就一个文件。

DeepSeek Harness 还在快速迭代，新版本可能让插件失效。
