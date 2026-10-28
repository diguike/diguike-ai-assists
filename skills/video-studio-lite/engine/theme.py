"""Look of a video: canvas, colours, fonts, motion and brand.

A look is assembled from three parts that mix freely:

    palette   colours           themes/parts/palettes.json   sunny chalk paper night ocean mint peach mono
    typeset   fonts by role     themes/parts/type.json       hand heavy song kai smiley clean
    motion    how things move   themes/parts/motion.json     keynote snappy calm bouncy editorial

A preset (themes/<name>.json) names its parts plus canvas, subtitle and brand.
The default is the house style (BASE: themes/shuiqian.json, or the base a studio.json
names; its own colours, handwriting, Keynote motion). An episode switches preset or mixes parts before
it builds slides:

    use_theme()                                     # house style
    use_theme('yedu')                               # another preset
    use_theme(palette='chalk', motion='snappy')     # house style recoloured, livelier
    use_theme('yedu', primary='#FF7A00', trans='fade', watermark=None)

A palette replaces every colour; single colour arguments still win over it.
Flat names reach into the nested groups (primary -> colors.primary,
watermark -> brand.watermark, sub_size -> subtitle.size, trans -> motion.trans);
KEYS lists them all. Shades derived from `primary` (dark text, light backgrounds,
subtitle colour) follow it automatically unless set explicitly.
"""
import copy
import json
import math
from pathlib import Path

import host

REPO = Path(__file__).resolve().parent.parent
THEMES = REPO / 'themes'
PARTS = THEMES / 'parts'
ASSETS = REPO / 'assets'
BASE = host.CONF.get('base', 'shuiqian')
REF_W, REF_H = 1920, 1080  # the size the default layouts were drawn at

COLORS = ('primary', 'secondary', 'ink', 'muted', 'danger', 'background', 'cover',
          'table_header', 'table_highlight', 'primary_dark', 'tint', 'tint2')
# finer tokens. House-style themes leave them unset and the CSS falls back to the
# exact values the default look was drawn with; palettes derive them from ink/background.
FINE = ('card', 'line', 'soft', 'rule', 'grid', 'axis', 'label', 'on_primary', 'on_th',
        'cover_ink', 'sub_outline', 'marker')
LEGACY = {'card': '#FFFFFF', 'line': '#333', 'soft': '#8C8C8C', 'rule': '#E3EEF8', 'grid': '#E6E6E6',
          'axis': '#888888', 'label': '#333333', 'on_primary': '#FFFFFF', 'on_th': '#FFFFFF',
          'cover_ink': '#222222', 'sub_outline': '#FFFFFF', 'marker': '#FCEB86'}
MOTION_KEYS = ('trans', 'trans_dur', 'ease', 'type_cps', 'cam_dur')
KEYS = {
    'size': ('size',), 'font_scale': ('font_scale',), 'ui_font': ('ui_font',),
    'font_family': ('font', 'family'), 'font_file': ('font', 'file'),
    **{k: ('colors', k) for k in COLORS + FINE},
    'sub_size': ('subtitle', 'size'), 'sub_color': ('subtitle', 'color'),
    'sub_bottom': ('subtitle', 'bottom'), 'sub_max_chars': ('subtitle', 'max_chars'),
    **{k: ('brand', k) for k in ('mascot', 'series', 'watermark', 'end_card', 'outro')},
    **{k: ('motion', k) for k in MOTION_KEYS}, 'motion_speed': ('motion', 'speed'),
    **{k: ('fx', k) for k in ('grain', 'vignette', 'letterbox', 'drift', 'glow')},
}
# film look, all off in the house style: grain (opacity of moving film grain, ~0.05), vignette
# (darkened corners, ~0.3), letterbox (picture ratio such as 2.39; subtitles sit in the lower bar),
# drift (every slide pushes in this much over its length, ~0.03), glow (soft light behind the page)
FX = {'grain': 0, 'vignette': 0, 'letterbox': 0, 'drift': 0, 'glow': 0}
PART_FILES = {'palette': 'palettes', 'typeset': 'type', 'motion': 'motion'}
# macOS system families and what Windows / Linux have in their place
FALLBACK = {'PingFang SC': ('Microsoft YaHei', 'Noto Sans CJK SC', 'Source Han Sans SC'),
            'Songti SC': ('SimSun', 'Noto Serif CJK SC', 'Source Han Serif SC')}

