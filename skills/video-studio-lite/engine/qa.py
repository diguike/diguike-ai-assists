"""Craft checks that read a cut in numbers before anyone watches it.

rhythm(plan)        from plan.json: do shot lengths vary, do slide changes carry something across,
                    is the picture ever still? -> work/rhythm.txt
analyze_ref(video)  a reference clip you like, measured: where it moves and rests, where it cuts,
                    its palette, contact sheets -> work/ref/<name>/

The thresholds come from what reads as "翻 PPT" in motion work: equal shot lengths (a
metronome), slides that replace each other with nothing surviving the change, and a
frame that never stops moving. They are advice, not gates: an explainer is allowed to
be calmer than a promo.
"""
import json
import math
import re
import shutil
import subprocess
from pathlib import Path

import numpy as np

import host

CARRY = {'magic', 'through', 'iris'}  # transitions where something on screen survives the change


def _union(intervals):
    out = []
    for a, b in sorted(intervals):
        if out and a <= out[-1][1]:
            out[-1][1] = max(out[-1][1], b)
        else:
            out.append([a, b])
    return out


def rhythm(plan, promo=False):
    """Lines of the rhythm report for a plan (promo=True judges carries more strictly)."""
    slides, total = plan['slides'], plan['total']
    lens = [s['end'] - s['start'] for s in slides]
    mean = sum(lens) / len(lens)
    cv = (sum((x - mean) ** 2 for x in lens) / len(lens)) ** 0.5 / mean if len(lens) > 1 else 0.0
    bounds = []
    for s in slides[1:]:
        k = s.get('tr', 'fade')
        carried = k in CARRY and (k != 'magic' or s.get('carry')) and (k != 'iris' or s.get('tro'))
        bounds.append((s['id'], k, bool(carried)))
    n_carry = sum(c for *_, c in bounds)
    # when is something moving: entrances, actions (loops excluded), camera moves
    busy = [(st, st + d) for st, d in plan['trig'].values()]
    busy += [(t0, t0 + d) for t0, d, si, persist, lp in plan.get('acts', {}).values() if not lp]
    busy += [(k[0], k[0] + 1.0) for s in slides for k in s.get('cams') or []]
    busy += [(s['start'], s['start'] + s.get('td', 0.35)) for s in slides[1:]]
    # a scene (Slide.animate) or a drift moves on every frame; its motion is continuous, not "new things"
    flowing = [(s['start'], s['end']) for s in slides if s.get('moving')]
    busy += flowing
    moving = _union(busy)
    still = total - sum(b - a for a, b in moving)
    gaps = [b[0] - a[1] for a, b in zip(moving, moving[1:])]
    longest_rest = max(gaps, default=0.0)
    longest_busy = max((b - a for a, b in moving), default=0.0)
    lines = ['# 节奏报告（看镜头长短、换页衔接、静止和停顿；是建议不是硬规定）', '',
             f'时长 {total:.1f}s，{len(slides)} 页；每页 {min(lens):.1f}–{max(lens):.1f}s，长短变化系数 {cv:.2f}'
             + ('  ← 太均匀，像节拍器：让重点页长、铺垫页短' if cv < (0.25 if promo else 0.15) and len(slides) > 3 else ''),
             f'静止占 {still / total:.0%}，最长一段静止 {longest_rest:.1f}s，最长一段一直在动 {longest_busy:.1f}s'
             + ('  ← 几乎不停：结论出来后让画面停一两秒' if still / total < 0.15 else ''),
             f'换页 {len(bounds)} 次，有衔接 {n_carry} 次（magic / through / iris）'
             + (f'  ← 宣传片里大多数换页应该有东西接过去' if promo and bounds and n_carry / len(bounds) < 0.5 else '')]
    kinds = {}
    for _, k, _c in bounds:
        kinds[k] = kinds.get(k, 0) + 1
    if kinds:
        lines.append('换页方式：' + '，'.join(f'{k} ×{v}' for k, v in sorted(kinds.items(), key=lambda kv: -kv[1])))
    run, longest = 1, 1
    for (_, a, _), (_, b, _) in zip(bounds, bounds[1:]):
        run = run + 1 if a == b else 1
        longest = max(longest, run)
    if longest >= 5:
        lines.append(f'连续 {longest} 次同一种换页：中间换一两种，或者用 magic 把相关的两页接起来')
    if flowing:
        lines.append(f'连续动画（场景或缓推）的页 {len(flowing)} 页，'
                     f'共 {sum(b - a for a, b in flowing):.0f}s：画面一直在动，静止比例按这些页算作在动；'
                     '这种页更要有"停住"的时刻（动作做完让它稳住）')
    idle = idle_pages(plan, 3.0 if promo else 6.0)
    lines += ['', f'# 一页里超过 {3 if promo else 6} 秒没有新东西出现（念到哪行出哪行，或者拆页）'] + (idle or ['（无）'])
    blank = blank_starts(plan)
    if blank:
        lines += ['', '# 硬切过来先是空白页（给一个元素 a=None，或者让第一个元素早点出来）'] + blank
    lines += ['', '# 每页时长'] + [f"{s['id']:6s} {e:5.1f}s  {'' if i == 0 else (s.get('tr', 'fade') + (' ✓衔接' if bounds[i - 1][2] else ''))}"
                                 for i, (s, e) in enumerate(zip(slides, lens))]
    return lines


