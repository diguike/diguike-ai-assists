"""Episode builder: narration -> timeline -> audio mix -> frames -> mp4.

usage: studio <episode> [step ...]          (the repo's CLI; see cli.py)
       python engine/build.py <episode_dir> [step ...]

An episode dir holds the sources (episode.py, data/, optional assets/); builds
write intermediates to work/ and deliverables to out/, both git-ignored.

steps
  tts      synthesise narration, one request per slide so prosody flows across lines
           (META voice 'myvoice' = a cloned voice via the local myvoice-tts CLI; otherwise an Edge voice)
  lint     edge voices: polyphone readings + odd word grouping; myvoice: ASR read-back,
           number readings, timing glitches -> lint.txt
  plan     timeline, subtitles (.srt), narration.wav, plan.json
  audio    background music + sound effects + final mix (mix.wav, out/音轨/)
  stills   final-state PNG of every slide, PDF, covers, work/contact.jpg (no TTS needed),
           plus work/layout.txt: boxes that leave the canvas, overlap, overflow or cover the subtitles
  render   all frames (Chrome) -> frames/
  video    frames + mix.wav -> <name>.mp4
  preview  <slide_id> [slide_id2]  quick mp4 of a slide range -> work/preview.mp4
  silent   [slide_id [slide_id2]]  motion only, no voice: timings estimated from the script
           -> work/silent/silent.mp4 (try a look or a transition in a minute, before any TTS)
  rhythm   shot lengths, carries across slide changes, stillness, pages that sit idle -> work/rhythm.txt
  freeze   mark out/ as published (out/.frozen): later builds write to work/out/ instead
  all      tts plan audio stills render video
  check    tts lint plan stills rhythm  (everything to review before the long render)
"""
import asyncio
import hashlib
import importlib.util
import json
import math
import os
import re
import subprocess
import sys
import time
import wave
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import numpy as np

ENGINE = Path(__file__).resolve().parent
REPO = ENGINE.parent
sys.path.insert(0, str(ENGINE))

import audio as A  # noqa: E402
import deck  # noqa: E402
import host  # noqa: E402
import narration  # noqa: E402
import pron  # noqa: E402
from theme import ASSETS, T  # noqa: E402

FPS = 30
SR = 24000            # TTS sample rate
TRANS = 0.35          # slide cross-fade (plans written before per-slide transitions)
LEAD_FIRST = 0.5      # cover hold before first line
LEAD = 0.45           # new slide -> first line (longer when the transition is)
SLIDE_TAIL = 0.45     # last line -> next slide
WORKERS = max(2, min(10, (os.cpu_count() or 4) - 2))
TYPE_CPS = 15
DUR = {'fade': .4, 'pop': .45, 'draw': .45, 'wipe': .5, 'growY': .5, 'growX': .6,
       'rise': .6, 'mask': .55, 'zoom': .45, 'blur': .6, 'slide': .5, 'count': 1.2, 'marker': .5, 'cut': .01,
       'soft': .8}
SILENT = False        # `silent` step: estimated timings, no voice (motion preview)
PUNCT = '，。；？！：、,;?!:'
DEFAULTS = {'voice': 'myvoice', 'myvoice': 'diguike', 'rate': '+22%', 'speed': 1.0, 'takes': 2, 'pron': {},
            'lead': LEAD, 'tail': SLIDE_TAIL, 'gaps': None, 'caps': None,
            'bgm': True, 'bgm_seed': 11, 'bgm_lu': -21.0, 'duck_db': 4.0, 'sfx': True, 'sfx_db': 0.0,
            **host.CONF.get('defaults', {})}

SRC = WORK = OUT = EP = NAME = TTS_DIR = FRAMES = None
VOICE_QC = {}


def load_episode(ep_dir, sub=None):
    """sub: build into work/<sub>/ and keep out/ untouched (the silent preview)."""
    global SRC, WORK, OUT, EP, NAME, TTS_DIR, FRAMES
    SRC = Path(ep_dir).resolve()
    if not (SRC / 'episode.py').exists():
        sys.exit(f'no episode.py in {SRC}')
    sys.path.insert(0, str(SRC))  # episode-local helper modules
    spec = importlib.util.spec_from_file_location('episode', SRC / 'episode.py')
    EP = importlib.util.module_from_spec(spec)
    sys.modules['episode'] = EP
    spec.loader.exec_module(EP)
    NAME = EP.META.get('name') or SRC.name
    WORK, OUT = SRC / EP.META.get('work_dir', 'work'), SRC / 'out'
    if sub:
        WORK = OUT = WORK / sub
    elif frozen():  # published: plan / audio / stills / video would overwrite the delivered files
        OUT = WORK / 'out'
        print(f'out/ 已冻结（{frozen()}），这次的 srt、口播稿、封面、成片都写到 work/out/。'
              '确定要换掉已发布的文件，先删掉 out/.frozen', file=sys.stderr)
    WORK.mkdir(parents=True, exist_ok=True)
    OUT.mkdir(exist_ok=True)
    TTS_DIR = WORK / 'tts'
    FRAMES = WORK / 'frames'
    link_assets()


def frozen():
    """Why out/ must not be rewritten (an episode that has been published), or ''."""
    f = SRC / 'out' / '.frozen'
    if f.exists():
        return (f.read_text(encoding='utf-8').strip().splitlines() or ['out/.frozen'])[0]
    return '有发布快照/' if (SRC / '发布快照').exists() else ''


def cmd_freeze():
    out = SRC / 'out'
    mp4 = out / f'{NAME}.mp4'
    if not mp4.exists():
        sys.exit(f'freeze: no {mp4.name} in out/ yet (run all first)')
    sha = hashlib.sha256(mp4.read_bytes()).hexdigest()
    (out / '.frozen').write_text(f'{time.strftime("%Y-%m-%d")} 冻结 {mp4.name} sha256 {sha[:16]}\n', encoding='utf-8')
    print(f'freeze ok: out/ is read-only for later builds ({mp4.name} {sha[:16]})')


def link_assets():
    """work/assets: the repo's shared assets plus the episode's own assets/, as symlinks (links or copies on Windows).

    The deck HTML lives in work/ and refers to everything as assets/<file>.
    """
    import shutil
    dst = WORK / 'assets'
    if dst.is_symlink() or dst.is_file():
        dst.unlink()
    dst.mkdir(exist_ok=True)
    for old in dst.iterdir():
        if old.is_symlink() or old.is_file():
            old.unlink()
        elif old.is_dir():
            shutil.rmtree(old)
    for src_dir in (ASSETS, SRC / 'assets'):
        if src_dir.is_dir():
            for f in src_dir.iterdir():
                if not f.name.startswith('.'):
                    host.place(f.resolve(), dst / f.name)


def chrome():
    """Installed Chrome or Edge, or None for Playwright's own Chromium (setup.sh installs it)."""
    return host.browser()


def ffmpeg():
    exe = host.ffmpeg()
    if not exe:
        sys.exit('ffmpeg not found: install it (brew install ffmpeg / winget install ffmpeg) or pip install imageio-ffmpeg')
    return exe


def open_page(pw, html_path, size):
    """Browser page on a deck/cover HTML file with the theme font verified."""
    br = pw.chromium.launch(executable_path=chrome(), args=['--font-render-hinting=none'])
    pg = br.new_page(viewport={'width': size[0], 'height': size[1]}, device_scale_factor=1)
    pg.goto(Path(html_path).as_uri())
    ready = pg.evaluate('window.__ready')
    if not ready['ok']:
        br.close()
        raise RuntimeError(f"font '{ready['font']}' failed to load (see the theme's font files under assets/); frames would use a fallback font")
    return br, pg


def meta(k):
    return EP.META.get(k, DEFAULTS[k])


def run(cmd, **kw):
    return subprocess.run(cmd, check=True, **kw)


# ---------------------------------------------------------------- TTS

def slide_rate(s):
    return getattr(s, 'rate', None) or meta('rate')


def beat_tts(b):
    t = pron.normalize(b['tts'] or b['text'], meta('pron'))
    # a beat ending in a closing quote or bracket (「……叫“复利”」) still needs a mark, or the next beat runs on
    if t and t.rstrip('”’」』）)"\'')[-1:] not in PUNCT:
        t += '，'
    return t


def runs_on(s):
    """The slide's narration stops mid-sentence: its last spoken beat ends on ，、：…… or no mark, and the
    next slide finishes the sentence. The slide change then gets a comma's pause, not a sentence's: a
    full lead and tail there split one sentence in two (「打工皇帝……」 2.4 s 「轮到它们拿主意」, 2026-10-31)."""
    said = [beat_tts(b) for b in s.beats if b.get('voiced', True) and beat_tts(b)]
    return bool(said) and not re.search(r'[。！？!?；;]$', said[-1].rstrip(' 」』”"’）)'))


def voiced(s):
    """The beats of a slide that are spoken (beats with text=None, dur=... are silent)."""
    return [b for b in s.beats if b.get('voiced', True)]


def novoice():
    """META voice None: no narration at all (a promo cut to music)."""
    return meta('voice') is None


def para(s):
    """TTS text of a slide plus each spoken beat's char span in it."""
    parts = [beat_tts(b) for b in voiced(s)]
    spans, pos = [], 0
    for p in parts:
        spans.append((pos, pos + len(p)))
        pos += len(p)
    return ''.join(parts), spans


def tts_key(text, rate):
    return hashlib.sha1(f"{meta('voice')}|{rate}|{text}".encode()).hexdigest()[:16]


MYVOICE = 'myvoice'


