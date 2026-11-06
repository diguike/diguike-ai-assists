// dsh-xhs-cards：一个文件，三件事。
//   1. 提示词：告诉 AI 有这个插件，什么时候用
//   2. 路口：标题超字数、开头是套话，在工具执行前直接拦下，让 AI 自己改
//   3. 工具：xhs_cards 出 3:4 图文，xhs_video 把图串成竖屏小视频
// 卸载时，这三样注册的东西都会自动撤销。
import { execFile } from 'node:child_process'
import { existsSync } from 'node:fs'
import { mkdir, mkdtemp, rm, writeFile } from 'node:fs/promises'
import { tmpdir } from 'node:os'
import { join, resolve } from 'node:path'
import { pathToFileURL } from 'node:url'
import { promisify } from 'node:util'
import { defineTool } from '@deepseek-ai/dsh-tools'

const run = promisify(execFile)

export const name = 'xhs-cards'
export const inject = ['tools', 'systemPrompt', 'workingDirectory']

const DEFAULTS = { maxTitle: 20, maxCardText: 120, bannedOpeners: ['家人们', '姐妹们', '在当今', '随着科技'] }

const THEMES = {
  paper: { bg: '#FFFDF8', ink: '#1F1D1A', accent: '#FF6A2B', soft: '#FFF0E6', muted: '#8A8378' },
  sky: { bg: '#EEF5FF', ink: '#14233C', accent: '#2F7BEF', soft: '#FFFFFF', muted: '#6C7D96' },
  ink: { bg: '#1B1D22', ink: '#F5F2EA', accent: '#FFB454', soft: '#2A2D34', muted: '#9B9EA6' },
}

