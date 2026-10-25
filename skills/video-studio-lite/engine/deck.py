"""Slide-building helpers in the house style.

An episode module builds `SLIDES` from these helpers. Every animated element is
registered in ELEM with its animation type; a beat's `show` list triggers
elements when that beat's narration starts.

Show item syntax:
  'id'           start after the previous item ends (slight overlap)
  ('id', 0.3)    start 0.3s after the beat starts
  ('id', '=')    start together with the previous item

Colours, fonts, canvas size and brand come from the theme `T` (see theme.py):
use T.primary / T.secondary / T.muted / T.danger / T.primary_dark in charts.
Coordinates are canvas pixels (T.W x T.H); font sizes passed to helpers are
multiplied by the theme's font_scale.

Sound effects are picked automatically from each element's animation/kind
(see audio.sfx_for); pass sfx='chime' / 'pop' / ... to override or sfx=None to
silence one element.

Motion: an element's entrance (a=) defaults to what the theme's motion preset
gives its kind (T.enter('text') is 'type' in the house style, 'rise' in
'snappy'); pass a='type' / 'fade' / 'pop' / 'rise' / 'mask' / 'zoom' / 'blur' / 'soft' /
'slide' / 'count' / 'wipe' / 'draw' / 'growX' / 'growY' to pick one. Slides take
trans= ('fade' 'push' 'up' 'zoom' 'wipe' 'iris' 'magic' 'cut') and carry= (magic
move: {old element id: new element id}); a beat's cam=(x, y, zoom) pushes the
camera in on a point of the slide, cam=0 pulls back out.
"""
import math
import random
import re

from theme import T, use_theme  # noqa: F401  (re-exported to episodes)

ELEM = {}
AUTO = 'auto'


def _plain(html):
    return re.sub(r'<[^>]+>', '', html)


def reg(eid, anim, html='', dur=None, kind=None, val=None, sfx=AUTO):
    if eid in ELEM:
        raise ValueError(f'duplicate element id: {eid}')
    ELEM[eid] = {'a': anim, 'n': len(_plain(html)), 'd': dur, 'kind': kind, 'val': val, 'sfx': sfx}


def _anim(a, kind):
    """An element's entrance: explicit, or the motion preset's default for its kind."""
    return T.enter(kind) if a == AUTO else a


# ---------------------------------------------------------------- cues
# A cue is a timed action on an element that is already there (or on the camera):
# put it in a beat's show list next to entrances, with the same timing syntax:
#   s.beat('记住这个数', ['n', (pulse('n'), 0.6), glow('n', hold=True)])
# Emphasis plays once; out / move / dim / focus / glow(hold=True) keep their end
# state; loop keeps going until the slide ends.

CUES = []
CURSORS = {}


class Cue:
    def __init__(self, el, k, d, sfx=AUTO, persist=False, loop=False, also=(), **a):
        self.i, self.el, self.k, self.d, self.sfx = len(CUES), el, k, float(d), sfx
        self.persist, self.loop, self.also = persist, loop, list(also)
        self.a = {key: v for key, v in a.items() if v is not None}
        CUES.append(self)

    def js(self):
        return {'el': self.el, 'k': self.k, 'd': self.d, 'a': self.a}

    def __repr__(self):
        return f'<{self.k} {self.el}>'


def pulse(eid, amp=0.12, d=0.5, sfx=AUTO):
    """Swells once and settles (amp < 0 dips, like a button press)."""
    return Cue(eid, 'pulse', d, sfx, amp=amp)


def punch(eid, d=0.8, sfx=AUTO):
    """Squash-and-ring as if hit: lands a conclusion that is already on screen."""
    return Cue(eid, 'punch', d, sfx)


def shake(eid=None, amp=None, d=0.7, sfx=AUTO):
    """Element shakes no-no; shake() without an element shakes the camera (an impact)."""
    return Cue(eid or '@cam', 'shake', d, sfx, amp=amp if amp is not None else (14 if eid is None else 16))


def wiggle(eid, amp=7, d=0.8, sfx=AUTO):
    return Cue(eid, 'wiggle', d, sfx, amp=amp)


def jump(eid, h=46, d=0.6, sfx=AUTO):
    """Hops up and lands with a squash."""
    return Cue(eid, 'jump', d, sfx, h=h)


def glow(eid, color=None, r=26, hold=False, d=0.8, sfx=AUTO):
    """A soft halo in the primary colour; hold=True keeps it on."""
    return Cue(eid, 'glow', d, sfx, persist=hold, color=color, r=r, hold=hold or None)


def flash(eid, d=0.5, sfx=AUTO):
    return Cue(eid, 'flash', d, sfx)


EXITS = ('fade', 'drop', 'shrink', 'blur', 'up', 'left', 'right', 'zoom', 'cut')


def out(eid, style='fade', d=0.4, sfx=AUTO):
    """Leaves: 'fade' 'drop' 'shrink' 'blur' 'up' 'left' 'right' 'zoom' 'cut'."""
    if style not in EXITS:
        raise ValueError(f'out({eid}): unknown style {style} (use one of: {", ".join(EXITS)})')
    return Cue(eid, 'out', 0.01 if style == 'cut' else d, sfx, persist=True, style=style)


