"""{TITLE} — 情感短片 (16:9 with film bars, 暖光 look).

Build:  studio {NAME} silent    motion only, estimated timings (look at this first)
        studio {NAME} check     voice + lint + stills
        studio {NAME} all       the finished video in out/

Light, air and a few lines of serif type; the voice slower than an explainer, long pauses,
no sound effects. Every line is on screen as type, so there are no subtitles. Each slide is a
scene: a light source that breathes, dust in the light, a line that drifts into focus (S.line).
Read playbooks/film.md first.
"""
from deck import *  # noqa: F401,F403

use_theme('nuanguang', watermark='')

LINE = 'position:absolute;left:0;width:1920px;text-align:center;opacity:0'


def line(lid, s, y, size=60, cls='line', extra=''):
    return f'<div id="{lid}" class="{cls}" style="{LINE};top:{y}px;font-size:{size}px;{extra}">{s}</div>'


def full(fid, css):
    return f'<div id="{fid}" class="sky" style="{css}"></div>'


SLIDES = []

s = Slide('f0', name='光', wm=False, sfx=None)
s.add(full('bg0', 'background:radial-gradient(1300px 900px at 30% 25%,#FFE2B2 0%,#F3D7B4 40%,#C9A58C 75%,#8C7468 100%)'),
      '<canvas id="cv0" class="abs" width="1920" height="1080" style="left:0;top:0"></canvas>',
      line('t0', '第一句，慢慢浮现。', 470, 64))
s.beat('第一句，慢慢浮现。', pause=1.2)
s.animate('''S => {
  S.el('bg0').style.filter = `brightness(${(1 - .08 * S.p(0, S.d, 'linear')).toFixed(3)})`;  // the light fades a little
  S.dust('cv0', 80, 3, [200, 120, 900, 820], '255,240,210', 10);                               // dust in the light
  S.line('t0', 'b0-0.3');
}''')
SLIDES.append(s)

s = Slide('f1', name='片尾', wm=False, sfx=None)
s.add(full('bg1', 'background:radial-gradient(1400px 900px at 50% 45%,#FBF3E8 0%,#F0E2D0 60%,#D8C2AC 100%)'),
      line('t1', '{TITLE}', 420, 96, extra='letter-spacing:.3em;padding-left:.3em'),
      line('t2', '下期见', 600, 34, cls='kicker', extra='letter-spacing:1em;padding-left:1em'))
s.beat('下期见。', pause=2.0)
s.animate('''S => {
  S.line('t1', .3, 1e9, 10);
  S.line('t2', S.word('b0', '下期', -.2), 1e9, 6);
}''')
SLIDES.append(s)

META = {
    'name': '{NAME}',
    'title': '{TITLE}',
    'voice': 'zh-CN-YunxiNeural',
    'subs': False,             # the type on screen is the text
    'rate': '+0%',             # slower than an explainer; long pauses come from beat(pause=)
    'lead': 1.0, 'tail': 0.8,
    'bgm': 'ambient',          # drumless and slow; still about 24 dB under the voice
    'sfx': False,
    'asof': '{DATE}',
    'notes': '',
}
