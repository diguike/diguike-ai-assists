"""studio: videos from HTML slides, narration and code-made music.

usage:
  studio new <name> [title] [--portrait] [--style <preset>] [--kind explainer|promo|talk|mechanism|film]
                                            start episodes/<name>/ from a template: explainer (16:9, or 9:16
                                            with --portrait), promo (no narration, cut to music), talk (大字口播, 9:16),
                                            mechanism (原理动画: continuous scenes, 瓷光), film (情感短片: light and type, 暖光)
  studio list                               episodes in the workspace (the repo, or studio.json home)
  studio styles                             looks: presets and the parts they mix (palette / typeset / motion)
  studio styles gallery [preset ...]        the style sampler in every preset, side by side -> work/styles/gallery.jpg
  studio styles silent <preset> [palette=x] [typeset=y] [motion=z] [--portrait]
                                            the sampler moving, no voice -> work/styles/<preset>.mp4
  studio ref <video> [--out dir]            measure a reference clip: motion energy, cuts, palette, contact sheets
  studio <episode> [step ...]               build steps, default `all`; `studio help` lists them
  studio selftest                           check the install by rendering both templates
  studio install-browser                    Playwright's own Chromium, for a computer without Chrome or Edge
<episode> is a folder name under episodes/ or a path to a folder with episode.py.
"""
import datetime
import re
import shutil
import subprocess
import sys
import tempfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ENGINE = Path(__file__).resolve().parent
REPO = ENGINE.parent
sys.path.insert(0, str(ENGINE))

import host  # noqa: E402

EPISODES = host.HOME / 'episodes'
TEMPLATES = REPO / 'templates'
STYLES_WORK = host.HOME / 'work' / 'styles'
KINDS = ('explainer', 'promo', 'talk', 'mechanism', 'film')


def resolve(arg):
    for p in (Path(arg).expanduser(), EPISODES / arg):
        if (p / 'episode.py').exists():
            return p.resolve()
    sys.exit(f'episode not found: {arg} (try: studio list)')


def _theme_call(tpl, style=None, extra=None):
    """Put the preset name and part overrides into the template's first use_theme(...) call."""
    args = ([repr(style)] if style else []) + [f'{k}={v!r}' for k, v in (extra or {}).items()]
    if not args:
        return tpl
    m = re.search(r'^use_theme\((.*)\)\s*$', tpl, re.M)  # the real call, not the commented examples
    own = m.group(1)
    if style:  # a chosen preset brings its own type and motion; drop the template's defaults for them
        own = re.sub(r"\s*(typeset|motion)='[^']*',?", '', own).strip().strip(',').strip()
    inner = ', '.join(args + ([own] if own else []))
    return tpl[:m.start()] + f'use_theme({inner})' + tpl[m.end():]


def new(name, title=None, portrait=False, root=None, quiet=False, style=None, template=None, extra=None):
    """template: 'landscape' / 'portrait' (default by orientation) or 'sample' (the style sampler)."""
    import theme
    dst = (Path(root) if root else EPISODES) / name
    if (dst / 'episode.py').exists():
        sys.exit(f'already exists: {dst / "episode.py"}')
    if style:
        if style not in theme.presets():
            sys.exit(f'unknown style: {style} (try: studio styles)')
        w, h = theme._read(style).get('size', (1920, 1080))
        portrait = portrait or h > w  # a vertical preset needs the vertical layouts
    (dst / 'data').mkdir(parents=True, exist_ok=True)
    template = template or ('portrait' if portrait else 'landscape')
    tpl = (TEMPLATES / f'{template}.py').read_text(encoding='utf-8')
    tpl = (tpl.replace('{NAME}', name).replace('{TITLE}', title or name)
           .replace('{DATE}', datetime.date.today().isoformat()))
    if template == 'sample' and portrait:
        extra = {**(extra or {}), 'size': (1080, 1920)}
    tpl = _theme_call(tpl, style if style != theme.BASE else None, extra)
    (dst / 'episode.py').write_text(tpl, encoding='utf-8')
    if not quiet:
        print(dst / 'episode.py')
    return dst


# ---------------------------------------------------------------- styles

def styles_list():
    import theme
    print('风格预设（use_theme(\'名字\')，或 studio new <名字> --style 名字）')
    for n in theme.presets():
        name, desc, parts = theme.describe(n)
        print(f'  {n:10s} {name}：{desc}' + (f'\n  {"":10s} {parts}' if parts else ''))
    for kind, label in (('palette', '配色 palette='), ('typeset', '字体 typeset='), ('motion', '动效 motion=')):
        print(f'\n{label}')
        for k, v in theme.parts(kind).items():
            print(f'  {k:10s} {v["name"]}：{v.get("desc", "")}')
    print('\n转场 Slide(trans=...)：fade push up zoom wipe iris magic cut')
    print('对照图：studio styles gallery    动起来看：studio styles silent <预设> [motion=...]')