def myvoice():
    return meta('voice') == MYVOICE


def myvoice_cli():
    import shutil
    exe = shutil.which('myvoice-tts') or str(Path.home() / '.local' / 'bin' / 'myvoice-tts')
    if not Path(exe).exists():
        sys.exit("myvoice-tts not found (see ~/.claude/skills/myvoice-tts); or set META 'voice' to an edge voice")
    return exe


_VOICE_INFO = {}


def myvoice_info():
    """{name, id, dir} of the cloned voice META 'myvoice' names (myvoice-tts --voice-info, no model load).

    The id hashes the voice's reference clip, transcript and speaker clips; with the tool's version
    it goes into every narration cache key, so a changed reference or a new take-picking rule
    re-synthesises instead of reusing old audio."""
    name = meta('myvoice')
    if name not in _VOICE_INFO:
        res = subprocess.run([myvoice_cli(), '--voice-info', '--voice', name], capture_output=True, text=True, encoding='utf-8', errors='replace')
        if res.returncode:
            sys.exit(f"myvoice-tts --voice-info failed for voice {name!r} (an older myvoice-tts? update it, "
                     f"or check META 'myvoice'):\n{res.stderr.strip()[-400:]}")
        _VOICE_INFO[name] = json.loads(res.stdout.strip().splitlines()[-1])
    return _VOICE_INFO[name]


def _pct(rate):
    return float(rate.strip().rstrip('%')) / 100


def slide_speed(s):
    """Cloned-voice tempo for a slide (1.0 = the clone's own pace, about edge +22%).

    Per-slide `rate` is written in edge percentages relative to META['rate'], so a
    slide marked '+12%' in a '+22%' episode plays at 1.12 / 1.22 of META['speed'].
    """
    sp = meta('speed')
    if getattr(s, 'rate', None):
        sp *= (1 + _pct(s.rate)) / (1 + _pct(meta('rate')))
    return round(sp, 3)


def slide_takes(s):
    return getattr(s, 'takes', None) or meta('takes')


def slide_key(s):
    """Cache key of a slide's narration audio in tts/."""
    text = para(s)[0]
    if myvoice():  # the voice, takes and tempo change the audio, so they are part of the key
        v = myvoice_info()
        return hashlib.sha1(f"{MYVOICE}|{v['name']}|{v['id']}|{v.get('engine', '')}|t{slide_takes(s)}|x{slide_speed(s)}|{text}".encode()).hexdigest()[:16]
    return tts_key(text, slide_rate(s))


async def synth(text, rate, sem, cache=None):
    cache = cache or TTS_DIR
    key = tts_key(text, rate)
    mp3, js = cache / f'{key}.mp3', cache / f'{key}.json'
    if mp3.exists() and js.exists():
        return key
    import edge_tts
    async with sem:
        for attempt in range(6):
            try:
                com = edge_tts.Communicate(text, meta('voice'), rate=rate, boundary='WordBoundary')
                audio, events = bytearray(), []
                async for ch in com.stream():
                    if ch['type'] == 'audio':
                        audio += ch['data']
                    elif ch['type'] == 'WordBoundary':
                        events.append([ch['offset'] / 1e7, ch['duration'] / 1e7, ch['text']])
                # the service sometimes ends a stream early; the mp3 is 48 kbps = 6000 B/s
                if not events or len(audio) / 6000 < events[-1][0] + events[-1][1] - 0.05:
                    raise RuntimeError('truncated stream')
                mp3.write_bytes(bytes(audio))
                js.write_text(json.dumps({'text': text, 'rate': rate, 'events': events}, ensure_ascii=False), encoding='utf-8')
                return key
            except Exception as e:  # network hiccups
                print('tts retry', attempt, repr(e)[:80])
                await asyncio.sleep(1.5 + attempt * 2)
    raise RuntimeError(f'tts failed: {text}')


def tts_myvoice():
    """Cloned voice: one batch for the local myvoice-tts CLI (writes the same mp3 + json as edge)."""
    batches = {}  # takes -> jobs; the CLI takes --takes per batch
    for s in EP.SLIDES:
        if not voiced(s):
            continue
        out = TTS_DIR / f'{slide_key(s)}.mp3'
        if not (out.exists() and out.with_suffix('.json').exists()):
            batches.setdefault(slide_takes(s), []).append(
                {'text': para(s)[0], 'out': str(out), 'rate': slide_rate(s), 'speed': slide_speed(s)})
    for takes, jobs in batches.items():
        lst = TTS_DIR / f'myvoice_jobs_t{takes}.jsonl'
        lst.write_text(''.join(json.dumps(j, ensure_ascii=False) + '\n' for j in jobs), encoding='utf-8')
        audio_min = sum(len(j['text']) for j in jobs) / 5.8 / 60
        print(f"tts (myvoice): {len(jobs)} slides, ~{audio_min:.1f} min of audio, "
              f"~{audio_min * 0.6 * takes + 0.5:.0f} min to synthesise (takes={takes})", flush=True)
        run([myvoice_cli(), '--batch', str(lst), '--takes', str(takes), '--voice', myvoice_info()['name']])
    print('tts ok (myvoice):', len(EP.SLIDES), 'slides,', sum(len(s.beats) for s in EP.SLIDES), 'beats')


def cmd_tts():
    TTS_DIR.mkdir(exist_ok=True)
    if novoice():
        print('tts: no narration (META voice None)')
        return
    if myvoice():
        return tts_myvoice()
    jobs = [(para(s)[0], s) for s in EP.SLIDES if voiced(s)]

    async def main():
        sem = asyncio.Semaphore(6)
        await asyncio.gather(*[synth(t, slide_rate(s), sem) for t, s in jobs])

    asyncio.run(main())
    print('tts ok:', len(jobs), 'slides,', sum(len(s.beats) for s in EP.SLIDES), 'beats')


def load_mp3(path, sr=SR):
    raw = run([ffmpeg(), '-v', 'error', '-i', str(path), '-f', 'f32le', '-ac', '1', '-ar', str(sr), '-'],
              capture_output=True).stdout
    return np.frombuffer(raw, dtype=np.float32)


def word_spans(text, events):
    """Word-boundary events -> [(char_start, char_end, t0, t1)]."""
    out, k = [], 0
    for off, du, w in events:
        w = w.strip()
        if not w:
            continue
        j = text.find(w, k)
        if j < 0 or j - k > 12:
            continue
        out.append((j, j + len(w), off, off + du))
        k = j + len(w)
    return out


def char_times(n, words):
    st = [None] * n
    for a, b, t0, t1 in words:
        for q in range(a, b):
            st[q] = t0 + (t1 - t0) * (q - a) / (b - a)
    last = 0.0
    for i in range(n):
        if st[i] is None:
            st[i] = last
        else:
            last = st[i]
    return st


def slide_audio(s):
    """Cut a slide's narration into beats.

    Returns (samples, [{'start', 'dur', 'text', 'ct'}]) with times relative to
    the slide audio; ct = per-char start times of the beat's TTS text.
    """
    if SILENT or novoice() or not voiced(s):
        return silent_audio(s)
    if len(voiced(s)) < len(s.beats):
        return mixed_audio(s)
    text, spans = para(s)
    key = slide_key(s)
    x = load_mp3(TTS_DIR / f'{key}.mp3')
    words = word_spans(text, json.loads((TTS_DIR / f'{key}.json').read_text(encoding='utf-8'))['events'])
    qc = {'cache_key': key}
    if myvoice() and EP.META.get('voice_level', True):
        target = EP.META.get('voice_level_db', -21.0)
        x, qc['sentences'] = narration.level_sentences(x, SR, text, words, target_db=target)
        x, qc['ride'] = narration.ride(x, SR, target_db=target)  # a long sentence that fades out
    if myvoice() and meta('caps') is not False:  # pauses held too long for their mark (quiet middle taken out)
        x, words, qc['held'] = narration.close_pauses(x, SR, text, words, {**narration.CAPS, **(meta('caps') or {})})
    if myvoice() and meta('gaps') is not False:  # pauses too short for their mark (lengthened, never cut)
        x, words, qc['pauses'] = narration.open_pauses(x, SR, text, words, {**narration.GAPS, **(meta('gaps') or {})})
    if myvoice() and EP.META.get('breaths', True):  # a loud inhale before a sentence, turned down
        x, qc['breaths'] = narration.tame_breaths(x, SR, text, words)
    if myvoice() and EP.META.get('floor', True):  # the hiss and hum the clone copied, lowered between words
        x, qc['floor'] = narration.quiet_floor(x, SR, words)
    if len(qc) > 1:
        VOICE_QC[s.id] = qc
    ct = char_times(len(text), words)
    bounds = []
    for a, b in spans:
        ws = [w for w in words if a <= w[0] < b]
        if not ws:
            raise ValueError(f'{s.id}: no word timing for {text[a:b]}')
        bounds.append((ws[0][2], ws[-1][3]))
    head, tail = narration.trim_bounds(x, SR, words)
    cuts = [head] + [(bounds[k][1] + bounds[k + 1][0]) / 2 for k in range(len(bounds) - 1)] + [tail]
    out, beats, t = [], [], 0.0
    ramp = np.linspace(0, 1, int(.006 * SR), dtype=np.float32)  # around silence inserted between beats
    for k, b in enumerate(s.beats):
        seg = x[int(cuts[k] * SR):int(cuts[k + 1] * SR)].copy()
        if out and not out[-1].any() and len(seg) > len(ramp):
            seg[:len(ramp)] *= ramp
        shift = t - cuts[k]
        a, e = spans[k]
        beats.append({'start': bounds[k][0] + shift, 'dur': bounds[k][1] - bounds[k][0],
                      'text': text[a:e], 'ct': [c + shift - (bounds[k][0] + shift) for c in ct[a:e]]})
        out.append(seg)
        t += len(seg) / SR
        if b['pause'] is not None and k < len(s.beats) - 1:
            extra = max(0.0, b['pause'] - (bounds[k + 1][0] - bounds[k][1]))
            if extra > 0:  # the cut sits in room tone, not at zero: fade into and out of the silence
                if len(seg) > len(ramp):
                    seg[-len(ramp):] *= ramp[::-1]
                out.append(np.zeros(int(extra * SR), np.float32))
            t += extra
    return narration.soften_quiet_edges(np.concatenate(out), SR), beats


