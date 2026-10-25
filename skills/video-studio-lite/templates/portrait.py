"""{TITLE} — episode spec (9:16 vertical short).

Build:  studio {NAME} stills    layout only, no voice (seconds)
        studio {NAME} check     voice + polyphone lint + timeline + stills
        studio {NAME} all       the finished video in out/

Canvas is 1080 x 1920. Keep content between y≈150 and y≈1350: subtitles sit at
about y=1490 and short-video apps cover the bottom fifth and the right edge
with their own buttons. Same helpers as the 16:9 template, laid out narrower.
"""
from deck import *  # noqa: F401,F403

# house style on a vertical canvas; any other theme knob can be added here too
use_theme(size=(1080, 1920))

SLIDES = []

# S00 cover
s = Slide('s00', name='开场封面', bg='cover', rate='+15%')
s.add(cover(None, '定投的<br>3个误区'))
s.beat('定投很简单，但这3个误区，很多人都踩过。')
SLIDES.append(s)

# S01 question + stacked boxes, each with a note under it
s = Slide('s01', name='三个误区')
s.add(question('q', '你踩过几个？', y=180, size=64))
points = [('① 涨了就停', '涨的时候也要投，成本才摊得低'), ('② 跌了就怕', '下跌正是便宜买份额的时候'),
          ('③ 金额太大', '定投的钱要能<em>长期</em>不动')]
for i, (head, note) in enumerate(points):
    y = 460 + i * 300
    s.add(box(f'p{i}', head, 140, y, w=800, size=60))
    s.add(txt(f'n{i}', note, y + 130, size=44, cls='gray2'))
s.beat('先看看，这3个误区你踩过几个？', ['q'])
s.beat('第一，涨了就停。', ['p0', 'n0'])
s.beat('第二，跌了就怕。', ['p1', 'n1'])
s.beat('第三，投的金额太大，拿不住。', ['p2', 'n2'])
SLIDES.append(s)

# S02 narrow table
s = Slide('s02', name='定投和一次买入')
s.add(title('t_t', '定投 vs 一次买入', y=220, size=64))
s.add(table('t', 80, 420, [260, 330, 330], ['', '定投', '一次买入'], [
    ['买点', '分很多次', '只有一次'],
    ['心态', '<em>不怕跌</em>', '怕买在高点'],
    ['适合', '工资族', '有大笔闲钱'],
], hl_rows=(1,), size=42))
s.beat('定投和一次买入有什么不一样？', ['t_t', 't_h'])
s.beat('定投分很多次买，不怕跌；一次买入只有一个买点，最怕买在高点。', ['t_r0', ('t_r1', 2.2)])
s.beat('所以定投更适合每个月有工资收入的人。', ['t_r2'])
SLIDES.append(s)

# S03 chips that wrap onto two rows, then a big line
s = Slide('s03', name='能定投什么')
s.add(title('c_t', '适合定投的基金', y=220, size=64))
s.add(chips('c', ['沪深300', '中证500', '标普500', '纳斯达克100', '红利指数'], 480))
s.add(txt('c_l', '波动大、长期向上的<em>宽基指数</em>', 860, size=54))
s.beat('哪些基金适合定投呢？', ['c_t'])
s.beat('像沪深300、中证500、标普500、纳斯达克100、红利指数，', [(f'c{i}', 0.1 + i * 0.5) for i in range(5)])
s.beat('这类波动大、长期向上的宽基指数，最适合定投。', ['c_l'])
SLIDES.append(s)

# S04 one-liner, slower
s = Slide('s04', name='一句话总结', rate='+12%')
s.add(txt('z1', '定投不看涨跌，', 640, size=88))
s.add(txt('z2', '<em>看时间</em>。', 800, size=88, sfx='chime'))
s.beat('所以记住一句话：', pause=0.4)
s.beat('定投不看涨跌，', ['z1'], pause=0.35)
s.beat('看时间。', ['z2'], pause=0.6)
SLIDES.append(s)

# S05 end card from the theme's brand (pass lines=[...] for different closing words)
SLIDES.append(end_slide('s05'))

COVERS = {
    '竖版封面': cover_page(None, '定投的<br>3个误区', size=(1080, 1920)),
    '3比4封面': cover_page(None, '定投的<br>3个误区', size=(1080, 1440)),
}

META = {
    'name': '{NAME}',
    'title': '{TITLE}',
    'voice': 'zh-CN-YunxiNeural',  # Edge voice; 'zh-CN-XiaoxiaoNeural' for a female one
    'rate': '+22%',      # edge rate; per-slide rates are relative to it
    'pron': {},          # word -> spoken form, for readings the voice gets wrong (see lint.txt)
    'asof': '{DATE}',
}