def move(eid, dx=None, dy=None, s=None, rot=None, op=None, curve='smooth', d=0.7, h=None, sfx=AUTO):
    """Moves by (dx, dy) px from where it was laid out, scales to s, turns to rot degrees, fades to op.

    curve: 'smooth' (eases in and out), 'snap' (fast then settles), 'spring' (overshoots),
    'soft', 'arc' (hops on an arc of height h), 'linear'. The end state holds; a later
    move on the same element starts from it."""
    return Cue(eid, 'move', d, sfx, persist=True, dx=dx, dy=dy, s=s, rot=rot, op=op, curve=curve, h=h)


def dim(eid, op=0.25, d=0.4):
    return move(eid, op=op, d=d)


def undim(eid, d=0.4):
    return move(eid, op=1, d=d)


def focus(*eids, op=0.22, d=0.5, sfx=AUTO):
    """Everything else on the slide steps back to op; unfocus() brings it back."""
    return Cue(eids[0], 'focus', d, sfx, persist=True, keep=list(eids), op=op)


def unfocus(d=0.5):
    return Cue('@focus', 'unfocus', d, None, persist=True)


def loop(eid, kind='float', period=3.0, amp=None):
    """Keeps moving until the slide ends: 'float' (bobs), 'breathe' (slow scale), 'spin'."""
    return Cue(eid, 'loop', period, None, loop=True, kind=kind, period=period, amp=amp)


def go(cid, x, y, d=0.8, h=40, sfx=AUTO):
    """The cursor glides to canvas point (x, y) on a slight arc."""
    x0, y0 = CURSORS[cid]
    return Cue(cid, 'move', d, sfx, persist=True, dx=x - x0, dy=y - y0, curve='arc', h=h)


def click(cid, target=None, d=0.5, sfx=AUTO):
    """The cursor presses (dip + ripple); `target` dips like a pressed button at the same time."""
    return Cue(cid, 'click', d, sfx, also=[pulse(target, amp=-0.07, d=0.3, sfx=None)] if target else [])


def text_width(text, size):
    """Rough rendered width of a text run in the handwriting font."""
    w = 0.0
    for ch in _plain(text):
        w += size * (0.56 if ord(ch) < 0x2E80 else 1.0)
    return w


TRANSITIONS = ('fade', 'push', 'up', 'zoom', 'wipe', 'iris', 'magic', 'through', 'cut')
CAM_CURVES = ('smooth', 'whip', 'snap', 'slow')