def silent_audio(s):
    """slide_audio without a voice: a beat lasts its dur=, or as long as the clone takes to say it (about 5.6 chars/s)."""
    beats, t = [], 0.0
    for k, b in enumerate(s.beats):
        seg = beat_tts(b) if b.get('voiced', True) else ''
        if b.get('dur'):
            dur = float(b['dur'])
        else:
            n = len(re.findall(r'[\u4e00-\u9fffA-Za-z0-9%]', seg)) or 1
            dur = n / 5.6 + 0.22 * len(re.findall(r'[，、；：,;]', seg.rstrip(PUNCT)))
        beats.append({'start': t, 'dur': dur, 'text': seg, 'ct': [dur * i / max(1, len(seg)) for i in range(len(seg))]})
        t += dur + (0 if b.get('dur') else 0.32) + ((b['pause'] or 0) if k < len(s.beats) - 1 else 0)
    return np.zeros(int(round(t * SR)), np.float32), beats


def mixed_audio(s):
    """A slide with spoken and silent beats: the spoken ones keep the slide's one TTS take
    (cut apart as usual), each silent beat is that many seconds of quiet in between."""
    import copy
    talk = copy.copy(s)
    talk.beats = voiced(s)
    x, vb = slide_audio(talk)
    # each spoken beat's slice of x, cut halfway between neighbouring beats
    cuts = [0.0] + [(vb[k]['start'] + vb[k]['dur'] + vb[k + 1]['start']) / 2 for k in range(len(vb) - 1)] + [len(x) / SR]
    out, beats, t, k = [], [], 0.0, 0
    for b in s.beats:
        if b.get('voiced', True):
            seg = x[int(cuts[k] * SR):int(cuts[k + 1] * SR)]
            beats.append({**vb[k], 'start': t + vb[k]['start'] - cuts[k]})
            out.append(seg)
            t += len(seg) / SR
            k += 1
        else:
            d = float(b['dur']) + (b['pause'] or 0)
            beats.append({'start': t + 0.05, 'dur': float(b['dur']), 'text': '', 'ct': []})
            out.append(np.zeros(int(d * SR), np.float32))
            t += d
    return np.concatenate(out), beats


# ---------------------------------------------------------------- lint

LINT_SKIP = '和大看中都'  # near-always read right; checking them costs a lot of requests
LINT_CACHE = Path.home() / '.cache' / 'video-studio' / 'lint'  # shared across episodes


def tool_python():
    """Interpreter of the myvoice-tts tool env (has faster-whisper, zhconv, wetext), or None."""
    exe = Path(myvoice_cli()).resolve()
    head = exe.read_text(errors='ignore')[:400]
    m = re.match(r'#!(\S*python\S*)', head) or re.search(r'exec\s+(\S*python\S*)', head)
    return m.group(1) if m and Path(m.group(1)).exists() else None


def asr_readback(paths):
    """{mp3 path: ASR result} via asr_readback.py in the tool env, cached next to each mp3."""
    out, todo = {}, []
    for p in paths:
        c = Path(p).with_suffix('.asr.json')
        if c.exists():
            out[p] = json.loads(c.read_text(encoding='utf-8'))
        else:
            todo.append(p)
    if todo:
        py = tool_python()
        if not py:
            print('lint: myvoice-tts tool env not found, skipping ASR read-back')
            return out
        print(f'lint: ASR read-back of {len(todo)} slides (faster-whisper small, ~{len(todo) * 4 // 60 + 1} min)', flush=True)
        res = run([py, '-I', str(ENGINE / 'asr_readback.py'), *todo], capture_output=True, text=True, encoding='utf-8', errors='replace').stdout
        for line in res.splitlines():
            r = json.loads(line)
            Path(r['path']).with_suffix('.asr.json').write_text(json.dumps(r, ensure_ascii=False), encoding='utf-8')
            out[r['path']] = r
    return out


def lint_myvoice():
    """Cloned voice QA: ASR read-back, how numbers were read, timing glitches -> lint.txt.

    The homophone test used for edge voices needs a deterministic voice; the clone
    samples, so a variant never reproduces the original. Instead check what a
    listener would catch: words dropped, added or said differently (faster-whisper
    read-back compared as toneless pinyin), the spoken form of digits, and
    stretched syllables or dead air inside a sentence.
    """
    import difflib
    slides = []
    for s in EP.SLIDES:
        if not voiced(s):
            continue
        text, spans = para(s)
        mp3 = TTS_DIR / f'{slide_key(s)}.mp3'
        slides.append((s, text, spans, str(mp3), json.loads(mp3.with_suffix('.json').read_text(encoding='utf-8'))))
    asr = asr_readback([m for *_, m, _ in slides])
    heard, readings, timing, rates = [], {}, [], {}
    for s, text, spans, mp3, js in slides:
        spoken = js.get('spoken', text)
        # spoken index -> text index, to name the beat a problem sits in
        sm = difflib.SequenceMatcher(None, text, spoken, autojunk=False)
        to_text = [0] * (len(spoken) + 1)
        for tag, i1, i2, j1, j2 in sm.get_opcodes():
            for j in range(j1, j2):
                to_text[j] = i1 + (j - j1) * max(0, i2 - i1 - 1) // max(1, j2 - j1)
            if tag != 'equal':
                a, b = i1, i2
                while a > 0 and re.match(r'[\d.%]', text[a - 1]):
                    a -= 1
                while b < len(text) and re.match(r'[\d.%]', text[b]):
                    b += 1
                if text[a:b].strip(PUNCT):
                    readings.setdefault(text[a:b], (spoken[j1 - (i1 - a):j2 + (b - i2)], s.id))
        to_text[len(spoken)] = len(text)

        def beat_of(i):
            return next(k for k, (a, b) in enumerate(spans) if i < b or k == len(spans) - 1)

        if mp3 in asr:
            cer, diffs = pron.readback_diff(spoken, asr[mp3]['norm'])
            for a, b, h in diffs:
                ctx = spoken[max(0, a - 6):a] + '[' + spoken[a:b] + ']' + spoken[b:b + 6]
                heard.append(f'{s.id:5s} b{beat_of(to_text[a]) + 1:<2d} {ctx}  -> 听成「{h}」')
            rates[s.id] = cer
        for q in js.get('takes', []):  # myvoice-tts keeps the best take even when every one failed
            if q.get('score', 0) >= 10:
                timing.append(f'{s.id:5s} 每一遍都失控或被截断（留了最好的一遍，去听）  {q["text"][:24]}')
            if q.get('lost'):
                timing.append(f'{s.id:5s} {q["tries"]} 遍都丢了最后一个字（去听；换个结尾的说法）  {q["text"][:24]}')
            if q.get('runon'):
                timing.append(f'{s.id:5s} {q["tries"]} 遍都在逗号处连读 {q["runon"]} 处  {q["text"][:24]}')
            if q.get('cut'):  # myvoice-tts 0.4.1 already let it die away over 90 ms; still worth a listen
                timing.append(f'{s.id:5s} {q["tries"]} 遍都在最后一个字还响着时结束（已做 90 ms 衰减，去听句尾）  {q["text"][:24]}')
        words = word_spans(text, js['events'])
        for (a, b, t0, t1), nxt in zip(words, words[1:] + [None]):
            w = text[a:b]
            if re.match(r'^[\u4e00-\u9fff]$', w) and t1 - t0 > 0.6:
                timing.append(f'{s.id:5s} b{beat_of(a) + 1:<2d} 拖音 {t1 - t0:.2f}s  {text[max(0, a - 6):a]}[{w}]{text[b:b + 6]}')
            # a sentence-final char the aligner could not find (0.02 s placeholder): the voice swallowed it
            # (mid-sentence placeholders are usually the aligner's own slips; read-back covers those)
            if (re.match(r'^[\u4e00-\u9fff]+$', w) and t1 - t0 < 0.04 * len(w)
                    and (b >= len(text) or text[b] in '。！？；')):
                timing.append(f'{s.id:5s} b{beat_of(a) + 1:<2d} 疑似吞字 {t1 - t0:.2f}s  {text[max(0, a - 6):a]}[{w}]{text[b:b + 6]}')
            if nxt and nxt[2] - t1 > 0.6 and not re.search(r'[。！？；]', text[b:nxt[0]]):
                timing.append(f'{s.id:5s} b{beat_of(b) + 1:<2d} 句中停顿 {nxt[2] - t1:.2f}s  '
                              f'{text[max(0, b - 6):b]}|{text[nxt[0]:nxt[0] + 6]}')
    lines = ['# 回读（ASR 听到的和稿子不一样的地方；whisper small 自己也会听错，去听这些位置）'] + (heard or ['（无）'])
    if rates:
        worst = sorted(rates.items(), key=lambda kv: -kv[1])[:5]
        lines += ['', '# 每页回读差异率（最高 5 页）'] + [f'{k:5s} {v:.1%}' for k, v in worst]
    lines += ['', '# 数字和符号的读法（核对一遍）'] + [f'{sid:5s} {o} -> {sp}' for o, (sp, sid) in readings.items()]
    lines += ['', '# 时间异常（单字超过 0.6 秒、句中停顿超过 0.6 秒、字短得像被吞掉）'] + (timing or ['（无）'])
    import polycheck  # read-back can't tell 验得了 le from liǎo; compare against each reading instead
    poly_lines, poly_bad = polycheck.run([(s.id, t, js['events'], m) for s, t, _, m, js in slides],
                                         myvoice_cli(), load_mp3, word_spans, voice=myvoice_info())
    lines += poly_lines
    (WORK / 'lint.txt').write_text('\n'.join(lines) + '\n', encoding='utf-8')
    total = sum(len(re.findall(r'[\u4e00-\u9fff]', js.get('spoken', t))) for _, t, _, _, js in slides)
    print(f'lint ok (myvoice): {len(heard)} read-back diffs in ~{total} syllables, {len(readings)} number readings, '
          f'{len(timing)} timing flags -> lint.txt')
    for ln in heard + timing + poly_bad:
        print('  ' + ln)