def _slide_events(plan, si):
    """Times something new happens on slide si: entrances, actions, camera moves."""
    s = plan['slides'][si]
    ev = [plan['trig'][e][0] for e in plan.get('elems', {}).get(s['id'], []) if e in plan['trig']]
    ev += [t0 for t0, d, i, persist, lp in plan.get('acts', {}).values() if i == si]
    ev += [k[0] for k in s.get('cams') or []]
    return sorted(t for t in ev if s['start'] <= t <= s['end'])


def idle_pages(plan, limit):
    """Stretches longer than `limit` seconds on one slide with no entrance, action or camera move."""
    out = []
    for si, s in enumerate(plan['slides']):
        ev = _slide_events(plan, si)
        if s.get('moving'):  # a scene changes with each line it is keyed to
            ev = sorted(ev + [s['start'] + b for b in s.get('bt', [])])
        if not ev:
            continue
        marks = [s['start'] + s.get('td', 0)] + ev + [s['end']]
        a, b = max(zip(marks, marks[1:]), key=lambda ab: ab[1] - ab[0])
        if b - a > limit:
            said = [x['text'] for x in plan['beats'] if x['text'] and x['start'] < b and x['start'] + x['dur'] > a]
            out.append(f"{s['id']:6s} {b - a:4.1f}s 静止（{a:.1f}–{b:.1f}s）" + (f"  在念：{said[0][:16]}…" if said else ''))
    return out


def blank_starts(plan):
    """Slides that cut in on an empty page: nothing static, nothing carried, first entrance late."""
    out = []
    for si, s in enumerate(plan['slides'][1:], 1):
        if s.get('tr') != 'cut' or s.get('static', True) or s.get('carry'):
            continue
        ev = _slide_events(plan, si)
        if ev and ev[0] - s['start'] > 0.2:
            out.append(f"{s['id']:6s} 前 {ev[0] - s['start']:.2f}s 是空白页")
    return out


# ---------------------------------------------------------------- reference clips

CHARS = ' .:-=+*#%@'


def _probe(video):
    if not host.ffprobe():  # a bundled ffmpeg comes without ffprobe: read the banner of `ffmpeg -i`
        err = subprocess.run([host.ffmpeg(), '-hide_banner', '-i', str(video)], capture_output=True, text=True,
                             encoding='utf-8', errors='replace').stderr
        dur = re.search(r'Duration: (\d+):(\d+):([\d.]+)', err)
        vid = re.search(r'Video:.*?, (\d{2,5})x(\d{2,5})[ ,].*?([\d.]+) fps', err)
        if not (dur and vid):
            raise RuntimeError(f'cannot read {video}: {err.strip()[-300:]}')
        h, m, sec = dur.groups()
        return {'width': int(vid[1]), 'height': int(vid[2]), 'fps': round(float(vid[3]), 2),
                'duration': round(int(h) * 3600 + int(m) * 60 + float(sec), 2)}
    r = subprocess.run(['ffprobe', '-v', 'error', '-select_streams', 'v:0', '-show_entries',
                        'stream=width,height,r_frame_rate:format=duration', '-of', 'json', str(video)],
                       capture_output=True, text=True, encoding='utf-8', errors='replace', check=True)
    j = json.loads(r.stdout)
    st = j['streams'][0]
    num, _, den = st['r_frame_rate'].partition('/')
    return {'width': st['width'], 'height': st['height'], 'fps': round(float(num) / float(den or 1), 2),
            'duration': round(float(j['format']['duration']), 2)}


