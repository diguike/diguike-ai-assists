"""{TITLE} — 原理动画 (mechanism animation, 16:9, 瓷光 look).

Build:  studio {NAME} silent    motion only, estimated timings (look at this first)
        studio {NAME} check     voice + lint + timeline + stills
        studio {NAME} all       the finished video in out/

Not pages that replace each other: a few continuous scenes, each one world the camera travels
over, where the same objects keep changing (open up, flow, morph). Draw the objects here with
the kit (engine/kit.py); move them in a scene (s.animate) keyed to the words being said
(S.word). Read playbooks/mechanism.md first.
"""
import json  # noqa: F401  (data/*.json for numbers on screen)
from pathlib import Path

from deck import *  # noqa: F401,F403
from kit import bars, box, editor, glow, grid, speech_env, svg, text

use_theme('ciguang', watermark='', series='')

DATA = Path(__file__).resolve().parent / 'data'
SLIDES = []

# scene 1: a world wider than the screen; the camera starts close on the source and pulls back
s = Slide('s00', name='从一行开始', drift=0)
s.add('<div id="w0" class="abs" style="left:0;top:0;width:1920px;height:1080px">',
      glow('g0', 760, 520, 700), grid('grid0'),
      editor('ed', 160, 330, 820, 230, 'episode.py', ["s.beat('这句话，是配音，也是字幕。', ['c'])"], size=26),
      svg('rib', '<path id="r0" d="M840,420 C1000,420 1060,300 1180,300" fill="none" stroke="var(--secondary)" stroke-width="1.75"/>'
                 '<path id="r1" d="M840,420 C1000,420 1060,560 1180,560" fill="none" stroke="var(--primary)" stroke-width="1.75"/>'),
      box('voice', 1180, 250, 560, 100, svg('vw', bars('vb', 110, 50, 420, 56, speech_env(56, seed=3)), 560, 100)
          + '<div class="lbl coral" style="position:absolute;left:28px;top:36px;font-size:22px">配音</div>', style='opacity:0'),
      box('subs', 1180, 510, 560, 100, '<div class="lbl blue" style="position:absolute;left:28px;top:36px;font-size:22px">字幕</div>'
          '<div class="big" style="position:absolute;left:110px;top:30px;font-size:28px;font-weight:500">这句话，是配音，也是字幕。</div>',
          style='opacity:0'),
      '<canvas id="cv0" class="abs" width="1920" height="1080" style="left:0;top:0"></canvas>',
      '</div>')
s.beat('一切从一行代码开始。')
s.beat('这一句话，既是配音，也是字幕。', pause=0.6)
s.animate('''S => {
  S.cam(S.el('w0'), [[0, 570, 445, 1.5], ['b1', 960, 430, 1.0, 1.8]], 5);   // close on the code, then the whole picture
  S.soft('ed', S.p(0, .8));
  const g = S.ctx('cv0');                              // a cleared canvas for this frame
  [['r0', 'voice', '配音'], ['r1', 'subs', '字幕']].forEach(([rib, card, word]) => {
    const at = S.word('b1', word, -.3);
    S.stroke(S.el(rib), S.p(at, .9));                 // the ribbon draws when the word is heard
    S.soft(card, S.p(at + .6, .7));
    if (S.p(at, .9) >= 1 && !S.still) for (let i = 0; i < 5; i++) {  // signals keep running along it
      const u = (S.t * .45 + i / 5) % 1, q = S.along(S.el(rib), u);
      g.fillStyle = 'rgba(47,91,255,' + (.8 * Math.sin(Math.PI * u)).toFixed(3) + ')';
      g.beginPath(); g.arc(q.x, q.y, 4, 0, 6.2832); g.fill();
    }
  });
  for (let k = 0; k < 56; k++) S.scaleY('vb-' + k, S.clamp((S.t - S.word('b1', '配音', .4) - k * .015) / .3));
}''')
SLIDES.append(s)

# scene 2: one object changes state (here a waveform opens up at its commas)
FLAT = speech_env(80, seed=8)
OPEN = speech_env(80, seed=8, pauses=[(26, 32), (54, 60)])
s = Slide('s01', name='一个东西变了样', trans='fade', drift=0)
s.add(glow('g1', 960, 520, 700), grid('grid1'),
      box('wv', 260, 380, 1400, 200, svg('wvs', bars('wb', 40, 100, 1320, 120, [1.0] * 80), 1400, 200), style='opacity:0'),
      text('cap', '逗号处，停顿出来了', 960, 640, cls='big', size=44, center=True, style='opacity:0'))
s.beat('同一段声音，逗号处原来是连着的。')
s.beat('换一种做法，停顿就出来了。', pause=0.8)
s.animate(f'''S => {{
  S.soft('wv', S.p(0, .8));
  const k = S.p(S.word('b1', '停顿', -.4), 1.4);
  const A = {[round(v, 3) for v in FLAT]}, B = {[round(v, 3) for v in OPEN]};
  for (let i = 0; i < 80; i++) S.scaleY('wb-' + i, S.lerp(A[i], B[i], k));
  S.soft('cap', S.p(S.word('b1', '出来', 0), .8), 12);
}}''')
SLIDES.append(s)

META = {
    'name': '{NAME}',
    'title': '{TITLE}',
    'voice': 'zh-CN-YunxiNeural',
    'bgm': 'glass',            # drumless bed with a quiet arpeggio; still about 24 dB under the voice
    'asof': '{DATE}',
    'notes': '',
}