const chars = text => [...String(text)].length
const esc = text => String(text).replace(/[&<>"]/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' })[c])

/** 把规则写在一个函数里：路口用它拦，返回的话 AI 能看到，看到就知道怎么改。 */
function checkNote(args, rules) {
  const problems = []
  const title = String(args?.title ?? '')
  if (chars(title) > rules.maxTitle) {
    problems.push(`标题「${title}」有 ${chars(title)} 个字，上限 ${rules.maxTitle}，请压缩后重新调用`)
  }
  const cards = Array.isArray(args?.cards) ? args.cards : []
  const first = String(cards[0]?.body ?? '')
  const opener = rules.bannedOpeners.find(word => first.startsWith(word) || title.startsWith(word))
  if (opener) problems.push(`不要用「${opener}」开头，直接说读者能得到什么`)
  cards.forEach((card, i) => {
    const size = chars(card?.body ?? '')
    if (size > rules.maxCardText) problems.push(`第 ${i + 1} 张内页 ${size} 个字，上限 ${rules.maxCardText}，请拆开或删减`)
  })
  return problems
}

function findChrome() {
  const candidates = [
    process.env.CHROME_PATH,
    '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',
    '/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge',
    'C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe',
    'C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe',
    '/usr/bin/google-chrome',
    '/usr/bin/chromium',
  ]
  return candidates.find(path => path && existsSync(path))
}

const page = (theme, inner) => `<!doctype html><meta charset="utf-8"><style>
*{box-sizing:border-box;margin:0}html,body{width:1080px;height:1440px;overflow:hidden}
body{background:${theme.bg};color:${theme.ink};font-family:-apple-system,"PingFang SC","Microsoft YaHei","Noto Sans CJK SC",sans-serif;padding:96px 88px;display:flex;flex-direction:column;position:relative}
body::before{content:"";position:absolute;right:-140px;top:-140px;width:520px;height:520px;border-radius:50%;background:${theme.soft}}
body>*{position:relative}
.tag{align-self:flex-start;background:${theme.accent};color:#fff;font-size:42px;font-weight:800;padding:14px 32px;border-radius:18px}
h1{font-size:150px;line-height:1.16;font-weight:900;margin:auto 0}
h1 em{font-style:normal;color:${theme.accent}}
h2{font-size:92px;line-height:1.22;font-weight:900;margin-top:40px}
h2::after{content:"";display:block;width:120px;height:14px;border-radius:7px;background:${theme.accent};margin-top:44px}
p{line-height:1.62;margin:auto 0;white-space:pre-wrap;font-weight:500}
.box{background:${theme.soft};border-left:14px solid ${theme.accent};border-radius:24px;padding:44px 48px;font-size:54px;line-height:1.5;font-weight:700}
.foot{display:flex;justify-content:flex-end;color:${theme.muted};font-size:40px;font-weight:700}
</style>${inner}`

const bodySize = text => (chars(text) <= 45 ? 82 : chars(text) <= 80 ? 68 : 56)

/** 标题最后一个逗号后面的部分用强调色，没有逗号就全黑。 */
function titleHtml(title) {
  const cut = Math.max(title.lastIndexOf('，'), title.lastIndexOf('：'))
  return cut < 0 ? esc(title) : `${esc(title.slice(0, cut + 1))}<em>${esc(title.slice(cut + 1))}</em>`
}

const coverHtml = (args, theme) => page(theme, `
${args.tag ? `<div class="tag">${esc(args.tag)}</div>` : ''}<h1>${titleHtml(args.title)}</h1>
${args.subtitle ? `<div class="box">${esc(args.subtitle)}</div>` : ''}`)

const cardHtml = (card, i, total, theme) => page(theme, `
<h2>${esc(card.heading ?? '')}</h2><p style="font-size:${bodySize(card.body ?? '')}px">${esc(card.body ?? '')}</p>
<div class="foot">${i + 1} / ${total}</div>`)

async function screenshot(chrome, html, outPath, signal) {
  const dir = await mkdtemp(join(tmpdir(), 'xhs-cards-'))
  try {
    const file = join(dir, 'card.html')
    await writeFile(file, html)
    await run(chrome, [
      '--headless=new', '--disable-gpu', '--hide-scrollbars', '--force-device-scale-factor=1',
      `--user-data-dir=${join(dir, 'profile')}`, '--window-size=1080,1440',
      `--screenshot=${outPath}`, pathToFileURL(file).href,
    ], { signal, timeout: 60_000 })
  } finally {
    await rm(dir, { recursive: true, force: true })
  }
}

export function apply(ctx, config = {}) {
  const rules = { ...DEFAULTS, ...config }

  // 第一件事：提示词。AI 每次组装提示词时都会看到这段。
  ctx.systemPrompt.section({
    name: 'xhs-cards',
    order: 900,
    interpolate: false,
    text: `用户要做小红书图文时，调用 xhs_cards。标题不超过 ${rules.maxTitle} 字，第一张内页直接说读者能得到什么。用户还要视频时，把生成的图片路径交给 xhs_video。`,
  })

  // 第二件事：蹲在「工具执行前」这个路口。不合规就拒绝，理由会原样交给 AI，AI 改完再来一次。
  ctx.on('tools/pre-execute', async (exec, next) => {
    if (exec.name !== 'xhs_cards') return next()
    const problems = checkNote(exec.arguments, rules)
    if (problems.length > 0) return { kind: 'deny', reason: problems.join('；') }
    return next()
  })

  // 第三件事：工具，真正出图。
  ctx.tools.register(defineTool({
    name: 'xhs_cards',
    description: '把一篇笔记做成小红书 3:4 图文：一张封面加若干内页，输出 PNG。',
    parameters: {
      title: { type: 'string', required: true, description: '封面标题' },
      subtitle: { type: 'string', description: '封面底部一句话' },
      tag: { type: 'string', description: '封面顶部的小标签' },
      theme: { type: 'string', description: '配色：paper（默认）、sky、ink' },
      cards: {
        type: 'array',
        required: true,
        description: '内页',
        items: {
          type: 'object',
          additionalProperties: false,
          properties: {
            heading: { type: 'string', required: true, description: '内页小标题' },
            body: { type: 'string', required: true, description: '内页正文' },
          },
        },
      },
    },
    output: {
      schema: { type: 'object', additionalProperties: false, properties: { files: { type: 'array', required: true, items: { type: 'string' } } } },
      render: (_args, value) => [{ type: 'text', text: `已生成 ${value.files.length} 张：\n${value.files.join('\n')}` }],
    },
    async execute(args, exec) {
      const chrome = findChrome()
      if (!chrome) throw new Error('没找到 Chrome 或 Edge。装一个，或者设置环境变量 CHROME_PATH。')
      const cwd = exec.agent === undefined ? process.cwd() : await ctx.workingDirectory.ensure(exec.agent, exec.signal)
      const outDir = resolve(cwd, 'xhs-output', new Date().toISOString().replace(/[:.]/g, '-'))
      await mkdir(outDir, { recursive: true })
      const theme = THEMES[args.theme] ?? THEMES.paper
      const pages = [coverHtml(args, theme), ...args.cards.map((card, i) => cardHtml(card, i, args.cards.length, theme))]
      const files = []
      for (const [i, html] of pages.entries()) {
        const file = join(outDir, `${String(i).padStart(2, '0')}.png`)
        await screenshot(chrome, html, file, exec.signal)
        files.push(file)
      }
      return { files }
    },
  }))

  ctx.tools.register(defineTool({
    name: 'xhs_video',
    description: '把 xhs_cards 生成的图片串成 3:4 竖屏小视频（MP4，无配音），需要本机有 ffmpeg。',
    parameters: {
      images: { type: 'array', required: true, description: '图片路径，按播放顺序', items: { type: 'string' } },
      seconds: { type: 'number', description: '每张停留几秒，默认 3' },
    },
    output: {
      schema: { type: 'object', additionalProperties: false, properties: { file: { type: 'string', required: true } } },
      render: (_args, value) => [{ type: 'text', text: `视频已生成：${value.file}` }],
    },
    async execute(args, exec) {
      if (args.images.length === 0) throw new Error('images 不能为空')
      const hold = args.seconds ?? 3
      const fade = 0.4
      const inputs = args.images.flatMap(path => ['-loop', '1', '-t', String(hold + fade), '-i', path])
      let filter = ''
      let last = '0:v'
      for (let i = 1; i < args.images.length; i++) {
        filter += `[${last}][${i}:v]xfade=transition=fade:duration=${fade}:offset=${(hold * i).toFixed(2)}[v${i}];`
        last = `v${i}`
      }
      const out = resolve(args.images[0], '..', 'note.mp4')
      const map = args.images.length > 1 ? ['-filter_complex', filter.slice(0, -1), '-map', `[${last}]`] : []
      await run('ffmpeg', ['-y', ...inputs, ...map, '-pix_fmt', 'yuv420p', '-r', '30', out], { signal: exec.signal, timeout: 180_000 })
      return { file: out }
    },
  }))
}