def _frames(video, fps, width, tmp):
    d = Path(tmp)
    if d.exists():
        shutil.rmtree(d)
    d.mkdir(parents=True)
    subprocess.run([host.ffmpeg(), '-v', 'error', '-y', '-i', str(video), '-vf', f'fps={fps},scale={width}:-2', str(d / 'f_%05d.png')],
                   check=True)
    return sorted(d.glob('f_*.png'))


def _suggest(colors):
    """use_theme() colours read off a reference palette: ground = most common, ink = best contrast on it,
    primary = the most saturated of the rest."""
    import colorsys
    from theme import contrast
    if not colors:
        return {}
    bg = colors[0]['hex']
    rest = [c['hex'] for c in colors[1:]]
    ink = max(rest or ['#111111'], key=lambda h: contrast(h, bg))
    sat = lambda h: colorsys.rgb_to_hsv(*[int(h[i:i + 2], 16) / 255 for i in (1, 3, 5)])[1]  # noqa: E731
    accents = [h for h in rest if h != ink and sat(h) > 0.25]
    out = {'background': bg, 'ink': ink if contrast(ink, bg) >= 4.5 else ('#111111' if contrast('#111111', bg) > contrast('#FFFFFF', bg) else '#FFFFFF')}
    if accents:
        out['primary'] = max(accents, key=sat)
    return out