class Slide:
    """One slide. name: section title used in 口播稿.md; bg: 'white' or 'cover'
    (the theme's cover colour; 'yellow' is an alias); rate: TTS rate override for
    this slide (e.g. '+12%' for a slow, emphatic takeaway); sfx: transition sound
    when the slide appears ('whoosh' by default, None for a hard cut).

    trans: how this slide replaces the previous one (default: the motion preset's,
    'fade' in the house style); ('iris', x, y) opens a circle from a point;
    ('through', id) pushes the camera into that element of the previous slide.
    trans_dur: seconds. carry: {id on the previous slide: id on this one} for
    trans='magic': each pair flies and scales from the old place to the new one,
    and the new element is on screen from the start (leave it out of the beats).

    world=(w, h): a canvas bigger than the screen for one continuous take; the
    camera (beat cam=) travels over it, cam0=(x, y, zoom) is where it starts.

    drift: slow push over the whole slide (0.03 = 3 % closer by the end); the theme's
    fx.drift by default. s.animate(js) adds a scene: motion computed from time on every
    frame (see animate)."""

    def __init__(self, sid, name='', bg='white', wm=True, rate=None, sfx=AUTO, takes=None,
                 trans=None, trans_dur=None, carry=None, world=None, cam0=None, drift=None):
        self.id, self.name, self.bg, self.wm, self.rate, self.sfx = sid, name, bg, wm, rate, sfx
        self.takes = takes  # cloned voice: more takes for a slide whose read-back keeps failing
        self.parts, self.under, self.over, self.beats = [], [], [], []
        trans = trans or T.motion['trans']
        if isinstance(trans, (tuple, list)):
            self.trans, self.trans_at = trans[0], (trans[1] if trans[0] == 'through' else list(trans[1:3]))
        else:
            self.trans, self.trans_at = trans, None
        if self.trans not in TRANSITIONS:
            raise ValueError(f'{sid}: unknown transition {self.trans} (use one of: {", ".join(TRANSITIONS)})')
        self.trans_dur = 0.0 if self.trans == 'cut' else (trans_dur if trans_dur is not None else T.motion['trans_dur'])
        if self.trans == 'cut' and sfx == AUTO:
            self.sfx = None
        self.carry = dict(carry or {})
        self.world = tuple(world) if world else None
        self.cam0 = tuple(cam0) if cam0 else None
        if self.trans == 'through' and trans_dur is None:
            self.trans_dur = 0.9
        self.drift = T.fx.get('drift', 0) if drift is None else drift
        self.scene = None
        self.sounds = []

    def sound(self, beat, kind='tone', word=None, off=0.0, d=None):
        """A small sound effect for something a scene does: at beat ('b2' or its key) start, or when
        `word` is heard in that beat, plus off seconds. Scenes have no registered elements, so their
        motion makes no sound unless it is placed here (the house rule: animations start and end
        with a small sound). kind: tone pop chime tick swish wipe whoosh whip click keys riser impact;
        d: length for swish / keys.

            s.sound('b1', 'swish', word='配音', off=-.2, d=.9)   # the ribbon draws
            s.sound('b1', 'tone', word='配音', off=.6)           # the card settles"""
        self.sounds.append({'beat': beat, 'k': kind, 'word': word, 'off': float(off), 'd': d})
        return self

    def animate(self, run, setup=None):
        """Continuous motion on this slide: `run` is a JavaScript function of time, called on
        every frame after entrances and cues; `setup` (optional) runs once before the first frame.

            s.animate('''S => {
              const k = S.p('open', 1.2);                 // 0..1 from beat key 'open' over 1.2 s
              S.set(S.el('lid'), {y: -220 * k, r: 8 * k});
              S.morph(S.el('wave'), FLAT, LOUD, S.p('b2+0.3', .8));
            }''')

        S.t seconds since the slide began (1e4 on stills: the end state), S.t0 when the slide
        begins in the video; S.at(a) turns a beat key / 'b3' / seconds into a time; S.word('b2',
        '配音', off) when that word is heard; S.p(a, dur, ease) progress; S.since(a); S.el(id), S.q,
        S.qa; S.set(el, {x, y, s, sx, sy, r, o, blur, origin}); S.morph(path, d0, d1, k) (same
        commands, point for point); S.stroke(el, k); S.along(path, u) -> {x, y, a}; S.ctx(id) a
        cleared canvas; S.noise(x, seed), S.hash(i, j), S.lerp, S.clamp, S.ease, S.spring,
        S.lerpColor; S.cam(world_el, [[time, x, y, zoom, dur, ease], ...], sway) moves a camera over
        a world element; S.state persists across frames for caches made in setup only.
        A slide with a scene renders every frame (nothing to reuse), so keep scenes to slides
        that really move."""
        self.scene = (run.strip(), setup.strip() if setup else None)
        return self

    def add(self, *html):
        self.parts.extend(html)
        return self

    def line(self, eid, x1, y1, x2, y2, color=None, w=3, a='draw', dash=None, sfx=AUTO):
        reg(eid, a, dur=0.45, kind='line', sfx=sfx)
        d = f' stroke-dasharray="{dash}"' if dash else ''
        self.under.append(f'<line id="{eid}" data-a="{a}" x1="{x1}" y1="{y1}" x2="{x2}" y2="{y2}" '
                          f'stroke="{color or T.line}" stroke-width="{w}" stroke-linecap="round"{d}/>')

    def arrow(self, eid, x1, y1, x2, y2, color=None, w=4, sfx=AUTO):
        reg(eid, 'draw', dur=0.45, kind='arrow', sfx=sfx)
        length = math.hypot(x2 - x1, y2 - y1) or 1
        ux, uy = (x2 - x1) / length, (y2 - y1) / length
        ax, ay = x2 - 18 * ux + 12 * uy, y2 - 18 * uy - 12 * ux
        bx, by = x2 - 18 * ux - 12 * uy, y2 - 18 * uy + 12 * ux
        self.under.append(f'<path id="{eid}" data-a="draw" d="M{x1},{y1} L{x2},{y2} M{ax:g},{ay:g} L{x2},{y2} L{bx:g},{by:g}" '
                          f'fill="none" stroke="{color or T.line}" stroke-width="{w}" stroke-linecap="round" stroke-linejoin="round"/>')

    def mark(self, eid, x, y, w, h, color=None, sw=6, r=16, sfx=AUTO):
        """Highlight frame drawn around something (signature style), primary colour by default."""
        reg(eid, 'draw', dur=0.6, kind='mark', sfx=sfx)
        self.over.append(f'<rect id="{eid}" data-a="draw" x="{x}" y="{y}" width="{w}" height="{h}" rx="{r}" '
                         f'fill="none" stroke="{color or T.primary}" stroke-width="{sw}"/>')

    def cross(self, eid, cx, cy, s=70, color=None, w=14, sfx=AUTO):
        reg(eid, 'draw', dur=0.45, kind='cross', sfx=sfx)
        self.over.append(f'<path id="{eid}" data-a="draw" d="M{cx - s},{cy - s} L{cx + s},{cy + s} M{cx + s},{cy - s} L{cx - s},{cy + s}" '
                         f'fill="none" stroke="{color or T.danger}" stroke-width="{w}" stroke-linecap="round"/>')

    # hand-drawn marks: a pen going over the slide, slightly uneven on purpose
    def circle(self, eid, cx, cy, rx, ry, color=None, w=7, seed=1, sfx=AUTO):
        """Hand-drawn loop around something: a little more than one turn, uneven radius."""
        reg(eid, 'draw', dur=0.65, kind='mark', sfx=sfx)
        rnd = random.Random(seed)
        # start at the upper right so the overlapping end of the stroke lands on that side
        a0, tilt = rnd.uniform(-0.95, -0.6), math.radians(rnd.uniform(-2.0, 2.0))
        ph, n, pts = rnd.uniform(0, 6.3), 64, []
        for i in range(n + 1):
            u = i / n
            t = a0 + 2 * math.pi * 1.07 * u
            k = 1.03 - 0.055 * u + 0.012 * math.sin(3 * t + ph)
            x, y = rx * k * math.cos(t), ry * k * math.sin(t)
            pts.append((cx + x * math.cos(tilt) - y * math.sin(tilt), cy + x * math.sin(tilt) + y * math.cos(tilt)))
        d = 'M' + ' L'.join(f'{x:.1f},{y:.1f}' for x, y in pts)
        self.over.append(f'<path id="{eid}" data-a="draw" d="{d}" fill="none" stroke="{color or T.primary}" '
                         f'stroke-width="{w}" stroke-linecap="round" stroke-linejoin="round"/>')

    def underline(self, eid, x1, x2, y, color=None, w=8, seed=1, sfx=AUTO):
        """Hand-drawn underline with a slight wave and lift at the end."""
        reg(eid, 'draw', dur=0.45, kind='mark', sfx=sfx)
        rnd = random.Random(seed)
        ph, n = rnd.uniform(0, 6.3), max(4, int((x2 - x1) / 28))
        pts = [(x1 + (x2 - x1) * i / n, y + 3.2 * math.sin(ph + i * 1.3) - 9 * (i / n) ** 3) for i in range(n + 1)]
        d = 'M' + ' L'.join(f'{x:.1f},{yy:.1f}' for x, yy in pts)
        self.over.append(f'<path id="{eid}" data-a="draw" d="{d}" fill="none" stroke="{color or T.primary}" '
                         f'stroke-width="{w}" stroke-linecap="round" stroke-linejoin="round"/>')

    def check(self, eid, cx, cy, s=34, color=None, w=11, sfx=AUTO):
        """Tick mark (pass / done), drawn in one stroke."""
        reg(eid, 'draw', dur=0.35, kind='check', sfx=sfx)
        d = f'M{cx - s:.1f},{cy - s * 0.05:.1f} L{cx - s * 0.25:.1f},{cy + s * 0.7:.1f} L{cx + s * 1.1:.1f},{cy - s * 0.85:.1f}'
        self.over.append(f'<path id="{eid}" data-a="draw" d="{d}" fill="none" stroke="{color or T.secondary}" '
                         f'stroke-width="{w}" stroke-linecap="round" stroke-linejoin="round"/>')

    def curve_arrow(self, eid, x1, y1, x2, y2, bend=0.25, color=None, w=6, head=22, sfx=AUTO):
        """Curved pen arrow from (x1, y1) to (x2, y2); bend > 0 bows to the left of the direction."""
        reg(eid, 'draw', dur=0.5, kind='arrow', sfx=sfx)
        mx, my = (x1 + x2) / 2, (y1 + y2) / 2
        qx, qy = mx - (y2 - y1) * bend, my + (x2 - x1) * bend
        ang = math.atan2(y2 - qy, x2 - qx)
        h1 = (x2 - head * math.cos(ang - 0.45), y2 - head * math.sin(ang - 0.45))
        h2 = (x2 - head * math.cos(ang + 0.45), y2 - head * math.sin(ang + 0.45))
        d = (f'M{x1:.1f},{y1:.1f} Q{qx:.1f},{qy:.1f} {x2:.1f},{y2:.1f} '
             f'M{h1[0]:.1f},{h1[1]:.1f} L{x2:.1f},{y2:.1f} L{h2[0]:.1f},{h2[1]:.1f}')
        self.over.append(f'<path id="{eid}" data-a="draw" d="{d}" fill="none" stroke="{color or T.primary}" '
                         f'stroke-width="{w}" stroke-linecap="round" stroke-linejoin="round"/>')

    def beat(self, text, show=(), tts=None, pause=None, cam=None, dur=None, key=None):
        """One narration line. `text` is the subtitle; `tts` overrides what is spoken.

        text=None (or '') with dur=seconds is a beat without narration: the picture
        moves on its own for that long (promos, music-driven cuts, a held pause).

        cam=(x, y, zoom) moves the camera while this line starts so canvas point
        (x, y) is centred at that zoom (e.g. 1.8 to read a corner of a chart);
        cam=(x, y, zoom, 'whip') picks the move: 'smooth' (default), 'whip' (fast
        in-out), 'snap' (fast then settles), 'slow'; cam=0 goes back to the whole
        slide. On a world slide zoom may go below 1 to show more. Stills always
        show the whole slide."""
        if cam is not None and cam != 0:
            if len(cam) not in (3, 4) or (cam[2] < 1 and not self.world) or cam[2] <= 0:
                raise ValueError(f'{self.id}: cam=(x, y, zoom[, curve]) with zoom >= 1 (any zoom on a world slide), or cam=0')
            if len(cam) == 4 and cam[3] not in CAM_CURVES:
                raise ValueError(f'{self.id}: camera curve {cam[3]} (use one of: {", ".join(CAM_CURVES)})')
        voiced = bool(text)
        if not voiced and not dur:
            raise ValueError(f'{self.id}: a beat without text needs dur=seconds')
        self.beats.append({'text': text or '', 'show': list(show), 'tts': tts, 'pause': pause, 'cam': cam,
                           'dur': dur, 'voiced': voiced, 'key': key})
        return self

    def has_cam(self):
        shakes = any(isinstance(it, Cue) and it.el == '@cam' or isinstance(it, tuple) and isinstance(it[0], Cue) and it[0].el == '@cam'
                     for b in self.beats for it in b['show'])
        return bool(self.world) or shakes or any(b.get('cam') is not None for b in self.beats)

    def staccato(self, prefix, words, y, size=150, gap=0.32, x=None, cls='display', sfx='tick'):
        """Words hard-cut one after another in the same spot (a burst of hits).

        Adds elements prefix0..N and returns the show list for one beat:
        s.beat(None, s.staccato('w', ['写稿', '配音', '出片'], 400), dur=1.2)"""
        show = []
        for i, w in enumerate(words):
            self.add(txt(f'{prefix}{i}', w, y, x=x, size=size, a='cut', cls=cls, sfx=sfx))
            show.append((f'{prefix}{i}', round(i * gap, 3)))
            if i < len(words) - 1:
                show.append((out(f'{prefix}{i}', 'cut'), round((i + 1) * gap, 3)))
        return show

    def html(self):
        w, h = self.world or (T.W, T.H)
        svg = f'<svg class="abs layer{{}}" width="{w}" height="{h}">{{}}</svg>'
        svg_u = svg.format('', ''.join(self.under)) if self.under else ''
        svg_o = svg.format(' top', ''.join(self.over)) if self.over else ''
        bg = 'bg-cover' if self.bg in ('cover', 'yellow') else ''
        body = f'{svg_u}{"".join(self.parts)}{svg_o}'
        if self.has_cam():  # everything the camera sees; watermark stays outside
            size = f' style="width:{self.world[0]}px;height:{self.world[1]}px"' if self.world else ''
            body = f'<div class="cam"{size}>{body}</div>'
        if self.drift:
            body = f'<div class="drift" data-drift="{self.drift}">{body}</div>'
        return f'<section class="slide {bg}" id="{self.id}">{body}</section>'

    def moving(self):
        """Does this slide change on every frame (a scene, or a slow drift)?"""
        return bool(self.scene or self.drift)


