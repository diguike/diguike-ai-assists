"""{TITLE} — style sampler: one short deck that exercises the theme-aware parts.

`studio styles gallery` builds it once per preset for the side-by-side sheet;
`studio styles silent <preset>` turns it into a voiceless motion preview. It is
also a working example of tag / hl / stat / bars / steps / cards / quote,
trans='magic' with carry, and a beat camera (cam=). Layout is relative to the
canvas, so it reads in 16:9 and 9:16.
"""
from deck import *  # noqa: F401,F403

use_theme()

W, H, P = T.W, T.H, T.portrait
CX = W // 2
SLIDES = []

s = Slide('s00', name='封面', bg='cover', rate='+15%')
s.add(cover(None, '复利：时间的魔法<br>一张图看懂', box_font=74))
s.beat('今天聊一个老生常谈、但很多人没算过的词：复利。')
SLIDES.append(s)

s = Slide('s01', name='提问')
y0 = round(H * 0.2)
s.add(tag('h_tag', '先问一个问题', y0))
s.add(title('h_t', '每年 8%，30 年后<br>变成多少？' if P else '每年 8%，30 年后变成多少？', y=y0 + 90, size=72))
s.add(txt('h_l1', f'答案是：差不多{hl("h_hl", "10 倍")}', y0 + (420 if P else 280), size=64))
s.add(chips('h_c', ['10 年 ≈ 2.2 倍', '20 年 ≈ 4.7 倍', '30 年 ≈ 10 倍'], y0 + (600 if P else 460)))
s.beat('先问一个问题：每年赚 8%，30 年后，本金会变成多少？', ['h_tag', 'h_t'])
s.beat('答案是差不多 10 倍。', ['h_l1', ('h_hl', 0.9)])
s.beat('10 年 2.2 倍，20 年 4.7 倍，30 年 10 倍。', [(f'h_c{i}', 0.2 + i * 0.9) for i in range(3)])
SLIDES.append(s)

s = Slide('s02', name='数字和柱子')
if P:
    s.add(stat('n_s', '<em>10.06</em><small>倍</small>', '每年 8%，持有 30 年', y=round(H * 0.16), size=170))
    bx, by, bw, bh = 140, round(H * 0.43), W - 280, round(H * 0.3)
else:
    s.add(stat('n_s', '<em>10.06</em><small>倍</small>', '每年 8%，持有 30 年', y=330, x=120, w=700, size=170))
    bx, by, bw, bh = 900, 190, 880, 600
b = bars(s, 'n_b', [('10 年', 2.16), ('20 年', 4.66), ('30 年', 10.06)], bx, by, bw, bh, unit='倍')
s.beat('1 块钱，每年 8%，30 年后是 10.06 块。', ['n_s'])
s.beat('前 10 年只多了一倍多，', [b['bars'][0], b['vals'][0]])
s.beat('后面越滚越快，最后 10 年多出来的，比前 20 年加起来还多。',
       [b['bars'][1], b['vals'][1], (b['bars'][2], 1.6), (b['vals'][2], 1.9)],
       cam=(bx + bw * 5 / 6, by + bh * 0.62, 1.4))
SLIDES.append(s)

s = Slide('s03', name='三条建议', trans='magic', carry={'n_s': 'k_s'})
if P:
    s.add(stat('k_s', '<em>10.06</em><small>倍</small>', '', y=round(H * 0.1), size=110, a=None))
    s.add(steps('k_p', ['越早开始越好', '中途别打断', ('收益率差一点，结果差很多', '8% 和 6%，30 年差约 1.75 倍')],
                110, round(H * 0.3), gap=220, size=54))
else:
    s.add(stat('k_s', '<em>10.06</em><small>倍</small>', '', y=130, size=110, a=None))
    s.add(steps('k_p', ['越早开始越好', '中途别打断', ('收益率差一点，结果差很多', '8% 和 6%，30 年差约 1.75 倍')],
                560, 360, gap=160, size=56))
s.beat('想吃到这 10 倍，记住三条。', [])
s.beat('越早开始越好；中途别打断；', ['k_p0', ('k_p1', 1.5)])
s.beat('收益率差一点，30 年后结果差很多。', ['k_p2'])
SLIDES.append(s)

s = Slide('s04', name='72 法则')
s.add(title('r_t', '一个心算技巧：72 法则', y=round(H * (0.12 if P else 0.17)), size=68))
s.add(cards('r_c', [('72 法则', '72 ÷ 年化收益率<br>≈ 翻倍要几年'), ('举个例子', '8% 的收益<br>约 9 年翻一倍'),
                    ('反过来用', '想 6 年翻倍<br>年化要约 12%')], round(H * (0.26 if P else 0.37)),
            h=round(H * 0.17) if P else 300, size=50 if P else 46))
s.beat('再教一个心算技巧：72 法则。', ['r_t'])
s.beat('用 72 除以年化收益率，就是翻倍大概要几年。', ['r_c0'])
s.beat('8% 大约 9 年翻倍；反过来，想 6 年翻倍，年化要 12% 左右。', ['r_c1', ('r_c2', 2.2)])
SLIDES.append(s)

s = Slide('s05', name='金句')
s.add(quote('q_q', '人生就像滚雪球，<br>重要的是找到很湿的雪和很长的坡。', '巴菲特', y=round(H * (0.3 if P else 0.33)),
            size=62 if P else 64))
s.beat('巴菲特说过：人生就像滚雪球，重要的是找到很湿的雪和很长的坡。', ['q_q'], pause=0.6)
SLIDES.append(s)

SLIDES.append(end_slide('s06'))

COVERS = {}
META = {
    'name': '{NAME}',
    'title': '{TITLE}',
    'voice': 'zh-CN-YunxiNeural',
    'asof': '样片，数字按年化 8% 复利计算',
    'notes': '',
}