def analyze_ref(video, out):
    """Measure a reference clip: energy map, stillness, cuts, bursts, palette, contact sheets."""
    from PIL import Image, ImageDraw
    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    info = _probe(video)
    fps = 12
    files = _frames(video, fps, 320, out / '_e')
    prev, diffs = None, []
    for f in files:
        a = np.asarray(Image.open(f).convert('L'), dtype=np.float32)
        diffs.append(0.0 if prev is None else float(np.abs(a - prev).mean()))
        prev = a
    d = np.array(diffs)
    rows = [f'{r / fps:6.1f}s |' + ''.join(CHARS[min(9, int(v / 3))] for v in d[r:r + fps * 4]) + '|' for r in range(0, len(d), fps * 4)]
    med = np.median(d[d > 0]) if (d > 0).any() else 0
    # a cut is an isolated spike: big against its neighbours (a fade or a move is spread over frames)
    cuts = [round(i / fps, 2) for i in range(1, len(d) - 1)
            if d[i] > max(1.2, 3 * med) and d[i] > 3 * max(d[i - 1], d[i + 1], 0.15)]
    big = [i / fps for i in range(len(d)) if d[i] > 8]
    bursts = []
    for t in big:
        n = sum(1 for u in big if t <= u < t + 1.5)
        if n >= 3 and not (bursts and t < bursts[-1][1]):
            bursts.append([round(t, 2), round(t + 1.5, 2)])
    quiet, run = 0, 0
    for v in d:
        run = run + 1 if v < 0.8 else 0
        quiet = max(quiet, run)
    shots = [0.0] + cuts + [info['duration']]
    shot_lens = [b - a for a, b in zip(shots, shots[1:]) if b > a]
    cv = float(np.std(shot_lens) / np.mean(shot_lens)) if len(shot_lens) > 1 else 0.0
    summary = {**info, 'still': round(float((d < 0.5).mean()), 3), 'low': round(float((d < 2).mean()), 3),
               'cuts': cuts, 'shots': len(shot_lens), 'shot_cv': round(cv, 2), 'bursts': bursts,
               'longest_quiet_s': round(quiet / fps, 2)}
    # contact sheets: 2 frames a second, 6 x 4 per sheet
    sheet_files = files[::fps // 2]
    tw = 320
    th = Image.open(sheet_files[0]).height
    for k in range(0, len(sheet_files), 24):
        group = sheet_files[k:k + 24]
        sh = Image.new('RGB', (tw * 6, th * math.ceil(len(group) / 6)), 'white')
        for i, f in enumerate(group):
            im = Image.open(f).convert('RGB')
            ImageDraw.Draw(im).text((6, 4), f'{(k + i) / 2:.1f}s', fill='white')
            sh.paste(im, ((i % 6) * tw, (i // 6) * th))
        sh.save(out / f'sheet_{k // 24:02d}.jpg', quality=85)
    # palette: the ground first, then what sits on it, counted separately so small type and accents still show
    pick = files[::max(1, len(files) // 36)][:36]
    px = np.concatenate([np.asarray(Image.open(f).convert('RGB'), dtype=np.uint8).reshape(-1, 3) for f in pick])
    total_px = len(px)

    def clusters(arr, n):
        side = int(np.ceil(np.sqrt(len(arr))))
        img = np.zeros((side * side, 3), np.uint8)
        img[:len(arr)] = arr
        q = Image.fromarray(img.reshape(side, side, 3)).quantize(colors=n, method=Image.Quantize.MEDIANCUT)
        pal, out = q.getpalette(), []
        for c, i in sorted(q.getcolors(), reverse=True):
            rgb = np.array(pal[i * 3:i * 3 + 3], dtype=float)
            for m in out:  # near-identical colours (anti-aliasing, gradients) count as one
                if np.abs(m['rgb'] - rgb).max() < 30:
                    m['n'] += c
                    break
            else:
                out.append({'rgb': rgb, 'n': c})
        return sorted(out, key=lambda m: -m['n'])

    ground = clusters(px[::7], 12)[0]['rgb']
    fg = px[np.abs(px.astype(float) - ground).max(1) > 48]
    merged = [{'rgb': ground, 'n': total_px - len(fg)}] + (clusters(fg[::max(1, len(fg) // 400000)], 16) if len(fg) else [])
    scale = len(fg) / max(1, sum(m['n'] for m in merged[1:]))
    colors = [{'hex': '#%02X%02X%02X' % tuple(int(v) for v in m['rgb']), 'share': round(m['n'] * (1 if k == 0 else scale) / total_px, 4)}
              for k, m in enumerate(merged) if k == 0 or m['n'] * scale / total_px >= 0.0005][:8]
    summary['palette'] = colors
    summary['suggest'] = _suggest(colors)
    sw = Image.new('RGB', (len(colors) * 120, 150), 'white')
    dr = ImageDraw.Draw(sw)
    for i, c in enumerate(colors):
        dr.rectangle((i * 120, 0, i * 120 + 118, 110), fill=c['hex'])
        dr.text((i * 120 + 6, 116), f"{c['hex']} {c['share']:.0%}", fill='black')
    sw.save(out / 'palette.png')
    (out / 'energy.txt').write_text('\n'.join(rows) + '\n', encoding='utf-8')
    (out / 'summary.json').write_text(json.dumps(summary, ensure_ascii=False, indent=1), encoding='utf-8')
    shutil.rmtree(out / '_e')
    lines = [f"{Path(video).name}: {info['duration']}s {info['width']}x{info['height']} {info['fps']}fps",
             f"静止 {summary['still']:.0%}（几乎不动 {summary['low']:.0%}），最长安静 {summary['longest_quiet_s']}s",
             f"剪辑点 {len(cuts)} 个，镜头长短变化系数 {cv:.2f}，爆发段 {len(bursts)} 个" + (f"：{bursts}" if bursts else ''),
             '配色：' + ' '.join(f"{c['hex']}({c['share']:.1%})" for c in colors),
             '建议：use_theme(' + ', '.join(f"{k}='{v}'" for k, v in summary['suggest'].items()) + ')  # 再按需要补 secondary / cover', '', *rows]
    return lines