# ---------------------------------------------------------------- elements

def txt(eid, html, y, x=None, size=50, a=AUTO, cls='', style='', dur=None, sfx=AUTO):
    """Text block; x=None centers it horizontally. a=None leaves it static."""
    pos = 'left:0;right:0;text-align:center;' if x is None else f'left:{x}px;'
    attr = ''
    a = _anim(a, 'text')
    if a:
        reg(eid, a, html, dur, kind='text', sfx=sfx)
        attr = f' data-a="{a}"'
    return f'<div id="{eid}" class="abs txt {cls}"{attr} style="{pos}top:{y}px;font-size:{T.px(size)}px;{style}">{html}</div>'


def box(eid, text, x, y, w=300, size=52, a=AUTO, cls='', sfx=AUTO):
    a = _anim(a, 'box')
    reg(eid, a, kind='box', sfx=sfx)
    return (f'<div id="{eid}" class="abs box {cls}" data-a="{a}" '
            f'style="left:{x}px;top:{y}px;width:{w}px;font-size:{T.px(size)}px">{text}</div>')


def title(eid, text, y=70, size=62, a=AUTO, sfx=AUTO):
    a = _anim(a, 'title')
    reg(eid, a, kind='title', sfx=sfx)
    return f'<div id="{eid}" class="abs title" data-a="{a}" style="top:{y}px;font-size:{T.px(size)}px">{text}</div>'


