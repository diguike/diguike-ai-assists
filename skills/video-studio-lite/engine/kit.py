"""Drawing kit for scene-based videos (原理动画, 情感短片): cards, labels, code windows, waveforms,
dot grids and soft lights as plain HTML/SVG strings with ids. Nothing here moves; a slide's scene
(Slide.animate) moves them by id.

    from kit import box, text, editor, bars, speech_env, grid, glow, svg

Coordinates are canvas (or world) pixels. Classes such as card / glass / lbl / big / mono come from
the theme stylesheet (themes/ciguang.css); other looks can define their own.
"""
import html
import math
import random

GRID = ('<svg class="abs layer" width="{w}" height="{h}" style="left:{x}px;top:{y}px;-webkit-mask-image:radial-gradient('
        'ellipse at 50% 45%,#000 25%,transparent 72%)"><defs><pattern id="{id}" width="40" height="40" '
        'patternUnits="userSpaceOnUse"><circle cx="20" cy="20" r="1.1" fill="var(--line)"/></pattern></defs>'
        '<rect width="100%" height="100%" fill="url(#{id})" opacity=".45"/></svg>')


def grid(gid, w=1920, h=1080, x=0, y=0):
    """Engineering-paper dots, faint and fading out towards the edges."""
    return GRID.format(id=gid, w=w, h=h, x=x, y=y)


def glow(gid, x, y, r, color='47,91,255', a=.035):
    """A soft light behind things; the scene drifts it."""
    return (f'<div id="{gid}" class="abs" style="left:{x - r}px;top:{y - r}px;width:{2 * r}px;height:{2 * r}px;'
            f'border-radius:50%;background:radial-gradient(circle,rgba({color},{a}) 0%,rgba({color},0) 64%)"></div>')


def box(bid, x, y, w, h, inner='', cls='card', style=''):
    return f'<div id="{bid}" class="abs {cls}" style="left:{x}px;top:{y}px;width:{w}px;height:{h}px;{style}">{inner}</div>'


def text(tid, s, x, y, cls='lbl', size=None, style='', center=False):
    if center:  # x is the centre: a 2000 px wide line, so the scene's transforms stay free
        x -= 1000
        style = 'width:2000px;text-align:center;' + style
    st = f'left:{x}px;top:{y}px;' + (f'font-size:{size}px;' if size else '') + style
    return f'<div id="{tid}" class="abs {cls}" style="{st}">{s}</div>'


# ---------------------------------------------------------------- code

KW = ('from', 'import', 'def', 'return')


def code_line(src):
    """One line of Python in the porcelain colours: strings coral, calls cobalt, the rest ink."""
    out, i = [], 0
    while i < len(src):
        c = src[i]
        if c in '\'"':
            j = src.index(c, i + 1) + 1
            out.append(f'<span style="color:var(--secondary)">{html.escape(src[i:j])}</span>')
            i = j
        elif c.isalpha() or c == '_':
            j = i
            while j < len(src) and (src[j].isalnum() or src[j] == '_'):
                j += 1
            w = src[i:j]
            if w in KW:
                out.append(f'<span style="color:var(--muted)">{w}</span>')
            elif j < len(src) and src[j] == '(':
                out.append(f'<span style="color:var(--primary)">{w}</span>')
            else:
                out.append(w)
            i = j
        else:
            out.append(html.escape(c))
            i += 1
    return ''.join(out)


def editor(eid, x, y, w, h, name, lines, size=28, lh=1.75, top=92):
    """A code window: title bar, file name, one div per line (ids eid-c0..) and a highlight bar."""
    rows = ''.join(f'<div id="{eid}-c{k}" class="mono" style="position:absolute;left:56px;top:{top + k * size * lh:.0f}px;'
                   f'font-size:{size}px;line-height:{size * lh:.0f}px">{code_line(s)}</div>' for k, s in enumerate(lines))
    bar = (f'<div id="{eid}-hl" style="position:absolute;left:28px;right:28px;top:{top}px;height:{size * lh:.0f}px;'
           f'border-radius:6px;background:rgba(47,91,255,.06);box-shadow:inset 2px 0 0 var(--primary);opacity:0"></div>')
    head = ('<div style="position:absolute;left:28px;top:30px;display:flex;gap:10px">'
            + ''.join('<i style="width:12px;height:12px;border-radius:50%;background:var(--rule);display:block"></i>' for _ in range(3))
            + f'</div><div class="lbl" style="position:absolute;left:0;right:0;top:24px;text-align:center;font-size:20px">{name}</div>'
            '<div style="position:absolute;left:0;right:0;top:72px;height:1px;background:var(--hair)"></div>')
    caret = (f'<div id="{eid}-caret" style="position:absolute;left:56px;top:{top}px;width:2px;height:{size * 1.2:.0f}px;'
             f'margin-top:{size * (lh - 1.2) / 2:.0f}px;background:var(--primary);opacity:0"></div>')
    return box(eid, x, y, w, h, head + bar + rows + caret)


# ---------------------------------------------------------------- waveforms

def speech_env(n, seed=1, pauses=(), fade=0.0):
    """Bar heights 0..1 for n bars of speech-like sound: syllable bumps, word groups, silence at
    the given bar ranges, an optional fade towards the end (a sentence that sags)."""
    rnd = random.Random(seed)
    out, ph = [], rnd.uniform(0, 6)
    for i in range(n):
        syl = .55 + .45 * abs(math.sin(ph + i * .95))
        word = .75 + .25 * math.sin(i * .21 + seed)
        v = syl * word * rnd.uniform(.72, 1.0)
        v *= 1 - fade * (i / max(1, n - 1)) ** 1.4
        out.append(v)
    for a, b in pauses:
        for i in range(max(0, a), min(n, b)):
            edge = min(i - a + 1, b - i) / 2
            out[i] *= max(0.0, 1 - edge) * .15
    return out


def bars(prefix, x, y, w, h, env, color='var(--secondary)', gap=.52, r=None, op=1.0, cls=''):
    """A waveform as thin rounded bars centred on y (each bar id prefix-k, height scaled by env)."""
    n = len(env)
    step = w / n
    bw = step * (1 - gap)
    r = bw / 2 if r is None else r
    out = []
    for k, v in enumerate(env):
        bh = max(bw, v * h)
        out.append(f'<rect id="{prefix}-{k}" class="{cls}" x="{x + k * step:.1f}" y="{y - bh / 2:.1f}" width="{bw:.1f}" height="{bh:.1f}" '
                   f'rx="{r:.1f}" fill="{color}" opacity="{op}"/>')
    return ''.join(out)


def svg(sid, inner, w=1920, h=1080, x=0, y=0, style=''):
    return f'<svg id="{sid}" class="abs layer" width="{w}" height="{h}" style="left:{x}px;top:{y}px;overflow:visible;{style}">{inner}</svg>'
