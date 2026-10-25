"""{TITLE} — 大字口播 / kinetic talk (9:16, an Edge voice, big words instead of subtitles).

Build:  studio {NAME} silent    motion only, seconds
        studio {NAME} check     voice + polyphone lint + timeline + stills
        studio {NAME} all       the finished video in out/

The words on screen are the captions: each beat shows the key phrase of what is
being said, big, and the important word gets a hit (punch / glow / highlighter).
META subs=False turns the usual subtitle line off. Read playbooks/talk.md.

Atoms used here: kinetic() words and lines, tag(), hl(), strike(), stat() counting
up, focus(), punch(), shake() on the conclusion, a silent beat (text=None, dur=)
to let the answer land, a camera push (cam=).
"""
from deck import *  # noqa: F401,F403

# 大字口播 reads best in heavy type; colours stay the house style unless the series has its own
use_theme(size=(1080, 1920), typeset='heavy', motion='snappy')

W, H = T.W, T.H
SLIDES = []

# S00 hook: a question in big words
s = Slide('s00', name='提问')
s.add(tag('h_tag', '理财小常识', 420, size=40))
s.add(kinetic('h_q', '你的钱|多久能|翻一倍？', 550, size=130, mode='words', style='line-height:1.25;white-space:normal;padding:0 80px'))
s.add(txt('h_sub', f'有个公式，{hl("h_hl", "三秒")}就能算出来', 1100, size=60))
s.beat('你的钱，多久能翻一倍？', ['h_tag', 'h_q'])
s.beat('有个公式，三秒就能算出来。', ['h_sub', ('h_hl', 0.9)])
SLIDES.append(s)

# S01 the rule, stamped
s = Slide('s01', name='72法则', trans='push')
s.add(title('r_t', '72 法则', y=480, size=170, a='zoom'))
s.add(kinetic('r_f', '72 ÷ 年化收益率<br>≈ 翻倍要几年', 840, size=78, mode='lines'))
s.beat('它叫72法则。', ['r_t', (shake(), 0.25)])
s.beat('用72除以年化收益率，就是翻倍大概要几年。', ['r_f'])
SLIDES.append(s)

# S02 two numbers, one after the other; the second takes the focus
s = Slide('s02', name='算两笔', trans=('iris', W / 2, 570))  # opens from where the rule was stamped
s.add(stat('n8', '<em>9</em><small>年</small>', '年化 8%', y=430, size=200))
s.add(stat('n6', '<em>12</em><small>年</small>', '年化 6%', y=950, size=200))
s.beat('比如年化8%，72除以8，大约9年翻一倍。', ['n8'])
s.beat('年化6%，大约要12年。', ['n6', (focus('n6'), 0.8)], tts='年化6%，大约要十二年。')  # '12年' alone reads like a year
SLIDES.append(s)

# S03 the point: two percentage points are three years
s = Slide('s03', name='差两个点', trans=('through', 'n6'))  # into the 12 years
s.add(txt('d_l', f'只差 2%，{strike("d_st", "无所谓？")}', 540, size=76))
s.add(kinetic('d_k', '多等|<em>3 年</em>', 820, size=190, mode='pops'))
s.beat('只差两个百分点，无所谓吗？', ['d_l', ('d_st', 1.6)])
s.beat(None, [], dur=0.6)  # a breath before the answer
s.beat('同样翻一倍，要多等三年。', ['d_k', (punch('d_k'), 1.2)], cam=(W / 2, 980, 1.25))
SLIDES.append(s)

# S04 the takeaway, slower
s = Slide('s04', name='记住', rate='+12%', trans='zoom')
s.add(kinetic('z_k', '记住：|72 ÷ 收益率', 760, size=120, mode='words', style='white-space:normal;line-height:1.3;padding:0 80px'))
s.beat('所以记住：72除以收益率。', ['z_k', (glow('z_k', hold=True), 1.5)], pause=0.6)
SLIDES.append(s)

SLIDES.append(end_slide('s05'))

COVERS = {'竖版封面': cover_page(None, '钱多久能<br>翻一倍？', size=(1080, 1440), box_font=90)}
META = {
    'name': '{NAME}',
    'title': '{TITLE}',
    'voice': 'zh-CN-YunxiNeural',
    'subs': False,        # the big words are the captions
    'asof': '{DATE}',
    'notes': '72 法则是近似：年化 6%–10% 时最准，收益率越高或越低误差越大。',
}