def question(eid, text, y=60, size=62, a=AUTO, sfx=AUTO):
    """Mascot + question headline, as used in earlier episodes."""
    a = _anim(a, 'title')
    reg(eid, a, kind='title', sfx=sfx)
    pic = f'<img src="assets/{T.mascot}" style="height:{int(T.px(size) * 1.9)}px">' if T.mascot else ''
    return (f'<div id="{eid}" class="abs qrow" data-a="{a}" style="top:{y}px">'
            f'{pic}<span style="font-size:{T.px(size)}px">{text}</span></div>')


def hand(eid, html, y, x=None, size=60, rot=-3, a=AUTO, cls='', style='', sfx=AUTO):
    """Handwritten note in the theme's main font (written out char by char by default)."""
    return txt(eid, html, y, x=x, size=size, a=_anim(a, 'hand'), cls=f'hand {cls}'.strip(), style=f'rotate:{rot}deg;{style}', sfx=sfx)


def prompt(eid, text, x, y, w, size=56, a='type', dur=None, sfx=AUTO):
    """Chat input box: the box fades in (eid), then the text types itself (eid + '_t').

    dur: typing time in seconds; set it to how long the narration takes to say the line."""
    reg(eid, 'fade', kind='box', sfx=sfx)
    reg(f'{eid}_t', a, text, dur=dur, kind='prompt')
    return (f'<div id="{eid}" class="abs prompt" data-a="fade" style="left:{x}px;top:{y}px;width:{w}px;font-size:{T.px(size)}px">'
            f'<div id="{eid}_t" class="ptext" data-a="{a}">{text}</div><i class="send"></i></div>')


def img(eid, src, x, y, w, a=AUTO, sfx=AUTO):
    """Picture from the episode's assets/ folder (src='assets/x.png') or a URL."""
    a = _anim(a, 'img')
    reg(eid, a, kind='img', sfx=sfx)
    return f'<img id="{eid}" class="abs" data-a="{a}" src="{src}" style="left:{x}px;top:{y}px;width:{w}px">'


def chips(prefix, labels, y, a=AUTO, sfx=AUTO):
    """Row of rounded chips that pop in one by one: ids prefix0..N (wraps on narrow canvases)."""
    a = _anim(a, 'chip')
    for i in range(len(labels)):
        reg(f'{prefix}{i}', a, kind='chip', sfx=sfx)
    return (f'<div class="abs chiprow" style="top:{y}px">' +
            ''.join(f'<div id="{prefix}{i}" class="chip" data-a="{a}">{c}</div>' for i, c in enumerate(labels)) + '</div>')


# ---------------------------------------------------------------- kinetic type + cursor

