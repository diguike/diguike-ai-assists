"""{TITLE} — promo cut (16:9, no narration, cut to music).

Build:  studio {NAME} silent    motion only, seconds (no music)
        studio {NAME} all       the film with music and effects in out/

A promo is timed by the music, not a voice: every beat has dur= in beats / bars of
BPM, so cuts land on the music's bars. Read playbooks/promo.md first; this
template is one concept ("one sentence becomes a video": a single take across a
board, then hits, then the lockup) — write your own concept, don't reuse its beats.

Atoms used here: world=/cam= one take with a whip and a pull-back, kinetic() letters
and lines, prompt() typing, cursor()+go()+click(), shake() on the landing, glow(),
trans=('through', id) into the next scene, s.staccato() hard-cut words, punch().
"""
from deck import *  # noqa: F401,F403

# a promo picks its look in the concept round; watermark off for a product film
use_theme(typeset='heavy', watermark=None)

BPM = 112
B = 60 / BPM      # one beat
BAR = 4 * B       # one bar: cut on these
W, H = T.W, T.H
SLIDES = []

# S00 one take over a board twice the screen: the prompt on the left, the pipeline on the right
s = Slide('s00', name='一句话', world=(2 * W, H), cam0=(W / 2, H / 2, 1.0))
# on a world slide x=None centres on the whole board; pin it over the first screen instead
s.add(kinetic('k_one', '一句话，', 190, x=0, size=120, mode='letters', style=f'width:{W}px;text-align:center'))
s.add(prompt('p', '做一期视频：指数基金是什么？', 360, 430, 1200, size=54))
s.add(cursor('m', 1320, 860))
stages = [('写稿', '稿子和分镜'), ('配音', '你自己的声音'), ('动画', '跟着口播动'), ('出片', '成片和字幕')]
xs = [W + 150 + i * 440 for i in range(4)]
for i, (head, sub) in enumerate(stages):
    s.add(box(f'c{i}', f'{head}<br><span style="font-size:.5em" class="gray">{sub}</span>', xs[i], 400, w=360, size=72, a='pop', cls='big'))
    s.check(f'k{i}', xs[i] + 318, 404, s=30)
    if i:
        s.arrow(f'a{i}', xs[i - 1] + 372, 540, xs[i] - 12, 540)
s.beat(None, ['k_one'], dur=BAR)
s.beat(None, ['p', ('p_t', 0.25), ('m', 0.3), (go('m', 1500, 505), 1.75), (click('m', target='p'), 2.55)], dur=1.5 * BAR)
s.beat(None, [(f'c{i}', 0.2 + i * B / 2) for i in range(4)] + [(f'a{i}', 0.35 + (i - 1) * B / 2) for i in range(1, 4)],
       dur=BAR, cam=(W * 1.5, H / 2, 1.0, 'whip'))
s.beat(None, [(f'k{i}', i * B) for i in range(4)], dur=BAR)
s.beat(None, [(glow('c3', hold=True), 0.5), (shake(), 0.55)], dur=BAR, cam=(W + 40, H / 2, 0.56, 'snap'))
SLIDES.append(s)

# S01 the camera goes into 出片: four hard-cut words on the beat
s = Slide('s01', name='四步', trans=('through', 'c3'))
s.beat(None, s.staccato('w', ['写稿。', '配音。', '动画。', '出片。'], 390, size=180, gap=B), dur=4 * B)
SLIDES.append(s)

# S02 a stage opens from the last word: two lines rise from behind a mask
s = Slide('s02', name='你的声音', trans=('iris', W / 2, H / 2))
s.add(kinetic('v', '用<em>你自己的声音</em><br>讲你想讲的事', 330, size=104, mode='lines'))
s.beat(None, ['v', (punch('v'), 1.6)], dur=1.5 * BAR)
SLIDES.append(s)

# S03 lockup: the name drops in letter by letter, lands, the frame shakes
s = Slide('s03', name='落版', trans='cut')
s.add(kinetic('logo', 'video-studio', 380, size=150, mode='letters'))
s.add(kinetic('tag', '一句话 → 一条视频', 610, size=56, mode='words', cls='gray'))
s.beat(None, ['logo', (punch('logo'), 0.95), (shake(), 0.95), ('tag', 1.3)], dur=2 * BAR)
SLIDES.append(s)

COVERS = {}
META = {
    'name': '{NAME}',
    'title': '{TITLE}',
    'voice': None,        # no narration: beats run on dur=, the music leads
    'bgm': 'pulse',       # built-in driving bed at META bpm; or a music file you may use: 'assets/track.mp3'
    'bpm': BPM,
    'music_lu': -3.0,     # music level against the effects (no voice to sit under)
    'notes': '',
}