def cmd_lint():
    """Which reading did the voice use for each polyphone? See pron.poly_units."""
    if novoice():
        print('lint: no narration')
        return
    if myvoice():
        return lint_myvoice()
    LINT_CACHE.mkdir(parents=True, exist_ok=True)
    units = {}  # (rate, unit, k) -> {'exp', 'vs', 'where'}
    glitches = []
    for s in EP.SLIDES:
        if not voiced(s):
            continue
        text, _ = para(s)
        rate = slide_rate(s)
        key = tts_key(text, rate)
        words = word_spans(text, json.loads((TTS_DIR / f'{key}.json').read_text(encoding='utf-8'))['events'])
        for a, b in pron.seg_glitches(text, words):
            glitches.append(f'{s.id:5s} {text[max(0, a - 6):a]}[{text[a:b]}]{text[b:b + 6]}')
        for pos, unit, k, exp, vs in pron.poly_units(text, words, LINT_SKIP):
            u = units.setdefault((rate, unit, k), {'exp': exp, 'vs': vs, 'where': []})
            u['where'].append((s.id, text[max(0, pos - 6):pos] + f'[{text[pos]}]' + text[pos + 1:pos + 6]))
    n_req = sum(1 + len(u['vs']) for u in units.values())
    # a reading whose only homophones are rare chars cannot be tested (e.g. 更 gèng)
    print(f'lint: {sum(len(u["where"]) for u in units.values())} polyphones, {len(units)} distinct words, '
          f'{n_req} requests (cached across episodes)')

    async def gen():
        sem = asyncio.Semaphore(6)
        tasks = []
        for (rate, unit, k), u in units.items():
            tasks.append(synth(unit + '。', rate, sem, LINT_CACHE))
            tasks += [synth(v + '。', rate, sem, LINT_CACHE) for v in u['vs'].values()]
        await asyncio.gather(*tasks)

    asyncio.run(gen())

    def load(text, rate):
        return load_mp3(LINT_CACHE / f'{tts_key(text + "。", rate)}.mp3')

    rows = []
    for (rate, unit, k), u in units.items():
        exp = u['exp']
        best, margin, d = pron.judge_units(load(unit, rate), {r: load(v, rate) for r, v in u['vs'].items()}, SR)
        exact = d[best] < 0.3 and margin > 1.0
        if best == exp:
            verdict = 'ok' if exact or margin > 0.25 else 'unsure'
        else:
            verdict = 'MISMATCH' if exact or margin > 0.3 else 'unsure'
        rows.append((verdict, unit, k, exp, best, margin, d, u['where']))
    order = {'MISMATCH': 0, 'unsure': 1, 'ok': 2}
    rows.sort(key=lambda r: (order[r[0]], r[1]))
    lines = []
    for v, unit, k, exp, best, margin, d, where in rows:
        mark = unit[:k] + f'[{unit[k]}]' + unit[k + 1:]
        lines.append(f'{v:8s} {mark:10s} expect {exp:7s} voice {best:7s} margin {margin:5.2f}  ' +
                     ' '.join(f'{r}:{x:.2f}' for r, x in d.items()) +
                     f'   x{len(where)} {where[0][0]} {where[0][1]}')
    seg = ['', '# word groupings that straddle a dictionary word (reword, e.g. 博时标普 -> 博时的标普)'] + glitches
    (WORK / 'lint.txt').write_text('\n'.join(lines + seg) + '\n', encoding='utf-8')
    cnt = {key: sum(r[0] == key for r in rows) for key in order}
    print(f"lint ok: {cnt['MISMATCH']} mismatch, {cnt['unsure']} unsure, {cnt['ok']} ok, "
          f"{len(glitches)} grouping glitches -> lint.txt")
    for ln in lines:
        if ln.startswith('MISMATCH'):
            print('  ' + ln)
    for g in glitches:
        print('  GROUPING ' + g)


# ---------------------------------------------------------------- subtitles

def split_cues(text, maxlen=17):
    """Split a beat into subtitle cues; returns [(start, end)] char spans."""
    import jieba
    jieba.setLogLevel(60)
    spans, s = [], 0
    for i, ch in enumerate(text):
        if ch in PUNCT and ch != '、':  # keep an enumeration (金额、日期、发票号) on one cue
            if i > s:
                spans.append([s, i + 1])
            s = i + 1
    if s < len(text):
        spans.append([s, len(text)])

    def core_len(a, b):  # display width: Latin letters, digits and spaces are about half a CJK character
        return sum(0.5 if ord(c) < 128 else 1 for c in text[a:b].rstrip(PUNCT))

    merged = []
    for sp in spans:
        # a short lead-in joins the next piece, but never across the end of a clause (；。？！)
        if (merged and core_len(*merged[-1]) <= 5 and core_len(merged[-1][0], sp[1]) <= maxlen
                and text[merged[-1][1] - 1] not in '；;。？！?!'):
            merged[-1][1] = sp[1]
        else:
            merged.append(sp)
    out = []
    for a, b in merged:
        stack = [(a, b)]
        while stack:
            a, b = stack.pop(0)
            if core_len(a, b) <= maxlen:
                out.append((a, b))
                continue
            core_b = a + len(text[a:b].rstrip(PUNCT))
            mid = (a + core_b) / 2
            bounds, pos = set(), a
            for w in jieba.cut(text[a:core_b]):
                pos += len(w)
                bounds.add(pos)
            best = None
            for k in range(a + 4, core_b - 3):
                l, r = text[k - 1], text[k]
                if k not in bounds or re.match(r'[A-Za-z0-9.%+]', l) or re.match(r'[A-Za-z0-9.%+]', r):
                    continue
                # nor at the space that keeps a number with its unit (「40 / 个小时」)
                if (l == ' ' and re.match(r'[0-9%]', text[k - 2:k - 1])) or (r == ' ' and re.match(r'[0-9]', text[k + 1:k + 2])):
                    continue
                if r in '的了吗呢' or l in '“':
                    continue
                # an enumeration is cut after a 、 rather than inside one of its items
                score = (abs(k - mid) - (4 if l == '、' else 0) - (2 if l in '的了是在和就都也' else 0)
                         - (2 if r in '而但就也还和与或把被让从对是' else 0))
                if best is None or score < best[0]:
                    best = (score, k)
            if best:
                k = best[1]
            else:  # no good break: near the middle, but not inside a number or a Latin name (513100, Claude Code)
                inside = {i for m in re.finditer(r'[A-Za-z0-9.%+]+(?: [A-Za-z0-9.%+]+)*', text)
                          for i in range(m.start() + 1, m.end())}
                ok = [i for i in range(a + 1, core_b) if i not in inside]
                k = min(ok, key=lambda i: abs(i - mid)) if ok else int(mid)
            stack[0:0] = [(a, k), (k, b)]
    return out


def cue_display(t):
    t = t.strip().rstrip(PUNCT)
    return re.sub(r'[，。；？！：,;?!:]', ' ', t).strip()


def fmt_ts(t):
    ms = int(round(t * 1000))
    return f'{ms // 3600000:02d}:{ms // 60000 % 60:02d}:{ms // 1000 % 60:02d},{ms % 1000:03d}'


def write_srt(cues, path):
    lines = []
    for i, c in enumerate(cues, 1):
        lines += [str(i), f'{fmt_ts(c["start"])} --> {fmt_ts(c["end"] - 0.02)}', c['text'], '']
    path.write_text('\n'.join(lines), encoding='utf-8')


# ---------------------------------------------------------------- plan

def el_dur(eid):
    """Entrance duration; the motion preset's speed scales everything but typing."""
    e = deck.ELEM[eid]
    if e['a'] == 'type':
        return e['d'] or min(2.2, max(0.35, e['n'] / T.motion.get('type_cps', TYPE_CPS)))
    return (e['d'] or DUR[e['a']]) * T.motion.get('speed', 1.0)


def slide_trans(s, si):
    """(kind, seconds) of the transition into slide si; the first slide just appears."""
    return ('fade', 0.0) if si == 0 else (s.trans, s.trans_dur)


def _expo_io(u):
    if u <= 0 or u >= 1:
        return min(1.0, max(0.0, u))
    return 2 ** (20 * u - 10) / 2 if u < 0.5 else (2 - 2 ** (-20 * u + 10)) / 2