# hand-tuned shades of the default orange; any other primary gets computed ones
CLASSIC = {'#F8A000': {'primary_dark': '#D48800', 'tint': '#FFF4D6', 'tint2': '#FFF8E4', 'sub_color': '#F39800'}}


def _hex(c):
    c = c.strip().lstrip('#')
    if len(c) == 3:
        c = ''.join(ch * 2 for ch in c)
    return tuple(int(c[i:i + 2], 16) for i in (0, 2, 4))


def mix(a, b, t):
    """Colour a moved a fraction t towards b."""
    pa, pb = _hex(a), _hex(b)
    return '#' + ''.join(f'{round(x + (y - x) * t):02X}' for x, y in zip(pa, pb))


def luminance(c):
    def ch(v):
        v /= 255
        return v / 12.92 if v <= 0.03928 else ((v + 0.055) / 1.055) ** 2.4
    r, g, b = (ch(v) for v in _hex(c))
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def contrast(a, b):
    la, lb = sorted((luminance(a), luminance(b)), reverse=True)
    return (la + 0.05) / (lb + 0.05)


def families(*names):
    """CSS font-family list for the given families, each followed by its stand-ins on other systems."""
    out = []
    for n in names:
        for x in (n,) + FALLBACK.get(n, ()):
            if x not in out:
                out.append(x)
    return ','.join(f"'{x}'" for x in out)


def legible_on(bg, *cands):
    """The candidate colour that reads best on bg."""
    return max(cands, key=lambda c: contrast(c, bg))


def _derived(primary):
    if primary.upper() in CLASSIC:
        return dict(CLASSIC[primary.upper()])
    return {'primary_dark': mix(primary, '#000000', 0.15), 'tint': mix(primary, '#FFFFFF', 0.84),
            'tint2': mix(primary, '#FFFFFF', 0.90), 'sub_color': mix(primary, '#000000', 0.03)}


def _fine(c):
    """Finer tokens of a palette, from its ink/background unless it sets them."""
    ink, bg = c['ink'], c['background']
    dark = luminance(bg) < 0.25
    out = {
        'card': mix(bg, ink, 0.06) if dark else mix(bg, '#FFFFFF', 0.7),
        'line': mix(ink, bg, 0.25), 'soft': mix(ink, bg, 0.45), 'rule': mix(ink, bg, 0.86),
        'grid': mix(ink, bg, 0.88), 'axis': mix(ink, bg, 0.5), 'label': mix(ink, bg, 0.12),
        'on_primary': legible_on(c['primary'], '#FFFFFF', ink, bg),
        'on_th': legible_on(c['table_header'], '#FFFFFF', ink, bg),
        'cover_ink': ink if contrast(ink, c['cover']) >= 4.5 else legible_on(c['cover'], '#FFFFFF', bg, '#141414'),
        # highlighter: the row highlight on light grounds; on dark ones a muted primary that still reads
        'sub_outline': bg, 'marker': mix(c['primary'], bg, 0.55) if dark else c['table_highlight'],
    }
    out.update({k: c[k] for k in FINE if c.get(k)})
    return out


def _read(name):
    p = Path(name) if str(name).endswith('.json') else THEMES / f'{name}.json'
    if not p.exists():
        raise FileNotFoundError(f'theme not found: {p} (available: {", ".join(presets())})')
    return json.loads(p.read_text(encoding='utf-8'))


_PARTS = {}