KINETIC = {'words': (0.55, 0.12), 'letters': (0.6, 0.05), 'lines': (0.6, 0.14), 'pops': (0.45, 0.1)}


def kinetic(eid, text, y, x=None, size=110, mode='words', stagger=None, cls='display', style='', sfx=AUTO):
    """Big type that arrives piece by piece.

    mode 'words': pieces split on '|' (or spaces; Chinese without either: one piece per
    character) spring up one after another; 'letters': each character drops in and
    squashes on landing (a wordmark); 'lines': lines (split on <br>) rise from behind a
    mask; 'pops': pieces pop. Pieces may hold inline html: kinetic('k', '不选股|<em>买一篮子</em>', 400)."""
    if mode not in KINETIC:
        raise ValueError(f'kinetic({eid}): mode {mode} (use one of: {", ".join(KINETIC)})')
    if mode == 'lines':
        parts = re.split(r'<br\s*/?>|\n', text)
    elif '|' in text:
        parts = text.split('|')
    elif ' ' in text.strip() and mode == 'words':
        parts = [w + ' ' for w in text.split(' ')]
    elif '<' not in text:
        parts = list(text)
    else:
        parts = [text]
    one, gap = KINETIC[mode]
    gap = gap if stagger is None else stagger
    total = one + gap * (len(parts) - 1)
    reg(eid, mode, text, dur=round(total, 3), kind='kinetic', sfx=sfx)
    kl = ' kl' if mode == 'lines' else ''
    body = ''.join(f'<span class="kp{kl}">{p}</span>' for p in parts)
    pos = 'left:0;right:0;text-align:center;' if x is None else f'left:{x}px;'
    return (f'<div id="{eid}" class="abs txt kin {mode} {cls}" data-a="{mode}" data-sf="{gap / total:.4f}" '
            f'data-df="{one / total:.4f}" style="{pos}top:{y}px;font-size:{T.px(size)}px;{style}">{body}</div>')


def cursor(eid, x, y, size=56):
    """A mouse pointer whose tip is at canvas point (x, y). It fades in when shown; then
    go(eid, x, y) glides it and click(eid, target) presses."""
    reg(eid, 'fade', kind='cursor', sfx=None)
    CURSORS[eid] = (x, y)
    k = size / 48
    return (f'<div id="{eid}" class="abs cursor" data-a="fade" style="left:{x}px;top:{y}px">'
            f'<span class="rip"></span><svg width="{round(34 * k)}" height="{round(50 * k)}" viewBox="-2 -2 34 50">'
            f'<path d="M0,0 L0,40 L10,31 L17,47 L24,44 L17,28 L30,28 Z" fill="#fff" stroke="#151515" '
            f'stroke-width="2.6" stroke-linejoin="round"/></svg></div>')


# ---------------------------------------------------------------- more layouts (any theme)

def hl(eid, text, sfx=AUTO):
    """Highlighter stroke sweeping behind part of a line; put it inside txt(): txt('t', f'记住{hl("k", "三件事")}', ...)."""
    reg(eid, 'marker', dur=0.5, kind='marker', sfx=sfx)
    return f'<span id="{eid}" class="mk" data-a="marker">{text}</span>'


def strike(eid, text, sfx=AUTO):
    """Strike-through drawn across part of a line (a claim being crossed out)."""
    reg(eid, 'marker', dur=0.4, kind='strike', sfx=sfx)
    return f'<span id="{eid}" class="strike" data-a="marker">{text}</span>'


def tag(eid, text, y, x=None, size=36, a=AUTO, sfx=AUTO):
    """Small outlined label above a title ("第一步", "误区"); x=None centers it."""
    a = _anim(a, 'chip')
    reg(eid, a, kind='chip', sfx=sfx)
    pos = 'left:0;right:0;text-align:center;' if x is None else f'left:{x}px;'
    return (f'<div class="abs tgrow" style="{pos}top:{y}px"><span id="{eid}" class="tg" data-a="{a}" '
            f'style="font-size:{T.px(size)}px">{text}</span></div>')


def stat(eid, value, label='', y=300, x=None, size=150, w=None, a=AUTO, sfx=AUTO):
    """A big number with a caption under it; numbers in `value` roll up from zero by default (a='count').

    value is html, e.g. '<em>16.3</em>%' or '1,000<small>元</small>'; x=None centers it."""
    a = _anim(a, 'stat')
    if a:
        reg(eid, a, kind='stat', sfx=sfx)
    pos = 'left:0;right:0;' if x is None else f'left:{x}px;' + (f'width:{w}px;' if w else '')
    lab = f'<div class="lab" style="font-size:{T.px(round(size * 0.3))}px">{label}</div>' if label else ''
    attr = f' data-a="{a}"' if a else ''
    return (f'<div id="{eid}" class="abs stat"{attr} style="{pos}top:{y}px">'
            f'<div class="num" style="font-size:{T.px(size)}px">{value}</div>{lab}</div>')


def quote(eid, text, who='', y=300, x=None, w=None, size=64, a=AUTO, sfx=AUTO):
    """Pull quote with a large opening mark and an optional attribution."""
    a = _anim(a, 'quote')
    reg(eid, a, kind='quote', sfx=sfx)
    w = w or round(T.W * 0.72)
    left = round((T.W - w) / 2) if x is None else x
    by = f'<div class="by" style="font-size:{T.px(round(size * 0.55))}px">—— {who}</div>' if who else ''
    return (f'<div id="{eid}" class="abs pq" data-a="{a}" style="left:{left}px;top:{y}px;width:{w}px">'
            f'<div class="qm" style="font-size:{T.px(size * 3)}px">“</div>'
            f'<div class="qt" style="font-size:{T.px(size)}px">{text}</div>{by}</div>')