# camera moves: (curve, share of the preset's cam_dur). 'whip' is quick and hard in/out, 'snap' arrives fast and settles
CAM_MOVES = {'smooth': (lambda u: 4 * u ** 3 if u < 0.5 else 1 - (-2 * u + 2) ** 3 / 2, 1.0),
             'whip': (_expo_io, 0.55), 'snap': (lambda u: 1 - 2 ** (-10 * u) if u < 1 else 1.0, 0.8),
             'slow': (lambda u: -(math.cos(math.pi * u) - 1) / 2, 1.6)}


def _cam_lerp(seg, t, dur):
    t0, (x0, y0, z0), (x1, y1, z1, curve) = seg
    ease, k = CAM_MOVES[curve]
    u = min(1.0, max(0.0, (t - t0) / (dur * k)))
    e = ease(u)
    return x0 + (x1 - x0) * e, y0 + (y1 - y0) * e, math.exp(math.log(z0) + (math.log(z1) - math.log(z0)) * e)


def _shake(t, hits):
    """Decaying, deterministic camera shake from the hits [[t0, amp, dur], ...] (screen px)."""
    x = y = 0.0
    for t0, amp, d in hits:
        tau = t - t0
        if 0 < tau < d + 0.3:
            e = amp * math.exp(-6 * tau)
            x += e * math.sin(2 * math.pi * 17 * tau + t0)
            y += 0.7 * e * math.sin(2 * math.pi * 23 * tau + 2 * t0)
    return x, y


def cam_at(keys, t, W, H, dur, world=None, start=None, hits=()):
    """Camera [x, y, zoom] at time t from a slide's keys [[t0, x, y, zoom, curve], ...]; None when it sits at rest
    on the plain view.

    Each move starts from wherever the previous one had got to, zooms in log space,
    and the view is kept on the canvas (the slide, or its world)."""
    hx, hy = _shake(t, hits)
    keys = [k if len(k) == 5 else list(k) + ['smooth'] for k in keys or []]
    if not start and not (keys and t >= keys[0][0]) and not (hx or hy):
        return None
    pos, seg = tuple(start) if start else (W / 2, H / 2, 1.0), None
    for t0, *to in keys:
        if t0 > t:
            break
        if seg:
            pos = _cam_lerp(seg, t0, dur)
        seg = (t0, pos, tuple(to))
    x, y, z = _cam_lerp(seg, t, dur) if seg else pos
    ww, wh = world or (W, H)
    hw, hh = W / (2 * z), H / (2 * z)
    x = min(max(x, hw), ww - hw) if ww >= 2 * hw else ww / 2
    y = min(max(y, hh), wh - hh) if wh >= 2 * hh else wh / 2
    return [round(x - hx / z, 1), round(y - hy / z, 1), round(z, 4)]


def acts_at(plan, sis, t):
    """{action index: [seconds since it started, start time]} for the actions on slides sis at time t.

    A finished emphasis is left out; a finished move / exit / focus is held at its
    duration (so frames after it stay identical) and the start time says which of
    two finished actions came last (see runtime applyCues)."""
    q = {}
    for k, (t0, d, si, persist, loop) in plan.get('acts', {}).items():
        if si not in sis or t < t0:
            continue
        tau = t - t0
        if loop or tau <= d:
            q[k] = [round(tau, 3), t0]
        elif persist:
            q[k] = [d, t0]
    return q


def slide_elems(slide):
    ids = re.findall(r'\bid="([^"]+)"[^>]*\bdata-a="', slide.html())
    return [i for i in ids if i in deck.ELEM]


def has_static(slide):
    """Does the slide show anything from its first frame (an element drawn without an entrance)?"""
    return any('data-a=' not in tag for tag in re.findall(r'<(?:div|img|svg|span)\b[^>]*\bclass="[^"]*\babs\b[^>]*>', slide.html()))


def write_wav(path, x, sr):
    x = np.atleast_2d(np.clip(x, -1, 1))
    with wave.open(str(path), 'wb') as w:
        w.setnchannels(x.shape[0])
        w.setsampwidth(2)
        w.setframerate(sr)
        w.writeframes((x.T * 32767).astype(np.int16).tobytes())


def read_wav(path):
    with wave.open(str(path), 'rb') as w:
        n, ch, sr = w.getnframes(), w.getnchannels(), w.getframerate()
        x = np.frombuffer(w.readframes(n), dtype=np.int16).astype(np.float32) / 32767
    return x.reshape(-1, ch).T, sr


def _flat(items):
    for it in items:
        if isinstance(it, list):
            yield from _flat(it)
        else:
            yield it


def world_view(s):
    """[x, y, zoom] that fits a world slide's whole canvas on screen."""
    ww, wh = s.world
    return [ww / 2, wh / 2, round(min(T.W / ww, T.H / wh), 4)]


