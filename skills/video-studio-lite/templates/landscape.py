"""{TITLE} — episode spec (16:9).

Build:  studio {NAME} stills    layout only, no voice (seconds)
        studio {NAME} check     voice + polyphone lint + timeline + stills
        studio {NAME} all       the finished video in out/

Each Slide has beats; a beat is one narration line (also its subtitle) plus the
elements that appear while it is spoken. Element ids must be unique per episode.
Charts: bars() in engine/deck.py does labelled bars; anything else is an svg() you draw
(engine/kit.py has the drawing helpers). Keep chart data in data/*.json.
"""
import json  # noqa: F401  (data/*.json for charts)
from pathlib import Path

from deck import *  # noqa: F401,F403

# Look: the house style by default. Override anything here, before the slides, e.g.
#   use_theme(primary='#2BA471', font_scale=1.1, watermark='我的频道', series='')
# All knobs: references/style.md (主题参数). Colours for charts: T.primary, T.secondary ...
use_theme()

DATA = Path(__file__).resolve().parent / 'data'

SLIDES = []

# S00 cover — first line plays over the cover
s = Slide('s00', name='开场封面', bg='cover', rate='+15%')
s.add(cover(None, '指数基金是什么？<br>三分钟讲清楚'))  # None = the theme's series name
s.beat('很多朋友刚开始买基金，都会听到一个词：指数基金。')
SLIDES.append(s)

# S01 hook — mind map: label -> lines -> boxes -> explanations
s = Slide('s01', name='开场：两个疑问')
h = mindmap(s, 'h', '指数基金？', 170, 400, [
    ('听说', 250, ['巴菲特都推荐', '费率<em>很低</em>']),
    ('疑问', 560, ['到底买的是什么？', '为什么<em>长期</em>更稳？']),
], bx=560, bw=330, tx=980, tsize=50)
s.beat('听说巴菲特都推荐它，费率还很低；', ['h_lab'] + node(h, 0))
s.beat('但它到底买的是什么，为什么适合长期拿着？', node(h, 1))
s.beat('今天这期，就把指数基金一次讲清楚。')
SLIDES.append(s)

# S02 concept — title, typed lines, chips
s = Slide('s02', name='什么是指数')
s.add(title('c_t', '什么是指数？'))
s.add(txt('c_l1', '按规则挑出<em>一篮子股票</em>，算出一个数', 250, size=54))
s.add(chips('c_c', ['沪深300', '中证500', '标普500', '纳斯达克100'], 385))
s.add(txt('c_l2', '指数基金：<em>照着指数</em>买这一篮子股票', 545, size=54))
s.beat('先说什么是指数。', ['c_t'])
s.beat('指数就是按一套规则，挑出一篮子股票，再算出一个数，用来代表这一类股票的涨跌。', ['c_l1'])
s.beat('比如沪深300、中证500，还有美股的标普500、纳斯达克100。', [(f'c_c{i}', 0.1 + i * 0.4) for i in range(4)])
s.beat('指数基金，就是照着指数，把这一篮子股票买下来。', ['c_l2'])
SLIDES.append(s)

# S03 table — blue header, rows wipe in, highlighted row
s = Slide('s03', name='指数基金 vs 主动基金')
s.add(table('t', 260, 150, [300, 550, 550], ['', '指数基金', '主动基金'], [
    ['选股', '照着指数买', '基金经理挑'],
    ['费率', '<em>低</em>，一年约0.2%~0.6%', '较高，一年约1.2%~1.5%'],
    ['透明度', '持仓一目了然', '季报才公布'],
], hl_rows=(1,)))
s.beat('我们用一张表，对比一下指数基金和主动基金。', ['t_h'])
s.beat('指数基金照着指数买，主动基金靠基金经理挑；', ['t_r0'])
s.beat('指数基金的费率低得多，持仓也更透明。', ['t_r1', ('t_r2', 1.4)])
SLIDES.append(s)

# S04 flow — question, circles, arrows, dashed box
s = Slide('s04', name='钱是怎么流动的')
s.add(question('f_q', '钱是怎么流动的？'))
for i, (a1, a2, cx) in enumerate([('投资者', '申购', 420), ('基金', '照指数买', 960), ('股票', '一篮子', 1500)]):
    reg(f'f_c{i}', 'pop')
    s.add(f'<div id="f_c{i}" class="abs circle" data-a="pop" style="left:{cx - 130}px;top:265px">'
          f'<div>{a1}<br><small>{a2}</small></div></div>')
s.arrow('f_a0', 570, 395, 805, 395)
s.arrow('f_a1', 1110, 395, 1345, 395)
s.add(box('f_b', '指数调整成分股，基金跟着调', 560, 600, w=800, size=44, a='pop', cls='dash'))
s.beat('那钱是怎么流动的呢？', ['f_q'])
s.beat('我们申购基金，基金公司再照着指数，把一篮子股票买进来。', ['f_c0', 'f_a0', 'f_c1', 'f_a1', 'f_c2'])
s.beat('指数定期调整成分股，基金也跟着调。', ['f_b'])
SLIDES.append(s)

# S05 one-liner takeaway — slower rate, chime on the key line
s = Slide('s05', name='一句话总结', rate='+12%')
s.add(txt('z_l1', '指数基金：<em>不选股</em>，', 330, size=80))
s.add(txt('z_l2', '买下<em>一整篮子</em>。', 480, size=80, sfx='chime'))
s.beat('所以记住一句话：', pause=0.4)
s.beat('指数基金不选股，', ['z_l1'], pause=0.35)
s.beat('买下一整篮子。', ['z_l2'], pause=0.6)
SLIDES.append(s)

# S06 summary. Research and production notes stay in META['notes'], off screen.
s = Slide('s06', name='总结')
sm = mindmap(s, 'v', '总结', 170, 400, [
    ('是什么', 200, ['照着指数买一篮子股票']),
    ('好在哪', 400, ['费率低、透明、分散']),
    ('怎么用', 600, ['<em>长期</em>定投，别追涨杀跌']),
], bx=430, bw=300, tx=800, tsize=46)
s.beat('总结一下：', ['v_lab'])
s.beat('指数基金照着指数买一篮子股票，费率低、透明、分散，适合长期定投。', node(sm, 0) + node(sm, 1) + node(sm, 2))
SLIDES.append(s)

# S07 end card: the theme's end_card text, narrated with its outro lines
SLIDES.append(end_slide('s07'))

NOTES = """
## 关键数据与来源

| 数据 | 数值 | 来源 / 口径 |
|---|---|---|
| 示例 | 示例 | 示例 |

## 发布前请复核

- 每天会变的数据（限购、溢价、净值）发布当天再刷新一次。
"""

# cover images in out/: name -> cover_page(series or None, title html, size=...)
COVERS = {
    '横版封面': cover_page(None, '指数基金是什么？<br>三分钟讲清楚'),
    '竖版封面': cover_page(None, '指数基金<br>是什么？<br>三分钟讲清楚', size=(1080, 1440)),
}

META = {
    'name': '{NAME}',
    'title': '{TITLE}',
    'voice': 'zh-CN-YunxiNeural',  # Edge voice; 'zh-CN-XiaoxiaoNeural' for a female one
    'rate': '+22%',      # edge rate; per-slide rates are relative to it
    'pron': {},        # word -> spoken form, for readings the voice gets wrong (see lint.txt)
    'asof': '数据截至 {DATE}',
    'notes': NOTES,
    # 'bgm_lu': -21.0,  # music loudness vs voice, LU (more negative = quieter)
    # 'sfx_db': 0.0,    # effects trim, dB
}