def steps(prefix, items, x, y, gap=130, size=52, a=AUTO, sfx=AUTO):
    """Numbered list, one element per step: ids prefix0..N. items: ['text', ...] or [('text', 'note'), ...]."""
    a = _anim(a, 'step')
    out = []
    for i, it in enumerate(items):
        text, note = (it, '') if isinstance(it, str) else it
        reg(f'{prefix}{i}', a, kind='step', sfx=sfx)
        sub = f'<div class="sm" style="font-size:{T.px(round(size * 0.62))}px">{note}</div>' if note else ''
        out.append(f'<div id="{prefix}{i}" class="abs stp" data-a="{a}" style="left:{x}px;top:{y + i * gap}px;font-size:{T.px(size)}px">'
                   f'<span class="sn">{i + 1}</span><div class="sb"><div>{text}</div>{sub}</div></div>')
    return ''.join(out)


def cards(prefix, items, y, w=None, h=None, gap=40, size=46, a=AUTO, sfx=AUTO):
    """A centred row (wrapping) of cards: ids prefix0..N. items: [('heading', 'body html'), ...]."""
    a = _anim(a, 'card')
    n = len(items)
    cols = n if n <= 4 and not T.portrait else (2 if T.portrait or n == 4 else 3)
    w = w or round((T.W * (0.86 if T.portrait else 0.84) - gap * (cols - 1)) / cols)
    hh = f'height:{h}px;' if h else ''
    out = [f'<div class="abs crdrow" style="top:{y}px;gap:{gap}px">']
    for i, (head, body) in enumerate(items):
        reg(f'{prefix}{i}', a, kind='card', sfx=sfx)
        out.append(f'<div id="{prefix}{i}" class="crd" data-a="{a}" style="width:{w}px;{hh}font-size:{T.px(size)}px">'
                   f'<div class="ct">{head}</div><div class="cx">{body}</div></div>')
    out.append('</div>')
    return ''.join(out)


def bars(s, prefix, items, x, y, w, h, unit='', vmax=None, size=40):
    """Simple vertical bar chart in theme colours. items: [(label, value[, colour])].

    Bars grow (ids prefix_b0..N) and their values fade in (prefix_v0..N); returns
    {'bars': [...], 'vals': [...]} so beats can show them in any order."""
    vmax = vmax or max(v for _, v, *_ in items) * 1.15
    n = len(items)
    gw = w / n
    bw = min(gw * 0.56, 150)
    g = [f'<svg class="abs" width="{T.W}" height="{T.H}" style="left:0;top:0">',
         f'<line x1="{x}" y1="{y + h}" x2="{x + w}" y2="{y + h}" stroke="{T.zero}" stroke-width="3"/>']
    ids = {'bars': [], 'vals': []}
    for i, (label, v, *col) in enumerate(items):
        col = col[0] if col else (T.primary if i == n - 1 else T.secondary)
        cx = x + gw * (i + 0.5)
        bh = max(2, v / vmax * h)
        bid, vid = f'{prefix}_b{i}', f'{prefix}_v{i}'
        reg(bid, 'growY', dur=0.55, kind='bar')
        reg(vid, 'fade')
        g.append(f'<rect id="{bid}" data-a="growY" class="pos" x="{cx - bw / 2:.1f}" y="{y + h - bh:.1f}" width="{bw:.1f}" '
                 f'height="{bh:.1f}" rx="6" fill="{col}"/>')
        g.append(f'<text id="{vid}" data-a="fade" x="{cx:.1f}" y="{y + h - bh - 18:.1f}" text-anchor="middle" class="val2" '
                 f'style="font-size:{T.px(size)}px">{v:g}{unit}</text>')
        g.append(f'<text x="{cx:.1f}" y="{y + h + T.px(size) + 14:.1f}" text-anchor="middle" class="lbl" '
                 f'style="font-size:{T.px(size)}px">{label}</text>')
        ids['bars'].append(bid)
        ids['vals'].append(vid)
    g.append('</svg>')
    s.add(''.join(g))
    return ids


def mindmap(s, p, label, lx, ly, nodes, bx, bw=300, tx=None, tsize=46, lsize=58, gap=72):
    """Label -> lines -> boxes -> explanation lines (the 优势/劣势 layout).

    nodes: [(box_text, box_top, [line_html, ...]), ...]
    Returns ids: {'label', 'lines', 'boxes', 'texts'}.
    """
    tx = tx if tx is not None else bx + bw + 70
    ids = {'label': f'{p}_lab', 'lines': [], 'boxes': [], 'texts': []}
    s.add(txt(ids['label'], label, ly, x=lx, size=lsize, a='fade', cls='orange'))
    ly_mid = ly + T.px(lsize) * 0.75
    lx_end = lx + text_width(label, T.px(lsize)) + 18
    for i, (btext, btop, lines) in enumerate(nodes):
        mid = btop + 48
        s.line(f'{p}_l{i}', round(lx_end), round(ly_mid), bx, mid)
        s.add(box(f'{p}_b{i}', btext, bx, btop, w=bw))
        ids['lines'].append(f'{p}_l{i}')
        ids['boxes'].append(f'{p}_b{i}')
        n = len(lines)
        start = mid - ((n - 1) * gap + 1.5 * T.px(tsize)) / 2
        tids = []
        for j, ln in enumerate(lines):
            tid = f'{p}_t{i}{j}'
            s.add(txt(tid, ln, round(start + j * gap), x=tx, size=tsize))
            tids.append(tid)
        ids['texts'].append(tids)
    return ids