def cmd_plan():
    VOICE_QC.clear()
    t = 0.0
    slides, beats_out, cues, trig, acts, scene_sounds = [], [], [], {}, {}, []
    audio_parts = []
    subs = EP.META.get('subs', not novoice())  # 大字口播 shows its own words: META subs False
    for si, s in enumerate(EP.SLIDES):
        s_html = s.html()
        s_start = t
        kind, td = slide_trans(s, si)
        if not novoice():  # cut to music: no padding, so slide changes land on the beats' grid
            if si == 0:
                t += LEAD_FIRST
            elif runs_on(EP.SLIDES[si - 1]):  # the sentence goes on: speak while the transition plays
                t += max(0.12, 0.5 * td)
            else:
                t += max(meta('lead'), td + 0.1)
        x, beats = slide_audio(s)
        audio_parts.append((t, x))
        a_start = t
        anim_end = t
        # magic move: carried elements are on screen from the slide's first frame, silently
        carried = {}
        for a_id, b_id in s.carry.items():
            if si == 0 or f'id="{a_id}"' not in EP.SLIDES[si - 1].html():
                raise KeyError(f'{s.id}: carry {a_id} is not on the previous slide')
            if f'id="{b_id}"' not in s.html():
                raise KeyError(f'{s.id}: carry target {b_id} is not on this slide')
            if b_id in deck.ELEM:
                trig[b_id] = (round(s_start, 4), 0.01)
                deck.ELEM[b_id]['sfx'] = None
            carried[b_id] = a_id
        cams, hits, bt, bk, bw = [], [], [], {}, []
        for b, bi in zip(s.beats, beats):
            b_start = a_start + bi['start']
            bt.append(round(b_start - s_start, 3))
            if s.moving() or s.sounds:  # when each character of the line is heard (S.word, s.sound)
                disp, n = b['text'] or '', max(1, len(bi['text']))
                ct = [bi['ct'][min(n - 1, int(round(i * n / max(1, len(disp)))))] if bi['ct'] else 0.0 for i in range(len(disp))]
                bw.append([disp, [round(bt[-1] + max(0.0, c), 3) for c in ct]])
            if b.get('key'):
                if b['key'] in bk:
                    raise ValueError(f"{s.id}: beat key {b['key']!r} used twice")
                bk[b['key']] = bt[-1]
            if b.get('cam') is not None:
                c = b['cam']
                home = world_view(s) if s.world else [T.W / 2, T.H / 2, 1.0]
                cams.append([round(b_start, 3)] + (home + ['smooth'] if c == 0 else [float(v) for v in c[:3]] + [c[3] if len(c) > 3 else 'smooth']))
            prev = None
            for item in _flat(b['show']):
                obj, spec = (item if isinstance(item, tuple) else (item, None))
                if isinstance(obj, deck.Cue):  # an action on something already there, or on the camera
                    c = obj
                    if c.i in acts:
                        raise ValueError(f'{s.id}: {c} is used twice; make a new one')
                    for target in [c.el] + c.a.get('keep', []):
                        if not target.startswith('@') and f'id="{target}"' not in s_html:
                            raise KeyError(f'{s.id}: {c.k}() on {target}, which is not on this slide')
                    if spec is None:
                        st = b_start + 0.05 if prev is None else prev[0] + prev[1] * 0.7
                    elif spec == '=':
                        st = prev[0]
                    else:
                        st = b_start + spec
                    for cx in [c] + c.also:
                        acts[cx.i] = [round(st, 4), cx.d, si, cx.persist, cx.loop]
                    if c.el == '@cam':
                        hits.append([round(st, 3), c.a.get('amp', 14), c.d])
                    d = 0.0 if c.loop else c.d
                    prev = (st, d)
                    anim_end = max(anim_end, st + d)
                    continue
                eid = obj
                if eid not in deck.ELEM:
                    raise KeyError(f'{s.id}: unknown element {eid}')
                if eid in carried:
                    raise ValueError(f'{s.id}: {eid} flies in from {carried[eid]} (carry); leave it out of the beats')
                d = el_dur(eid)
                if spec is None:
                    st = b_start + 0.05 if prev is None else prev[0] + prev[1] * 0.7
                elif spec == '=':
                    st = prev[0]
                else:
                    st = b_start + spec
                if eid in trig:
                    raise ValueError(f'{eid} triggered twice')
                trig[eid] = (round(st, 4), d)
                prev = (st, d)
                anim_end = max(anim_end, st + d)
            disp, text = b['text'], bi['text']
            beats_out.append({'slide': si, 'start': round(b_start, 3), 'dur': round(bi['dur'], 3), 'text': disp})
            if not (subs and disp and b.get('voiced', True)):
                continue
            spans = split_cues(disp, T.sub_max)
            ratio = len(text) / len(disp)
            starts = [b_start + max(0.0, bi['ct'][min(len(text) - 1, int(round(a * ratio)))]) for a, _ in spans]
            starts[0] = b_start
            ends = starts[1:] + [b_start + bi['dur'] + 0.15]
            # a cue shorter than 0.7 s flashes by: join it to its neighbour in the same line when the two
            # still fit on one line (a little over sub_max is fine; the band is wider than that)
            width = lambda t: sum(0.5 if ord(ch) < 128 else 1 for ch in t.strip('，。、；：！？,.;:!? '))  # noqa: E731
            parts = []
            for (a, bb), c0, c1 in zip(spans, starts, ends):
                if parts and (c1 - c0 < 0.7 or parts[-1][3] - parts[-1][2] < 0.7) \
                        and width(disp[parts[-1][0]:bb]) <= T.sub_max + 3:
                    parts[-1] = (parts[-1][0], bb, parts[-1][2], c1)
                else:
                    parts.append((a, bb, c0, c1))
            for a, bb, c0, c1 in parts:
                cues.append({'start': round(c0, 3), 'end': round(c1, 3), 'text': cue_display(disp[a:bb])})
        t = a_start + len(x) / SR + (s.beats[-1]['pause'] or 0)
        if not novoice():
            # the last animation gets a 0.4 s hold, the last line its tail: whichever ends later, not the
            # two added (a punch landing just after the line made a 1.5 s gap before the next slide)
            t = max(t + 0.1, anim_end + 0.15) if runs_on(s) else max(t + meta('tail'), anim_end + 0.4)
        for snd in s.sounds:  # scene sound effects, resolved like S.word
            b = snd['beat']
            i = int(b[1:]) if re.fullmatch(r'b\d+', b) else (bt.index(bk[b]) if b in bk else None)
            if i is None or i >= len(bt):
                raise KeyError(f'{s.id}: sound at unknown beat {b!r}')
            at = bt[i]
            if snd['word']:
                text, ct = bw[i] if i < len(bw) else ('', [])
                k = text.find(snd['word'])
                if k < 0:
                    raise KeyError(f"{s.id}: sound word {snd['word']!r} is not in beat {b}: {text}")
                at = ct[k]
            ev = {'t': round(s_start + at + snd['off'], 3), 'k': snd['k']}
            if snd['d']:
                ev['d'] = snd['d']
            scene_sounds.append(ev)
        slides.append({'id': s.id, 'start': round(s_start, 3), 'end': round(t, 3), 'tr': kind, 'td': td,
                       'static': has_static(s),
                       'tro': s.trans_at, 'carry': [[a, b] for b, a in carried.items()], 'cams': cams, 'hits': hits,
                       'world': list(s.world) if s.world else None, 'cam0': list(s.cam0) if s.cam0 else None,
                       'moving': s.moving(), 'bt': bt, 'bk': bk, 'bw': bw})
    total = t + 0.6
    slides[-1]['end'] = round(total, 3)

    for s in EP.SLIDES:  # elements never triggered stay static; warn so mistakes are visible
        for eid in slide_elems(s):
            if eid not in trig:
                print('warn: static element', s.id, eid)

    buf = np.zeros(int(total * SR) + SR, dtype=np.float32)
    for st, x in audio_parts:
        i = int(round(st * SR))
        buf[i:i + len(x)] += x
    write_wav(WORK / 'narration.wav', buf / (np.abs(buf).max() or 1.0) * 0.89, SR)

    # a beat's last cue lingers 0.15 s; when the next line starts sooner the two cues would show together
    for c, nxt in zip(cues, cues[1:]):
        if c['end'] > nxt['start'] - 0.02:
            c['end'] = round(max(c['start'] + 0.3, nxt['start'] - 0.02), 3)

    plan = {'total': round(total, 3), 'slides': slides, 'beats': beats_out, 'cues': cues,
            'trig': trig, 'acts': {str(k): v for k, v in sorted(acts.items())}, 'elems': {s.id: slide_elems(s) for s in EP.SLIDES},
            'sounds': scene_sounds}
    (WORK / 'plan.json').write_text(json.dumps(plan, ensure_ascii=False, indent=1), encoding='utf-8')
    if VOICE_QC:
        (WORK / 'narration-qc.json').write_text(json.dumps(VOICE_QC, ensure_ascii=False, indent=2), encoding='utf-8')
    write_srt(cues, OUT / f'{NAME}.srt')
    write_script(plan)
    chars = sum(len(re.sub(r'[^一-鿿A-Za-z0-9]', '', b['text'])) for b in beats_out)
    talk = sum(b['dur'] for b in beats_out if b['text'])
    pace = f', {chars / talk:.2f} chars/s while talking' if talk and not novoice() else ''
    print(f'plan ok: {total / 60:.1f} min, {len(beats_out)} beats, {len(cues)} subtitle cues, {len(acts)} actions{pace}')
    said = [b for b in beats_out if b['text']]
    long_gaps = []
    for a, b in zip(said, said[1:]):
        gap = b['start'] - a['start'] - a['dur']
        ends = re.search(r'[。！？!?；;]$', a['text'].rstrip(' 」』”"’）)'))
        if gap > (1.3 if ends else 0.7):
            long_gaps.append((gap, a, b, ends))
    if long_gaps:
        print(f'  voice: {len(long_gaps)} long silences between spoken lines (a silent beat, pause=, or the voice '
              'waiting for an animation; shorten them or say why they are there):')
        for gap, a, b, ends in long_gaps[:10]:
            where = '换页' if a['slide'] != b['slide'] else '同页'
            print(f'    {gap:.1f}s {where}{"" if ends else "，句子中间"} 「…{a["text"][-8:]}」→「{b["text"][:8]}…」')
    pauses = [(sid, p) for sid, q in VOICE_QC.items() for p in q.get('pauses', [])]
    breaths = sum(len(q.get('breaths', [])) for q in VOICE_QC.values())
    held = [p for q in VOICE_QC.values() for p in q.get('held', [])]
    if pauses or breaths or held:
        added = [p for _, p in pauses if p['added']]
        stuck = [(sid, p) for sid, p in pauses if not p['added']]
        print(f'  voice: {len(added)} pauses lengthened (+{sum(p["added"] for p in added):.1f} s), '
              f'{len(held)} held too long shortened (-{sum(p["had"] - p["now"] for p in held):.1f} s), '
              f'{len(stuck)} marks run together, {breaths} inhales turned down (narration-qc.json)')
        for sid, p in stuck[:8]:
            print(f'    {sid:5s} 标点处连读（换一遍合成或改说法） {p["text"]}')
    floors = {sid: q['floor'] for sid, q in VOICE_QC.items() if q.get('floor')}
    if floors:
        sid, f = max(floors.items(), key=lambda kv: kv[1]['floor_db'])
        print(f'  voice floor: worst {sid} {f["floor_db"]:.0f} dB under speech -> {f["floor_after_db"]:.0f} dB between words')
        if f['floor_db'] > -38:
            print(f'    底噪偏高：{sid} 的底噪只比人声低 {-f["floor_db"]:.0f} dB（参考音太吵？换音色或重新合成），停顿里已压低')


def write_script(plan):
    """口播稿.md: narration per slide with timestamps, plus the episode's notes."""
    def mmss(t):
        return f'{int(t) // 60:02d}:{int(t) % 60:02d}'
    out = [f"# {EP.META.get('title', NAME)}", '',
           f"> {T.watermark or T.series}", f"> 时长约 {plan['total'] / 60:.1f} 分钟 · {EP.META.get('asof', '')}".rstrip(' ·'),
           '', '## 口播稿（按幻灯片分段）', '']
    by_slide = {}
    for b in plan['beats']:
        by_slide.setdefault(b['slide'], []).append(b['text'])
    for si, (s, sp) in enumerate(zip(EP.SLIDES, plan['slides'])):
        out += [f"### {si:02d}｜{s.name or s.id}　`{mmss(sp['start'])}`", '', ''.join(by_slide.get(si, [])), '']
    if EP.META.get('notes'):
        out += [EP.META['notes'].strip(), '']
    (OUT / '口播稿.md').write_text('\n'.join(out), encoding='utf-8')


# ---------------------------------------------------------------- audio

def music_bed(total, plan):
    """META bgm: True / 'lofi' (the house bed), 'ambient' (slow, drumless: 情感短片), 'glass' (ambient with a
    quiet arpeggio: 原理动画), 'pulse' (driving, META bpm), a music file path, or False."""
    m = meta('bgm')
    if not m:
        return None
    end = plan['slides'][-1]['start']
    if m is True or m == 'lofi':
        return A.make_bgm(total, seed=meta('bgm_seed'), outro_at=end)
    if m in ('ambient', 'glass'):
        return A.make_ambient(total, seed=meta('bgm_seed'), bpm=EP.META.get('bpm', 64 if m == 'ambient' else 84),
                              arp=m == 'glass', outro_at=end)
    if m == 'pulse':
        return A.make_pulse(total, bpm=EP.META.get('bpm', 112), outro_at=end)
    path = next((c for c in (Path(m), SRC / m, REPO / m) if c.exists()), None)
    if not path:
        sys.exit(f"music not found: {m} (META bgm: True, 'pulse', a file path or False)")
    return A.load_music(path, total, ffmpeg())


CUE_SFX = {'punch': 'impact', 'jump': 'pop', 'click': 'click'}  # anything else is silent unless it asks