def _sample(name, style, portrait=False, extra=None):
    d = STYLES_WORK / 'eps' / name
    if d.exists():
        shutil.rmtree(d)
    return new(name, '风格样片', portrait, root=STYLES_WORK / 'eps', quiet=True, style=style, template='sample', extra=extra)


def styles_gallery(names):
    """Stills of the sampler in each preset, one row per preset."""
    import theme
    from PIL import Image, ImageDraw, ImageFont
    names = names or theme.presets()
    STYLES_WORK.mkdir(parents=True, exist_ok=True)

    def build(n):
        d = _sample(n, n)
        r = subprocess.run([sys.executable, str(ENGINE / 'build.py'), str(d), 'stills'], capture_output=True, text=True, encoding='utf-8', errors='replace')
        if r.returncode:
            raise SystemExit(f'{n}: stills failed\n{(r.stderr or r.stdout)[-1500:]}')
        flags = (d / 'work' / 'layout.txt').read_text(encoding='utf-8').splitlines()[1:]
        return n, sorted((d / 'work' / 'stills').glob('*.png')), [f for f in flags if f != '（无）']

    print(f'building the sampler in {len(names)} presets ...', flush=True)
    with ThreadPoolExecutor(3) as ex:
        rows = list(ex.map(build, names))
    pick = ('s00', 's01', 's02', 's03', 's04', 's05')
    font = ImageFont.truetype(str(theme.ASSETS / 'fonts' / 'WenKaiGB-Medium.ttf'), 30)
    small = ImageFont.truetype(str(theme.ASSETS / 'fonts' / 'WenKaiGB-Medium.ttf'), 22)
    tiny = ImageFont.truetype(str(theme.ASSETS / 'fonts' / 'WenKaiGB-Medium.ttf'), 18)
    lw, gap, tw = 420, 12, 300
    blocks = []
    for n, stills, flags in rows:
        ims = [Image.open(p).convert('RGB') for p in stills if p.stem.split('_', 1)[1] in pick]
        th = round(tw * ims[0].height / ims[0].width)
        if th > tw * 1.2:  # vertical canvas: same row width, taller row
            th = round(tw * 1.25)
        row = Image.new('RGB', (lw + len(pick) * (tw + gap), th + gap), '#F4F4F2')
        for i, im in enumerate(ims):
            w = round(th * im.width / im.height) if im.height > im.width else tw
            row.paste(im.resize((w, th), Image.LANCZOS), (lw + i * (tw + gap) + (tw - w) // 2, 0))
        title, desc, parts = theme.describe(n)
        dr = ImageDraw.Draw(row)
        head = f'{n}  {title}'
        hf = font if dr.textlength(head, font=font) <= lw - 40 else ImageFont.truetype(font.path, 24)
        dr.text((24, 14), head, fill='#1F1F1F', font=hf)
        lines, cur = [], ''
        for ch in desc:  # wrap the description into the label column
            if dr.textlength(cur + ch, font=small) > lw - 48:
                lines.append(cur)
                cur = ''
            cur += ch
        lines.append(cur)
        for i, ln in enumerate(lines[:3]):
            dr.text((24, 60 + i * 30), ln, fill='#666666', font=small)
        if parts:
            dr.text((24, 60 + min(3, len(lines)) * 30 + 4), ' · '.join(x.split('=')[1] for x in parts.split()), fill='#999999', font=tiny)
        blocks.append(row)
        if flags:
            print(f'  {n}: {len(flags)} layout flags (see {STYLES_WORK / "eps" / n / "work" / "layout.txt"})')
    sheet = Image.new('RGB', (max(b.width for b in blocks), sum(b.height for b in blocks)), '#F4F4F2')
    y = 0
    for b in blocks:
        sheet.paste(b, (0, y))
        y += b.height
    out = STYLES_WORK / 'gallery.jpg'
    sheet.save(out, quality=88)
    print(f'gallery ok: {out}')


def styles_silent(args):
    import theme
    names = [a for a in args if '=' not in a and not a.startswith('--')]
    if not names:
        sys.exit('studio styles silent <preset> [palette=x] [typeset=y] [motion=z] [--portrait]')
    extra = dict(a.split('=', 1) for a in args if '=' in a)
    for k in extra:
        if k not in theme.PART_FILES:
            sys.exit(f'only palette= typeset= motion= here (got {k}=)')
    tag = '_'.join([names[0]] + [f'{k}-{v}' for k, v in extra.items()] + (['portrait'] if '--portrait' in args else []))
    d = _sample(tag, names[0], '--portrait' in args, extra)
    subprocess.run([sys.executable, str(ENGINE / 'build.py'), str(d), 'silent'], check=True)
    out = STYLES_WORK / f'{tag}.mp4'
    shutil.copy(d / 'work' / 'silent' / 'silent.mp4', out)
    print(f'styles silent ok: {out}')


def list_episodes():
    if not EPISODES.is_dir():
        sys.exit(f'no episodes yet in {EPISODES} (studio new <name>)')
    for d in sorted(EPISODES.iterdir()):
        if (d / 'episode.py').exists():
            mp4 = sorted((d / 'out').glob('*.mp4')) if (d / 'out').exists() else []
            print(f'{d.name}  ' + (f'(out/{mp4[0].name})' if mp4 else '(还没出片)'))


def bundled_chromium():
    try:
        from playwright.sync_api import sync_playwright
        with sync_playwright() as pw:
            return Path(pw.chromium.executable_path).exists()
    except Exception:
        return False


def selftest():
    import build
    ok = True

    def check(label, cond, hint=''):
        nonlocal ok
        print(('  ok    ' if cond else '  FAIL  ') + label + ('' if cond else f'  -> {hint}'))
        ok = ok and bool(cond)

    check('ffmpeg', host.ffmpeg(), 'brew install ffmpeg / winget install ffmpeg')
    check('Chrome / Edge / Chromium', build.chrome() or bundled_chromium(),
          '装 Chrome 或 Edge，或运行 ./setup.sh / studio install-browser（Playwright 自带的 Chromium）')
    if build.DEFAULTS['voice'] == build.MYVOICE:
        voice = shutil.which('myvoice-tts') or (Path.home() / '.local/bin/myvoice-tts').exists()
        print(('  ok    ' if voice else '  --    ') + 'myvoice-tts 克隆音' +
              ('' if voice else '  -> 没装：只能用 Edge 音色（episode META voice 设为 zh-CN-YunxiNeural），装法见 README'))
    print(f'  --    视频目录 {EPISODES}')
    with tempfile.TemporaryDirectory() as tmp:
        for tpl, portrait in (('16:9 模板', False), ('9:16 模板', True)):
            d = new('selftest_' + ('portrait' if portrait else 'landscape'), 'selftest', portrait, root=tmp, quiet=True)
            r = subprocess.run([sys.executable, str(ENGINE / 'build.py'), str(d), 'stills'], capture_output=True, text=True, encoding='utf-8', errors='replace')
            n = len(list((d / 'work' / 'stills').glob('*.png')))
            check(f'{tpl}出图（{n} 页）', r.returncode == 0 and n > 0, (r.stderr or r.stdout).strip()[-600:])
    print('selftest ok' if ok else 'selftest FAILED')
    sys.exit(0 if ok else 1)


def main(argv):
    if not argv or argv[0] in ('-h', '--help'):
        sys.exit(__doc__)
    cmd = argv[0]
    if cmd == 'new':
        rest, style, kind = list(argv[1:]), None, None
        if '--style' in rest:
            i = rest.index('--style')
            if i + 1 >= len(rest):
                sys.exit('--style needs a preset name (try: studio styles)')
            style = rest[i + 1]
            del rest[i:i + 2]
        if '--kind' in rest:
            i = rest.index('--kind')
            kind = rest[i + 1] if i + 1 < len(rest) else ''
            if kind not in KINDS:
                sys.exit(f'--kind {kind}: use one of {", ".join(KINDS)}')
            del rest[i:i + 2]
        args = [a for a in rest if not a.startswith('--')]
        if not args:
            sys.exit(__doc__)
        new(args[0], args[1] if len(args) > 1 else None, '--portrait' in argv, style=style,
            template=None if kind in (None, 'explainer') else kind)
    elif cmd == 'list':
        list_episodes()
    elif cmd == 'ref':
        import qa
        args = [a for a in argv[1:] if not a.startswith('--')]
        if not args:
            sys.exit('studio ref <video> [--out dir]')
        video = Path(args[0]).expanduser()
        out = Path(argv[argv.index('--out') + 1]) if '--out' in argv else host.HOME / 'work' / 'ref' / video.stem
        print('\n'.join(qa.analyze_ref(video, out)))
        print(f'ref ok: {out}  (energy.txt, summary.json, palette.png, sheet_*.jpg)')
    elif cmd == 'styles':
        sub = argv[1] if len(argv) > 1 else ''
        if sub == 'gallery':
            styles_gallery(argv[2:])
        elif sub == 'silent':
            styles_silent(argv[2:])
        else:
            styles_list()
    elif cmd == 'selftest':
        selftest()
    elif cmd == 'install-browser':
        subprocess.run([sys.executable, '-m', 'playwright', 'install', 'chromium'], check=True)
    elif cmd == 'help':
        import build
        print(build.__doc__)
    else:
        import build
        build.main([str(resolve(cmd))] + argv[1:])


if __name__ == '__main__':
    main(sys.argv[1:])