def node(ids, i):
    """Show sequence for one mindmap branch: line, box, then its text lines."""
    return [ids['lines'][i], ids['boxes'][i]] + ids['texts'][i]


def table(p, x, y, cols, header, rows, hl_rows=(), rh=112, hh=100, size=44):
    """Header-coloured table like the A/C episode. Each row is a wipe-revealed element."""
    w = sum(cols)
    out = [f'<div class="abs tbl" style="left:{x}px;top:{y}px;width:{w}px">']
    reg(f'{p}_h', 'fade', kind='th')
    out.append(f'<div id="{p}_h" class="tr th" data-a="fade" style="height:{hh}px">' +
               ''.join(f'<div class="td" style="width:{c}px;font-size:{T.px(size + 4)}px">{t}</div>' for c, t in zip(cols, header)) + '</div>')
    for i, r in enumerate(rows):
        reg(f'{p}_r{i}', 'wipe', kind='row')
        cls = 'tr hl' if i in hl_rows else 'tr'
        out.append(f'<div id="{p}_r{i}" class="{cls}" data-a="wipe" style="height:{rh}px">' +
                   ''.join(f'<div class="td{" first" if k == 0 else ""}" style="width:{c}px;font-size:{T.px(size)}px">{t}</div>'
                           for k, (c, t) in enumerate(zip(cols, r))) + '</div>')
    out.append('</div>')
    return ''.join(out)


# ---------------------------------------------------------------- cover / end card

def cover(top_text=None, box_html='', box_font=None, box_h=None, size=None,
          box_weight=None, box_stroke=None, series_font=None, series_weight=None):
    """Cover-style block: mascot + series name, then the white title box.

    Laid out for `size` (default: the canvas) by scaling the 1920x1080 design;
    top_text=None uses the theme's series name. box_h fixes the box height
    (design px), otherwise it fits the text. Typography comes from the theme's
    cover_type; explicit values override it, including zero stroke for old covers.
    """
    W, H = size or (T.W, T.H)
    s = (W * H / (1920 * 1080)) ** 0.5
    typo = T.cfg.get('cover_type') or {}
    box_font = typo.get('size', 78) if box_font is None else box_font
    box_weight = typo.get('weight') if box_weight is None else box_weight
    box_stroke = typo.get('stroke', 0) if box_stroke is None else box_stroke
    series_font = typo.get('series_size', 80) if series_font is None else series_font
    series_weight = typo.get('series_weight') if series_weight is None else series_weight
    title_style = (f'font-weight:{box_weight};' if box_weight is not None else '')
    title_style += f'-webkit-text-stroke:{box_stroke * s * T.fs:.2f}px currentColor;'
    label_style = f'font-weight:{series_weight};' if series_weight is not None else ''
    top_text = T.series if top_text is None else top_text
    pic_h = round(255 * s) if T.mascot else 0
    # a third of the free space above the block (mascot row + a nominal 270px box): 170px at 1920x1080
    row_top = round((H - (pic_h or 110 * s) - 45 * s - 270 * s) / 3)
    out = []
    if T.mascot or top_text:
        pic = f'<img src="assets/{T.mascot}" style="height:{pic_h}px">' if T.mascot else ''
        label = (f'<span style="font-size:{round(series_font * s * T.fs)}px;{label_style}padding-bottom:{round(26 * s)}px">{top_text}</span>'
                 if top_text else '')
        out.append(f'<div class="abs cover-row" style="top:{row_top}px;gap:{round(14 * s)}px">{pic}{label}</div>')
        box_top = row_top + (pic_h or round(110 * s * T.fs)) + round(45 * s)
    else:
        box_top = row_top
    height = f'height:{round(box_h * s)}px;' if box_h else f'padding-top:{round(22 * s)}px;padding-bottom:{round(22 * s)}px;'
    out.append(f'<div class="abs coverbox" style="top:{box_top}px;{height}padding-left:{round(80 * s)}px;'
               f'padding-right:{round(80 * s)}px;font-size:{round(box_font * s * T.fs)}px;{title_style}'
               f'box-shadow:0 {round(34 * s)}px {round(36 * s)}px -{round(24 * s)}px rgba(0,0,0,.28)">{box_html}</div>')
    return ''.join(out)


def cover_page(top_text=None, box_html='', size=None, **kw):
    """(size, html) of a standalone cover image, for the episode's COVERS dict."""
    size = tuple(size or (T.W, T.H))
    return size, cover(top_text, box_html, size=size, **kw)


def end_slide(sid='end', name='结尾', lines=None):
    """End card with the theme's brand: series + end_card text, narrated with T.outro."""
    s = Slide(sid, name=name, bg='cover', rate='+15%')
    s.add(cover(T.series, T.end_card, box_font=86, box_h=200))
    lines = T.outro if lines is None else lines
    for i, line in enumerate(lines):
        s.beat(line, pause=1.8 if i == len(lines) - 1 else None)
    return s