def cue_events(plan):
    """Sound cues for the actions (cues): a camera shake thuds, a punch lands, a click clicks."""
    ev = []
    for k, (t0, d, si, persist, loop) in plan.get('acts', {}).items():
        c = deck.CUES[int(k)]
        snd = c.sfx if c.sfx != deck.AUTO else ('thud' if c.el == '@cam' else CUE_SFX.get(c.k))
        if snd:
            ev.append({'t': t0 - (d if snd == 'riser' else 0), 'k': snd, 'd': d})
    return ev


def cmd_audio():
    from scipy.signal import resample_poly
    plan = json.loads((WORK / 'plan.json').read_text(encoding='utf-8'))
    total = plan['total']
    v, sr = read_wav(WORK / 'narration.wav')  # peak-normalised mono at 24 kHz
    voice = resample_poly(v[0], A.SR // sr, 1).astype(np.float32)[:int(total * A.SR)]
    bgm = music_bed(total, plan)
    events = []
    if meta('sfx'):
        trans = [None] + [(s.sfx if s.sfx != deck.AUTO else 'whoosh') for s in EP.SLIDES[1:]]
        events = sorted(A.sfx_events(plan, deck.ELEM, trans) + cue_events(plan) + A.pitch_run(plan.get('sounds', [])),
                        key=lambda e: e['t'])
    sfx = A.render_sfx_track(events, total, gain=10 ** (meta('sfx_db') / 20))
    if novoice():  # the music is the lead: near full level, effects on their usual footing
        out, stems = A.mix(voice, bgm, sfx, bgm_lu=EP.META.get('music_lu', -3.0), ref_lufs=-18.0)
    else:
        out, stems = A.mix(voice, bgm, sfx, bgm_lu=meta('bgm_lu'), duck_db=meta('duck_db'))
    out = A.limit(out)
    write_wav(WORK / 'mix.wav', out, A.SR)
    stem_dir = OUT / '音轨'  # separate tracks for re-balancing in an editor
    stem_dir.mkdir(exist_ok=True)
    if not novoice():
        write_wav(stem_dir / '配音.wav', A.limit(stems['voice'])[0], A.SR)
    write_wav(stem_dir / '背景音乐.wav', stems['bgm'], A.SR)
    write_wav(stem_dir / '音效.wav', stems['sfx'], A.SR)
    (WORK / 'sfx.json').write_text(json.dumps(events, ensure_ascii=False), encoding='utf-8')
    lv, lb = A.lufs(stems['voice']), A.lufs(stems['bgm']) if bgm is not None else -70
    if novoice():
        print(f'audio ok: mix {A.lufs(out):.1f} LUFS, music {lb:.1f}, effects {A.lufs(stems["sfx"]):.1f}, {len(events)} sfx (no narration)')
    else:
        print(f'audio ok: mix {A.lufs(out):.1f} LUFS, voice {lv:.1f}, bgm {lb:.1f} ({lb - lv:+.1f} LU), {len(events)} sfx')


# ---------------------------------------------------------------- deck html

def page_html(body, size=None):
    """A full HTML page in the theme: :root variables, font face, house CSS, runtime."""
    w, h = size or (T.W, T.H)
    css = T.css_vars() + T.font_face() + (ENGINE / 'deck.css').read_text(encoding='utf-8') + T.theme_css() + T.extra_css()
    if (w, h) != (T.W, T.H):
        css += f':root{{--W:{w}px;--H:{h}px}}'
    scenes = ','.join(f'{json.dumps(s.id)}:{{run:({s.scene[0]}),setup:({s.scene[1] or "null"})}}'
                      for s in EP.SLIDES if s.scene) if EP else ''
    js = (f'window.__MOTION={json.dumps({"ease": T.motion["ease"]})};'
          f'window.__CUES={json.dumps([c.js() for c in deck.CUES], ensure_ascii=False)};'
          f'window.__FX={json.dumps(T.fx)};window.__SCENES={{{scenes}}};' + (ENGINE / 'runtime.js').read_text(encoding='utf-8'))
    return (f'<!doctype html><html><head><meta charset="utf-8"><style>{css}</style></head>'
            f'<body>{body}<script>{js}</script></body></html>')


def watermark():
    return f'<div class="wm">{T.watermark}</div>' if T.watermark else ''


def deck_html(subs=True):
    slides = []
    for s in EP.SLIDES:
        h = s.html()
        if s.wm:
            h = h.replace('</section>', watermark() + '</section>')
        slides.append(h)
    sub = '<div id="sub"></div>' if subs else '<div id="sub" style="display:none"></div>'
    return page_html(''.join(slides) + fx_layers() + sub)


def fx_layers():
    """Film look over every slide (theme fx): grain, vignette, letterbox bars; none in the house style."""
    out = ''
    if T.fx.get('vignette'):
        out += '<div id="fx-vig" class="fx"></div>'
    if T.fx.get('grain'):
        out += '<div id="fx-grain" class="fx"></div>'
    if T.bar:
        out += '<div id="fx-bars" class="fx"><i></i><i></i></div>'
    return out


# ---------------------------------------------------------------- frames

def frame_states(plan, t_from=0.0, t_to=None):
    trig = {k: tuple(v) for k, v in plan['trig'].items()}
    nchar = {k: max(1, v['n']) for k, v in deck.ELEM.items()}
    slides, cues = plan['slides'], plan['cues']
    t_to = plan['total'] if t_to is None else t_to
    runs, last_sig = [], None
    ci, si = 0, 0
    cw, ch, cdur = deck.T.W, deck.T.H, deck.T.motion.get('cam_dur', 1.0)
    grainy = bool(deck.T.fx.get('grain'))  # moving grain: every frame differs
    for f in range(int(t_from * FPS), int(math.ceil(t_to * FPS))):
        T = f / FPS
        while si + 1 < len(slides) and T >= slides[si + 1]['start']:
            si += 1
        td = slides[si].get('td', TRANS)
        alpha = 1.0 if si == 0 or td <= 0 else min(1.0, (T - slides[si]['start']) / td)
        alpha = round(alpha, 3)
        prev = si - 1 if alpha < 1 else None
        sl = slides[si]
        cam = cam_at(sl.get('cams'), T, cw, ch, cdur, sl.get('world'), sl.get('cam0'), sl.get('hits') or ())
        pl = slides[prev] if prev is not None else None
        pcam = cam_at(pl.get('cams'), T, cw, ch, cdur, pl.get('world'), pl.get('cam0'), pl.get('hits') or ()) if pl else None
        q = acts_at(plan, {si} if prev is None else {si, prev}, T)
        p = {}
        for eid in plan['elems'][EP.SLIDES[si].id]:
            if eid in trig:
                st, d = trig[eid]
                v = min(1.0, max(0.0, (T - st) / d))
                if deck.ELEM[eid]['a'] == 'type' and v < 1:
                    v = math.floor(v * nchar[eid]) / nchar[eid]
                p[eid] = round(v, 3)
            else:
                p[eid] = 1.0
        if prev is not None:
            for eid in plan['elems'][EP.SLIDES[prev].id]:
                p[eid] = 1.0
        while ci + 1 < len(cues) and T >= cues[ci + 1]['start']:
            ci += 1
        sub = cues[ci]['text'] if cues and cues[ci]['start'] <= T < cues[ci]['end'] else ''
        sc = scene_clock(sl, T)
        psc = scene_clock(pl, T) if pl else None
        moving = sc is not None or psc is not None or grainy
        sig = (si, alpha, prev, sub, tuple(sorted(p.items())), tuple(cam or ()), tuple(pcam or ()), tuple(sorted(q.items())),
               f if moving else None)
        if sig != last_sig:
            st = {'cur': si, 'prev': prev, 'alpha': alpha, 'p': p, 'sub': sub, 'f': f}
            if sc:
                st['sc'] = sc
            if psc:
                st['psc'] = psc
            if prev is not None and slides[si].get('tr', 'fade') != 'fade':
                st['tr'] = {'k': slides[si]['tr'], 'o': slides[si].get('tro'), 'c': slides[si].get('carry')}
            if cam:
                st['cam'] = cam
            if pcam:
                st['pcam'] = pcam
            if q:
                st['q'] = q
            runs.append({'f': f, 'n': 1, 'st': st})
            last_sig = sig
        else:
            runs[-1]['n'] += 1
    return runs


def scene_clock(sl, T):
    """What a moving slide's scene needs at time T: {t since the slide began, d its length, bt, bk}."""
    if not sl.get('moving'):
        return None
    return {'t': round(T - sl['start'], 4), 'd': round(sl['end'] - sl['start'], 3), 'bt': sl.get('bt', []), 'bk': sl.get('bk', {}),
            'bw': sl.get('bw', []), 's': sl['start']}


def _render_chunk(args):
    html_path, items, outdir, size = args
    from playwright.sync_api import sync_playwright
    with sync_playwright() as pw:
        br, pg = open_page(pw, html_path, size)
        for idx, st in items:
            pg.evaluate('st => window.__frame(st)', st)
            pg.screenshot(path=str(Path(outdir) / f'r{idx:06d}.jpg'), type='jpeg', quality=94)
        br.close()
    return len(items)


def render_frames(runs, outdir):
    (WORK / 'deck.html').write_text(deck_html(), encoding='utf-8')
    outdir.mkdir(exist_ok=True)
    for old in outdir.glob('*.jpg'):
        old.unlink()
    items = [(i, r['st']) for i, r in enumerate(runs)]
    chunks = [items[k::WORKERS] for k in range(WORKERS)]
    print(f'render: {len(runs)} unique frames of {sum(r["n"] for r in runs)}, {WORKERS} workers')
    with ProcessPoolExecutor(WORKERS) as ex:
        done = sum(ex.map(_render_chunk, [(str(WORK / 'deck.html'), c, str(outdir), (T.W, T.H)) for c in chunks]))
    lines = ['ffconcat version 1.0']
    for i, r in enumerate(runs):
        lines += [f"file 'r{i:06d}.jpg'", f'duration {r["n"] / FPS:.6f}']
    lines.append(f"file 'r{len(runs) - 1:06d}.jpg'")
    (outdir / 'list.ffconcat').write_text('\n'.join(lines), encoding='utf-8')
    return done


def cmd_render():
    plan = json.loads((WORK / 'plan.json').read_text(encoding='utf-8'))
    print('render ok:', render_frames(frame_states(plan), FRAMES))


def video_crf():
    """x264 quality: META crf, else 18; with film grain 22, since moving grain changes every pixel of
    every frame and at 18 a 46 s film came out at 144 MB (25 Mbit/s) with no visible gain."""
    return EP.META.get('crf', 22 if T.fx.get('grain') else 18)


def mux(frames_dir, out, t_from=0.0, t_dur=None, sound=True):
    audio = ['-ss', f'{t_from:.3f}'] + (['-t', f'{t_dur:.3f}'] if t_dur else []) + ['-i', str(WORK / 'mix.wav')] if sound else []
    run([ffmpeg(), '-v', 'error', '-y', '-f', 'concat', '-safe', '0', '-i', str(frames_dir / 'list.ffconcat'), *audio,
         # JPEG frames are full-range BT.601; deliver limited-range BT.709 like any phone video
         # (accurate rounding keeps a white page at 235/128/128 instead of a faint cyan 235/128/127;
         # setparams tags primaries / transfer too, which the output options alone left 'unknown')
         '-filter_complex', '[0:v]fps=30,scale=out_range=tv:out_color_matrix=bt709:flags=accurate_rnd+full_chroma_int,format=yuv420p,'
                            'setparams=range=tv:colorspace=bt709:color_primaries=bt709:color_trc=bt709[v]', '-map', '[v]',
         *(['-map', '1:a'] if sound else []),
         '-c:v', 'libx264', '-preset', 'medium', '-crf', str(video_crf()), '-pix_fmt', 'yuv420p',
         '-color_range', 'tv', '-colorspace', 'bt709', '-color_primaries', 'bt709', '-color_trc', 'bt709',
         *(['-c:a', 'aac', '-b:a', '192k', '-shortest'] if sound else []), '-movflags', '+faststart', str(out)])


def cmd_video():
    out = OUT / f'{NAME}.mp4'
    mux(FRAMES, out)
    print('video ok:', out)


def cmd_preview(first, last=None):
    plan = json.loads((WORK / 'plan.json').read_text(encoding='utf-8'))
    ids = [s['id'] for s in plan['slides']]
    a, b = ids.index(first), ids.index(last or first)
    t0, t1 = plan['slides'][a]['start'], plan['slides'][b]['end']
    render_frames(frame_states(plan, t0, t1), WORK / 'preview_frames')
    mux(WORK / 'preview_frames', WORK / 'preview.mp4', t0, t1 - t0)
    print(f'preview ok: {WORK / "preview.mp4"} ({t0:.1f}s-{t1:.1f}s)')


def cmd_silent(first=None, last=None):
    """Motion preview without a voice: timings estimated from the script -> work/silent/silent.mp4."""
    global SILENT
    SILENT = True
    cmd_plan()
    plan = json.loads((WORK / 'plan.json').read_text(encoding='utf-8'))
    ids = [s['id'] for s in plan['slides']]
    a, b = (ids.index(first), ids.index(last or first)) if first else (0, len(ids) - 1)
    t0, t1 = plan['slides'][a]['start'], plan['slides'][b]['end']
    render_frames(frame_states(plan, t0, t1), WORK / 'frames')
    mux(WORK / 'frames', WORK / 'silent.mp4', sound=False)
    print(f'silent ok: {WORK / "silent.mp4"} ({t1 - t0:.1f}s, no sound; timings are estimates)')
    cmd_rhythm()


def cmd_rhythm():
    """Shot lengths, carries across slide changes, stillness -> work/rhythm.txt (see qa.rhythm)."""
    import qa
    lines = qa.rhythm(json.loads((WORK / 'plan.json').read_text(encoding='utf-8')), promo=novoice())
    (WORK / 'rhythm.txt').write_text('\n'.join(lines) + '\n', encoding='utf-8')
    for ln in lines[2:7]:
        if ln:
            print('  ' + ln)


def _on_slide(c, s):
    """Is action c used in one of slide s's beats?"""
    return any((it[0] if isinstance(it, tuple) else it) is c for b in s.beats for it in _flat(b['show']))


def cmd_stills():
    """Final-state slides -> PNG + PDF, plus covers and a contact sheet. Needs no TTS."""
    from playwright.sync_api import sync_playwright
    from PIL import Image
    sdir = WORK / 'stills'
    sdir.mkdir(exist_ok=True)
    for old in sdir.glob('*.png'):
        old.unlink()
    (WORK / 'deck_nosub.html').write_text(deck_html(subs=False), encoding='utf-8')
    covers = getattr(EP, 'COVERS', {}) or {}
    # where subtitles sit: a centred band as wide as the longest cue
    sw = T.sub_max * T.sub_size * 1.04
    band = {'top': T.H - T.sub_bottom - T.sub_size * 1.25, 'bottom': T.H - T.sub_bottom + 6,
            'left': (T.W - sw) / 2, 'right': (T.W + sw) / 2}
    layout = []
    with sync_playwright() as pw:
        br, pg = open_page(pw, WORK / 'deck_nosub.html', (T.W, T.H))
        paths = []
        for si, s in enumerate(EP.SLIDES):
            p = {eid: 1.0 for eid in slide_elems(s)}
            st = {'cur': si, 'prev': None, 'alpha': 1, 'p': p, 'sub': '', 'f': 0}
            if s.moving():  # a scene at its end: every timed move finished
                st['sc'] = {'t': 1e4, 'd': 1e4, 'bt': [], 'bk': {}, 'still': True}
            # actions at their end state: exits gone, moves arrived, focus held
            # (creation order stands in for start time: a later action wins)
            st['q'] = {str(c.i): [c.d, c.i] for c in deck.CUES if c.persist and _on_slide(c, s)}
            if s.world:
                st['cam'] = world_view(s)
            pg.evaluate('st => window.__frame(st)', st)
            fp = sdir / f'{si:02d}_{s.id}.png'
            pg.screenshot(path=str(fp))
            paths.append(fp)
            layout += [f'{s.id:5s} {x}' for x in pg.evaluate('([b, z]) => window.__layout(b, z)',
                                                              [None if s.world else band, T.avoid])]
        br.close()
        for name, (size, body) in covers.items():
            hp = WORK / f'cover_{size[0]}x{size[1]}.html'
            hp.write_text(page_html(f'<section class="slide bg-cover" style="display:block">{body}{watermark()}</section>', size),
                          encoding='utf-8')
            br, pg = open_page(pw, hp, size)
            pg.screenshot(path=str(OUT / f'{name}.png'))
            br.close()
    ims = [Image.open(p).convert('RGB') for p in paths]
    ims[0].save(OUT / f'{NAME}_幻灯片.pdf', save_all=True, append_images=ims[1:], resolution=144)
    cols = 4 if T.W >= T.H else 6
    w = 1920 // cols
    h = round(w * T.H / T.W)
    sheet = Image.new('RGB', (w * cols, h * math.ceil(len(ims) / cols)), 'white')
    for i, im in enumerate(ims):
        sheet.paste(im.resize((w, h), Image.LANCZOS), ((i % cols) * w, (i // cols) * h))
    sheet.save(WORK / 'contact.jpg', quality=90)
    (WORK / 'layout.txt').write_text('# 排版自检：出界、重叠、溢出、压字幕、文字进避让区（看 contact.jpg 确认，有意为之的可以忽略）\n'
                                     + '\n'.join(layout or ['（无）']) + '\n', encoding='utf-8')
    print(f'stills ok: {len(paths)} slides, {len(covers)} covers -> work/contact.jpg; '
          f'layout: {len(layout)} flags -> work/layout.txt')
    for ln in layout[:12]:
        print('  ' + ln)
    if len(layout) > 12:
        print(f'  ... {len(layout) - 12} more in layout.txt')


STEPS = {'tts': cmd_tts, 'lint': cmd_lint, 'plan': cmd_plan, 'audio': cmd_audio, 'stills': cmd_stills,
         'render': cmd_render, 'video': cmd_video, 'rhythm': cmd_rhythm, 'freeze': cmd_freeze}
GROUPS = {'all': ['tts', 'plan', 'audio', 'stills', 'render', 'video'], 'check': ['tts', 'lint', 'plan', 'stills', 'rhythm']}

def main(argv):
    if not argv:
        sys.exit(__doc__)
    args = argv[1:] or ['all']
    if args[0] == 'silent':
        load_episode(argv[0], sub='silent')
        cmd_silent(*args[1:3])
        return
    load_episode(argv[0])
    if args[0] == 'preview':
        for st in ('tts', 'plan', 'audio'):
            STEPS[st]()
        cmd_preview(*args[1:3])
        return
    for a in args:
        for st in GROUPS.get(a, [a]):
            if st not in STEPS:
                sys.exit(f'unknown step: {st}\n\n{__doc__}')
            STEPS[st]()


if __name__ == '__main__':
    main(sys.argv[1:])