def parts(kind):
    """{name: spec} of one part library: 'palette', 'typeset' or 'motion'."""
    if kind not in _PARTS:
        d = json.loads((PARTS / f'{PART_FILES[kind]}.json').read_text(encoding='utf-8'))
        _PARTS[kind] = {k: v for k, v in d.items() if k != 'about'}
    return _PARTS[kind]


def part(kind, name):
    lib = parts(kind)
    if name not in lib:
        raise KeyError(f'unknown {kind}: {name} (available: {", ".join(lib)})')
    return lib[name]


def presets():
    """Names of the full presets in themes/ (default first)."""
    names = sorted(p.stem for p in THEMES.glob('*.json'))
    return [BASE] + [n for n in names if n != BASE]


def _merge(dst, src):
    for k, v in src.items():
        if isinstance(v, dict) and isinstance(dst.get(k), dict):
            _merge(dst[k], v)
        else:
            dst[k] = copy.deepcopy(v)
    return dst


def _set(cfg, path, v):
    node = cfg
    *head, last = path
    for h in head:
        node = node.setdefault(h, {})
    node[last] = list(v) if isinstance(v, tuple) else v


class Theme:
    """Resolved theme. Read attributes (T.primary, T.W, T.motion, ...); change it with use_theme()."""

    def __init__(self):
        self.load()

    def load(self, name=BASE, **over):
        cfg = _read(BASE)
        preset = _read(name) if name and name != BASE else {}
        _merge(cfg, preset)
        for k in PART_FILES:
            if k in over:
                cfg[k] = over[k]
        # parts first, so explicit arguments land on top of them
        pal = cfg.get('palette')
        if pal:
            colors = copy.deepcopy(part('palette', pal)['colors'])
            if preset.get('palette') == pal:  # a preset may tweak the palette it names
                _merge(colors, preset.get('colors') or {})
            cfg['colors'] = colors
        ts = cfg.get('typeset')
        if ts:
            t = part('typeset', ts)
            if t.get('font'):
                cfg['font'] = copy.deepcopy(t['font'])
            if t.get('ui_font'):
                cfg['ui_font'] = t['ui_font']
            fams = {f['family'] for f in t.get('fonts', [])}
            cfg['fonts'] = copy.deepcopy(t.get('fonts', [])) + [f for f in cfg.get('fonts') or [] if f['family'] not in fams]
            roles = copy.deepcopy(t.get('roles') or {})
            if preset.get('typeset') == ts:
                _merge(roles, preset.get('roles') or {})
            cfg['roles'] = roles
        m = cfg.get('motion') or 'keynote'
        base, tweak = (m, {}) if isinstance(m, str) else (m.get('base', 'keynote'), {k: v for k, v in m.items() if k != 'base'})
        mo = copy.deepcopy(part('motion', 'keynote'))
        _merge(mo, part('motion', base))
        cfg['motion'] = _merge(mo, tweak)
        for k, v in over.items():
            if k in PART_FILES:
                continue
            if k in KEYS:
                _set(cfg, KEYS[k], v)
            elif k in cfg and isinstance(v, dict) and isinstance(cfg[k], dict):
                _merge(cfg[k], v)
            else:
                raise KeyError(f'unknown theme key: {k} (use one of: {", ".join(sorted(KEYS) + list(PART_FILES))})')
        self._apply(cfg, derive=bool(pal))
        return self

    def _apply(self, cfg, derive=False):
        self.cfg = cfg
        self.name = cfg.get('name', '')
        self.palette, self.typeset = cfg.get('palette'), cfg.get('typeset')
        self.W, self.H = (int(x) for x in cfg['size'])
        self.portrait = self.H > self.W
        self.s = math.sqrt(self.W * self.H / (REF_W * REF_H))  # engine-drawn parts scale with canvas area
        self.fs = float(cfg.get('font_scale', 1.0))
        c = cfg['colors']
        for k in COLORS[:9]:
            setattr(self, k, c[k])
        d = _derived(self.primary)
        self.primary_dark = c.get('primary_dark') or d['primary_dark']
        self.tint = c.get('tint') or d['tint']
        self.tint2 = c.get('tint2') or d['tint2']
        fine = _fine(c) if derive else {k: c[k] for k in FINE if c.get(k)}
        self.fine = fine  # emitted as CSS variables; anything missing keeps the house value
        for k in FINE:
            setattr(self, k, fine.get(k) or (self.table_highlight if k == 'marker' else LEGACY[k]))
        self.zero = mix(self.ink, self.background, 0.35) if derive else '#555'  # chart zero line
        f = cfg['font']
        self.font_family, self.font_file = f['family'], f.get('file')
        if self.font_file and not (ASSETS / self.font_file).exists():
            raise FileNotFoundError(f'theme font missing: assets/{self.font_file}')
        self.ui_font = cfg.get('ui_font', 'PingFang SC')
        # extra faces (e.g. a heavy headline font next to a handwriting main font)
        self.fonts = [dict(x) for x in cfg.get('fonts') or []]
        for x in self.fonts:
            if not (ASSETS / x['file']).exists():
                raise FileNotFoundError(f"theme font missing: assets/{x['file']}")
        self.roles = {k: dict(v) for k, v in (cfg.get('roles') or {}).items()}
        # optional stylesheet in themes/, loaded after the house CSS
        self.css_file = cfg.get('css') or None
        if self.css_file and not (THEMES / self.css_file).exists():
            raise FileNotFoundError(f'theme css missing: themes/{self.css_file}')
        self.motion = cfg['motion']
        self.fx = {**FX, **(cfg.get('fx') or {})}
        lb = float(self.fx.get('letterbox') or 0)
        self.bar = round((self.H - self.W / lb) / 2) if lb and self.W / lb < self.H else 0
        sub = cfg['subtitle']
        self.sub_size = round(sub['size'] * self.s * self.fs)
        self.sub_color = d['sub_color'] if sub.get('color', 'auto') == 'auto' else sub['color']
        if sub.get('bottom', 'auto') == 'auto' and self.bar:
            self.sub_bottom = max(4, round((self.bar - self.sub_size * 1.2) / 2))  # inside the lower bar
        elif sub.get('bottom', 'auto') == 'auto':
            # vertical feeds cover the bottom fifth with captions and buttons
            self.sub_bottom = round(self.H * 0.2) if self.portrait else round(46 * self.s)
        else:
            self.sub_bottom = int(sub['bottom'])
        if sub.get('max_chars', 'auto') == 'auto':
            self.sub_max = max(8, min(14 if self.portrait else 17, int(self.W * 0.9 / (self.sub_size * 1.04))))
        else:
            self.sub_max = int(sub['max_chars'])
        b = cfg['brand']
        self.mascot = b.get('mascot') or None
        if self.mascot and not (ASSETS / self.mascot).exists():
            raise FileNotFoundError(f'theme mascot missing: assets/{self.mascot}')
        self.series = b.get('series') or ''
        self.watermark = b.get('watermark') or ''
        self.end_card = b.get('end_card') or ''
        self.outro = list(b.get('outro') or [])
        # hand(): handwritten notes lean a few degrees by default; a theme can stand them upright
        self.hand_rot = float((cfg.get('hand') or {}).get('rot', -3))
        # areas text should stay out of, e.g. a phone app's buttons over a portrait video:
        # [{"name": ..., "box": [x0, y0, x1, y1]}], checked by `stills` into layout.txt
        self.avoid = [dict(z) for z in cfg.get('avoid') or []]
        if self.portrait and not any('裁切' in z.get('name', '') for z in self.avoid):
            # full-screen playback stretches 9:16 over a 19.5:9–20:9 phone and crops ~100–110 px a side
            m = round(self.W * 136 / 1080)
            self.avoid += [{'name': '左侧裁切区', 'box': [0, 0, m, self.H]},
                           {'name': '右侧裁切区', 'box': [self.W - m, 0, self.W, self.H]}]

    # motion -----------------------------------------------------------------
    def enter(self, kind):
        """Default entrance animation for an element kind ('text', 'box', 'title', ...)."""
        return self.motion['enter'].get(kind, 'fade')

    # sizes ------------------------------------------------------------------
    def px(self, n):
        """A content font size after font_scale."""
        return round(n * self.fs)

    def sp(self, n):
        """A length of an engine-drawn part (cover, watermark) scaled to the canvas."""
        return round(n * self.s)

    # css --------------------------------------------------------------------
    def stack(self, role):
        """CSS font-family list for a type role ('display' / 'text'), or None if the theme has no such role."""
        r = self.roles.get(role)
        if not r:
            return None
        return families(r['family'], self.ui_font) + ',sans-serif'

    def css_vars(self):
        fine = ''.join(f"--{k.replace('_', '-')}:{v};" for k, v in self.fine.items())
        return (':root{'
                f'--W:{self.W}px;--H:{self.H}px;--fs:{self.fs};'
                f'--primary:{self.primary};--primary-dark:{self.primary_dark};--tint:{self.tint};--tint2:{self.tint2};'
                f'--secondary:{self.secondary};--ink:{self.ink};--muted:{self.muted};--danger:{self.danger};'
                f'--bg:{self.background};--cover:{self.cover};--th:{self.table_header};--hl:{self.table_highlight};'
                f"--font:{families(self.font_family, self.ui_font)},sans-serif;--font-main:{families(self.font_family)};"
                f'--ui:{families(self.ui_font)},sans-serif;'
                f'--sub-size:{self.sub_size}px;--sub-color:{self.sub_color};--sub-bottom:{self.sub_bottom}px;'
                f'--wm-size:{self.sp(31 * self.fs)}px;--wm-right:{self.sp(56)}px;--wm-bottom:{self.sp(30)}px;'
                f'--bar:{self.bar}px;--grain:{self.fx["grain"]};--vignette:{self.fx["vignette"]};--glow:{self.fx["glow"]}'
                + (';' + fine.rstrip(';') if fine else '') +
                '}')

    def font_face(self):
        faces = ([{'family': self.font_family, 'file': self.font_file}] if self.font_file else []) + self.fonts
        return ''.join(f"@font-face{{font-family:'{x['family']}';src:url('assets/{x['file']}')}}" for x in faces)

    def theme_css(self):
        """Rules that only exist when the theme sets type roles or cover ink (none for the house style)."""
        out = ''
        text = self.stack('text')
        if text:
            w = self.roles['text'].get('weight', 400)
            out += f'body,svg text,svg .ax2,svg .lbl,svg .lbl2{{font-family:{text}}}body{{font-weight:{w}}}'
        disp = self.stack('display')
        if disp:
            w = self.roles['display'].get('weight', 400)
            out += (f'.title,.display,.qrow span,.coverbox,.cover-row span,.stat .num,.pq .qt,.crd .ct'
                    f'{{font-family:{disp};font-weight:{w}}}')
        if 'cover_ink' in self.fine:
            out += f'.slide.bg-cover,.slide.bg-cover .wm{{color:{self.cover_ink}}}'
        return out

    def extra_css(self):
        return (THEMES / self.css_file).read_text(encoding='utf-8') if self.css_file else ''


T = Theme()


def use_theme(name=BASE, **over):
    """Switch preset and/or mix parts and override fields; call at the top of episode.py, before any slide."""
    return T.load(name, **over)


def describe(name):
    """(title, description, parts) of a preset, for listings."""
    cfg = _read(name)
    bits = [f"{k}={cfg[k] if isinstance(cfg.get(k), str) else '自定'}" for k in ('palette', 'typeset', 'motion') if cfg.get(k)]
    return cfg.get('name', name), cfg.get('desc', ''), ' '.join(bits)
