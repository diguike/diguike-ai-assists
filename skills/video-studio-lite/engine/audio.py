"""Background music, sound effects and the final mix.

Everything is synthesised here (no third-party samples or loops), so episodes
carry no music-licensing risk and every build is reproducible from a seed.
Pitched effects use the music's scale (C major pentatonic) so they sit in key
with the bed.
"""
import numpy as np
from scipy import signal

SR = 48000
PENTA = [0, 2, 4, 7, 9]


def hz(m):
    return 440.0 * 2 ** ((m - 69) / 12)


def _t(n):
    return np.arange(n) / SR


def penta(base, step):
    """MIDI note `step` pentatonic steps above `base` (a C)."""
    return base + 12 * (step // 5) + PENTA[step % 5]


def _fade_tail(x, sec=0.012):
    """Raised-cosine fade over the last `sec` of a note or effect. A sound cut off while it is still
    ringing (a kick at -19 dB, a pad at -21 dB, a pop at -24 dB) ends on a step, and a step is a
    click: the author heard them as a sudden 「卡」 (2026-10-31)."""
    n = min(int(sec * SR), x.shape[-1])
    if n > 1:
        x = x.copy()
        x[..., -n:] *= 0.5 + 0.5 * np.cos(np.linspace(0, np.pi, n))
    return x


def _add(buf, x, t):
    x = _fade_tail(x)
    i = int(round(t * SR))
    if i < 0:
        x, i = x[..., -i:], 0
    n = min(x.shape[-1], buf.shape[-1] - i)
    if n > 0:
        buf[..., i:i + n] += x[..., :n]


def _sos(kind, f, order=2):
    return signal.butter(order, f, kind, fs=SR, output='sos')


def _peq(f0, gain_db, q):
    """RBJ peaking EQ biquad as (b, a)."""
    a_ = 10 ** (gain_db / 40)
    w = 2 * np.pi * f0 / SR
    al = np.sin(w) / (2 * q)
    b = np.array([1 + al * a_, -2 * np.cos(w), 1 - al * a_])
    a = np.array([1 + al / a_, -2 * np.cos(w), 1 - al / a_])
    return b / a[0], a / a[0]


# ---------------------------------------------------------------- instruments

def epiano(m, dur, vel, rng):
    """FM electric piano: a soft bark on the attack that mellows into a sine."""
    f = hz(m) * 2 ** (rng.normal(0, 2) / 1200)
    n = int((dur + 1.4) * SR)
    t = _t(n)
    idx = (0.5 + 1.2 * vel) * np.exp(-t / 0.3) + 0.12
    body = np.sin(2 * np.pi * f * t + idx * np.sin(2 * np.pi * f * t))
    tine = np.sin(2 * np.pi * f * t + 1.5 * np.exp(-t / 0.015) * np.sin(2 * np.pi * 14 * f * t)) * np.exp(-t / 0.06) * 0.2
    env = np.exp(-t / (1.6 * (261.6 / f) ** 0.4)) * (1 - np.exp(-t / 0.003))
    env *= np.where(t > dur, np.exp(-np.maximum(t - dur, 0) / 0.2), 1.0)
    return (body + tine) * env * vel


def bass(m, dur, vel):
    f = hz(m)
    n = int((dur + 0.4) * SR)
    t = _t(n)
    x = np.sin(2 * np.pi * f * t) + 0.18 * np.sin(4 * np.pi * f * t) + 0.06 * np.sin(6 * np.pi * f * t)
    env = (1 - np.exp(-t / 0.006)) * (0.55 + 0.45 * np.exp(-t / 0.35))
    env *= np.where(t > dur, np.exp(-np.maximum(t - dur, 0) / 0.08), 1.0)
    return x * env * vel


def pad(ms, dur, rng, lo=16000):
    """Warm stereo pad: band-limited detuned saws, rendered at 16 kHz and upsampled."""
    n = int((dur + 4.6) * lo)  # the 0.9 s release rings out to about -45 dB before the buffer ends
    t = np.arange(n) / lo
    out = np.zeros((2, n))
    for ch, cents in enumerate((-7, 7)):
        for m in ms:
            f = hz(m) * 2 ** (cents / 1200)
            ph = rng.random() * 2 * np.pi
            for k in range(1, max(1, int(1600 // f)) + 1):
                out[ch] += np.sin(2 * np.pi * k * f * t + k * ph) / k / (1 + (k * f / 700) ** 2)
    env = (1 - np.exp(-t / 0.7)) * np.where(t > dur, np.exp(-np.maximum(t - dur, 0) / 0.9), 1.0)
    return signal.resample_poly(out * env, SR // lo, 1, axis=1)


def kick(vel):
    n = int(0.8 * SR)  # tau 0.16 s: 0.8 s is -43 dB (0.35 s cut the tail at -19 dB, a click on every beat)
    t = _t(n)
    ph = 2 * np.pi * np.cumsum(45 + 70 * np.exp(-t / 0.035)) / SR
    return np.sin(ph) * np.exp(-t / 0.16) * (1 - np.exp(-t / 0.002)) * vel


def brush(vel, rng):
    n = int(0.25 * SR)
    t = _t(n)
    x = signal.sosfilt(_sos('bandpass', [1200, 6000]), rng.standard_normal(n))
    return _fade_tail(x * np.exp(-t / 0.07) * (1 - np.exp(-t / 0.004)) * vel * 0.5, 0.08)


def shaker(vel, rng):
    n = int(0.08 * SR)
    t = _t(n)
    x = signal.sosfilt(_sos('highpass', 5000), rng.standard_normal(n))
    return _fade_tail(x * np.exp(-t / 0.025) * (1 - np.exp(-t / 0.008)) * vel * 0.4, 0.03)


def reverb_ir(rng, rt=1.6):
    n = int(rt * 1.2 * SR)
    t = _t(n)
    out = []
    for _ in range(2):
        w = rng.standard_normal(n)
        ir = (signal.sosfilt(_sos('lowpass', 600), w) * np.exp(-6.9 * t / rt)
              + signal.sosfilt(_sos('bandpass', [600, 3500]), w) * np.exp(-6.9 * t / (rt * 0.75))
              + signal.sosfilt(_sos('highpass', 3500), w) * np.exp(-6.9 * t / (rt * 0.4)))
        ir[:int(0.015 * SR)] = 0
        out.append(ir / np.sqrt((ir ** 2).sum()))
    return np.array(out)


# ---------------------------------------------------------------- music

CHORDS = {  # name: (bass, voicing) in C major
    'Fmaj7': (41, [53, 57, 60, 64]), 'G6': (43, [55, 59, 62, 64]), 'Em7': (40, [52, 55, 59, 62]),
    'Am7': (45, [57, 60, 64, 67]), 'Dm9': (38, [53, 57, 60, 64]), 'G9sus': (43, [53, 57, 60, 62]),
    'Cmaj9': (36, [52, 55, 59, 62]), 'Am9': (45, [55, 60, 64, 71]),
}
SECTIONS = [['Fmaj7', 'G6', 'Em7', 'Am7'] * 2, ['Dm9', 'G9sus', 'Cmaj9', 'Am9'] * 2]
COMPS = [  # (beat, length in beats, velocity) per bar
    [(0, 2.5, .55), (2.5, 1.5, .38)],
    [(0, 1.5, .52), (1.5, 1.0, .36), (3.0, 1.0, .34)],
    [(0, 4.0, .50)],
    [(0, 2.0, .52), (2.5, 0.5, .32), (3.0, 1.0, .36)],
]


def make_bgm(total, seed=11, bpm=76, intro=2.5, outro_at=None):
    """Gentle lo-fi bed (electric piano, pad, bass, soft drums), stereo, peak-normalised.

    intro: seconds before drums come in; outro_at: time to stop the groove and
    let a final Cmaj9 ring out (the end card).
    """
    rng = np.random.default_rng(seed)
    beat = 60 / bpm
    bar = 4 * beat
    swing = 0.06 * beat
    L = int((total + 4) * SR)
    ep, pads, bs, dr = np.zeros(L), np.zeros((2, L)), np.zeros(L), np.zeros(L)
    pad_cache = {}
    end_bar = int(np.ceil(total / bar))
    if outro_at is not None:
        end_bar = min(end_bar, max(1, int(round(outro_at / bar))))
    for bi in range(end_bar + 1):
        t0 = bi * bar
        final = bi == end_bar
        name = 'Cmaj9' if final else SECTIONS[(bi // 8) % 2][bi % 8]
        root, voic = CHORDS[name]
        hold = (total - t0 + 0.5) if final else bar
        key = (name, round(hold, 2))
        if key not in pad_cache:
            pad_cache[key] = pad(voic, hold, rng)
        _add(pads, pad_cache[key], t0)
        comp = [(0, hold / beat, .5)] if final else COMPS[rng.integers(len(COMPS))]
        for b, d, v in comp:
            st = t0 + b * beat + (swing if b % 1 else 0)
            notes = voic if v > .45 else voic[1:]
            for k, m in enumerate(notes):
                vel = v * (1 + rng.normal(0, .06))
                _add(ep, epiano(m, d * beat, vel, rng), st + k * 0.011 + rng.normal(0, .005))
        _add(bs, bass(root, (hold if final else 1.6 * beat), .8), t0)
        if final:
            break
        _add(bs, bass(root + (7 if rng.random() < .3 else 0), 1.2 * beat, .55), t0 + 2.5 * beat + swing)
        if bi % 4 == 3 and rng.random() < .55:  # little pentatonic fill closing a phrase
            step = int(rng.integers(5, 9))
            for j in range(int(rng.integers(3, 5))):
                step = int(np.clip(step + rng.choice([-2, -1, 1, 2]), 4, 10))
                _add(ep, epiano(penta(60, step), .45 * beat, .18, rng), t0 + (2 + .5 * j) * beat + (swing if j % 2 else 0))
        if t0 >= intro:  # soft kit enters after the cover
            for b in (0, 2.5):
                _add(dr, kick(.75 if b == 0 else .5), t0 + b * beat + (swing if b % 1 else 0))
            for b in (1, 3):
                _add(dr, brush(.55, rng), t0 + b * beat)
            for k in range(8):
                _add(dr, shaker(.3 if k % 2 == 0 else .2, rng), t0 + k * .5 * beat + (swing if k % 2 else 0))

    ir = reverb_ir(rng)
    t = _t(L)
    pan = 0.5 + 0.18 * np.sin(2 * np.pi * 0.07 * t)
    ep_st = np.stack([ep * np.sqrt(1 - pan), ep * np.sqrt(pan)])
    bs = signal.sosfilt(_sos('lowpass', 280), bs)
    dry = 0.55 * ep_st + 0.30 * pads + 0.38 * bs + 0.24 * dr
    send = 0.28 * ep_st + 0.35 * pads + 0.06 * dr
    wet = np.stack([signal.oaconvolve(send[c], ir[c])[:L] for c in range(2)])
    x = dry + 0.5 * wet
    x = signal.sosfilt(_sos('highpass', 35), x, axis=1)
    x = signal.sosfilt(_sos('lowpass', 8000, 4), x, axis=1)
    b, a = _peq(2500, -3.0, 0.8)  # leave room for the voice
    x = signal.lfilter(b, a, x, axis=1)
    x = np.tanh(1.2 * x / np.abs(x).max()) / np.tanh(1.2)
    fade_in = np.clip(t / 1.2, 0, 1)
    fade_out = np.clip((total - t) / 2.5, 0, 1)
    x = x * fade_in * fade_out
    return (x[:, :int(total * SR)] * 0.9).astype(np.float32)


def _glass(m, dur, vel):
    """Soft bell: two sines with a quick decay, for arpeggios that should not bark like a piano."""
    f = hz(m)
    n = int((dur + 4.5) * SR)  # tau 0.9 s rings out to about -45 dB (dur + 1.8 cut it at -17 dB)
    t = _t(n)
    x = np.sin(2 * np.pi * f * t) + 0.25 * np.sin(2 * np.pi * 2.01 * f * t) * np.exp(-t / 0.25)
    env = (1 - np.exp(-t / 0.004)) * np.exp(-t / 0.9)
    return x * env * vel


AMBIENT = ['Fmaj7', 'Cmaj9', 'Am9', 'G9sus']


def make_ambient(total, seed=3, bpm=64, arp=False, outro_at=None):
    """Slow, drumless bed: long pads, a few high piano notes, a lot of air. arp=True adds a quiet
    glassy arpeggio for explainers that should feel like motion (the 原理动画 bed, 'glass')."""
    rng = np.random.default_rng(seed)
    beat = 60 / bpm
    chord_len = 8 * beat
    L = int((total + 6) * SR)
    pads, keys = np.zeros((2, L)), np.zeros(L)
    end = total if outro_at is None else max(chord_len, outro_at)
    k = 0
    while k * chord_len < end + 0.01:
        t0 = k * chord_len
        final = (k + 1) * chord_len >= end
        name = 'Cmaj9' if final else AMBIENT[k % len(AMBIENT)]
        root, voic = CHORDS[name]
        hold = (total - t0 + 1.0) if final else chord_len + 1.5
        _add(pads, pad([root + 12] + voic, hold, rng), t0)
        if arp and not final:
            notes = [voic[0] + 12, voic[1] + 12, voic[2] + 12, voic[3] + 12, voic[2] + 12, voic[1] + 12]
            for j in range(16):
                if rng.random() < 0.82:
                    _add(keys, _glass(notes[j % len(notes)], .5 * beat, .16 + .05 * rng.random()), t0 + j * .5 * beat)
        else:
            for j in range(int(rng.integers(2, 4))):  # a few notes, never on a grid
                m = penta(72, int(rng.integers(0, 7)))
                _add(keys, epiano(m, 1.5 * beat, .14 + .06 * rng.random(), rng), t0 + rng.uniform(0.5, chord_len - 1.5))
        if final:
            break
        k += 1
    ir = reverb_ir(rng, rt=3.2)
    t = _t(L)
    pan = 0.5 + 0.25 * np.sin(2 * np.pi * 0.05 * t)
    keys_st = np.stack([keys * np.sqrt(1 - pan), keys * np.sqrt(pan)])
    dry = 0.42 * pads + 0.45 * keys_st
    send = 0.5 * pads + 0.55 * keys_st
    x = dry + 0.8 * np.stack([signal.oaconvolve(send[c], ir[c])[:L] for c in range(2)])
    x = signal.sosfilt(_sos('highpass', 40), x, axis=1)
    x = signal.sosfilt(_sos('lowpass', 7000, 4), x, axis=1)
    b, a = _peq(2500, -4.0, 0.8)  # leave room for the voice
    x = signal.lfilter(b, a, x, axis=1)
    x = np.tanh(1.1 * x / np.abs(x).max()) / np.tanh(1.1)
    x = x * np.clip(t / 3.0, 0, 1) * np.clip((total - t) / 3.5, 0, 1)
    return (x[:, :int(total * SR)] * 0.9).astype(np.float32)


def make_pulse(total, seed=7, bpm=112, intro=0.0, outro_at=None):
    """Driving bed for promos and short cuts: four-on-the-floor kick, off-beat hats, eighth-note
    bass, a plucked arpeggio over Am7-Fmaj7-Cmaj9-G6, a pad. Stereo, peak-normalised.

    Cut on its bars (one bar = 240 / bpm seconds) and the picture lands with the music."""
    rng = np.random.default_rng(seed)
    beat = 60 / bpm
    bar = 4 * beat
    L = int((total + 4) * SR)
    pl, pads, bs, dr = np.zeros(L), np.zeros((2, L)), np.zeros(L), np.zeros(L)
    prog = ['Am7', 'Fmaj7', 'Cmaj9', 'G6']
    end_bar = int(np.ceil(total / bar))
    if outro_at is not None:
        end_bar = min(end_bar, max(1, int(round(outro_at / bar))))
    order = [0, 2, 1, 3, 2, 1, 3, 2]
    for bi in range(end_bar + 1):
        t0 = bi * bar
        final = bi == end_bar
        root, voic = CHORDS['Am9' if final else prog[bi % 4]]
        hold = (total - t0 + 0.5) if final else bar
        _add(pads, pad(voic, hold, rng), t0)
        if final:
            _add(bs, bass(root, hold, .8), t0)
            for k, m in enumerate(voic):
                _add(pl, epiano(m + 12, hold, .45, rng), t0 + k * 0.012)
            break
        for k in range(8):  # arpeggio, eighths, an octave up
            _add(pl, epiano(voic[order[k]] + 12, 0.42 * beat, .42 if k % 2 == 0 else .3, rng), t0 + k * beat / 2)
            _add(bs, bass(root + (12 if k % 2 else 0), 0.42 * beat, .75 if k % 2 == 0 else .5), t0 + k * beat / 2)
        if t0 >= intro:
            for b in range(4):
                _add(dr, kick(.9), t0 + b * beat)
                _add(dr, shaker(.55, rng), t0 + (b + .5) * beat)
            for b in (1, 3):
                _add(dr, brush(.8, rng), t0 + b * beat)
    ir = reverb_ir(rng, rt=1.1)
    t = _t(L)
    pan = 0.5 + 0.25 * np.sin(2 * np.pi * (bpm / 60 / 8) * t)
    pl_st = np.stack([pl * np.sqrt(1 - pan), pl * np.sqrt(pan)])
    bs = signal.sosfilt(_sos('lowpass', 320), bs)
    dry = 0.42 * pl_st + 0.22 * pads + 0.5 * bs + 0.42 * dr
    send = 0.3 * pl_st + 0.3 * pads
    wet = np.stack([signal.oaconvolve(send[c], ir[c])[:L] for c in range(2)])
    x = signal.sosfilt(_sos('highpass', 30), dry + 0.45 * wet, axis=1)
    x = np.tanh(1.4 * x / np.abs(x).max()) / np.tanh(1.4)
    x = x * np.clip(t / 0.3, 0, 1) * np.clip((total - t) / 1.5, 0, 1)
    return (x[:, :int(total * SR)] * 0.9).astype(np.float32)


def load_music(path, total, ffmpeg='ffmpeg', fade=2.0):
    """A music file (the user's own, licensed for this use) as a stereo bed of `total` seconds, looped if short."""
    import subprocess
    raw = subprocess.run([ffmpeg, '-v', 'error', '-i', str(path), '-f', 'f32le', '-ac', '2', '-ar', str(SR), '-'],
                         capture_output=True, check=True).stdout
    x = np.frombuffer(raw, dtype=np.float32).reshape(-1, 2).T
    n = int(total * SR)
    if x.shape[1] < n:
        x = np.tile(x, (1, n // x.shape[1] + 1))
    x = x[:, :n].copy()
    t = _t(n)
    x *= np.clip((total - t) / fade, 0, 1)
    return (x / (np.abs(x).max() + 1e-9) * 0.9).astype(np.float32)


# ---------------------------------------------------------------- effects

def _pop(m):
    n = int(0.3 * SR)  # tau 0.05 s: 0.3 s is -52 dB (0.14 s ended it on a click at -24 dB)
    t = _t(n)
    ph = 2 * np.pi * np.cumsum(hz(m) * (0.62 + 0.38 * (1 - np.exp(-t / 0.018)))) / SR
    x = np.sin(ph) * np.exp(-t / 0.05) + 0.25 * np.sin(2 * ph) * np.exp(-t / 0.02)
    return x * (1 - np.exp(-t / 0.002))


def _tone(m, dec=0.35):
    """Marimba-like strike."""
    f = hz(m)
    n = int(dec * 6 * SR)  # six time constants: -52 dB (3.5 cut the ring at -30 dB)
    t = _t(n)
    x = (np.sin(2 * np.pi * f * t) * np.exp(-t / dec)
         + 0.35 * np.sin(2 * np.pi * 3.9 * f * t) * np.exp(-t / (dec * .18))
         + 0.12 * np.sin(2 * np.pi * 9.2 * f * t) * np.exp(-t / .012))
    return x * (1 - np.exp(-t / .0015))


def _bell(m, dec=1.1):
    f = hz(m)
    n = int(dec * 6 * SR)
    t = _t(n)
    x = np.sin(2 * np.pi * f * t + 1.6 * np.exp(-t / .25) * np.sin(2 * np.pi * 3.5 * f * t))
    return x * np.exp(-t / dec) * (1 - np.exp(-t / .002))


def _noise_sweep(dur, rng, f_lo, f_hi, width=0.7):
    """Noise through a band-pass whose centre rises then falls (a whoosh)."""
    n = int(dur * SR)
    frame, hop = 1024, 256
    win = np.hanning(frame)
    noise = rng.standard_normal(n + frame)
    out = np.zeros(n + frame)
    freqs = np.maximum(np.fft.rfftfreq(frame, 1 / SR), 1)
    for i in range(0, n, hop):
        p = i / n
        c = f_lo * (f_hi / f_lo) ** (np.sin(np.pi * min(1.0, p * 1.1)) ** 1.5)
        g = np.exp(-0.5 * (np.log2(freqs / c) / width) ** 2)
        out[i:i + frame] += np.fft.irfft(np.fft.rfft(noise[i:i + frame] * win) * g) * win
    p = np.clip(_t(n) / dur, 0, 1)
    env = p ** 1.2 * (1 - p) ** 0.9
    return out[:n] * env / env.max()


def _seq(parts):
    """[(offset_seconds, signal)] -> one signal."""
    y = np.zeros(max(int(o * SR) + len(x) for o, x in parts))
    for o, x in parts:
        y[int(o * SR):int(o * SR) + len(x)] += x
    return y


def _stereo(x, pan=0.5):
    return np.stack([x * np.sqrt(1 - pan), x * np.sqrt(pan)])


def render_sfx(ev, rng):
    k = ev['k']
    if k == 'pop':
        return _stereo(_pop(ev.get('m', 79)))
    if k == 'tone':
        return _stereo(_tone(ev.get('m', 76)))
    if k == 'bar':
        return _stereo(_tone(ev.get('m', 72), dec=0.22))
    if k == 'chime':
        m = ev.get('m', 79)
        return _stereo(_seq([(0, _bell(m)), (0.11, 0.8 * _bell(m + 5))]))
    if k == 'wrong':
        return _stereo(_seq([(0, _tone(64, dec=.18)), (0.14, _tone(60, dec=.25))]))
    if k == 'whoosh':
        x = _noise_sweep(0.5, rng, 260, 3000)
        p = np.linspace(0.3, 0.7, len(x))
        return np.stack([x * np.sqrt(1 - p), x * np.sqrt(p)])
    if k == 'wipe':
        return _stereo(_noise_sweep(0.3, rng, 900, 4200, width=0.6))
    if k == 'swish':  # a soft marker stroke: airy noise that swells and fades, no tremolo
        # Until 2026-10-31 this was 2.2-7 kHz hiss with an 11 Hz tremolo: exactly what radio static
        # sounds like, and the author heard it as an intermittent 「电流滋滋」 under the voice.
        d = ev.get('d', 0.6)
        n = int(d * SR)
        t = _t(n)
        x = signal.sosfilt(_sos('bandpass', [700, 3200]), rng.standard_normal(n))
        x = signal.sosfilt(_sos('lowpass', 4500, 4), x)
        u = np.clip(t / d, 0, 1)
        env = np.sin(np.pi * np.minimum(1, u / .25) / 2) ** 2 * (1 - .35 * u) * np.cos(np.pi * np.maximum(0, u - .7) / .6) ** 2
        x *= env
        return _stereo(x / (np.abs(x).max() + 1e-9))
    if k == 'keys':  # soft keyboard clicks while a prompt types itself
        d = ev.get('d', 1.0)
        out, t = np.zeros(int((d + 0.1) * SR)), 0.0
        while t < d:
            n = int(rng.uniform(0.010, 0.016) * SR)
            c = signal.sosfilt(_sos('bandpass', [1800, 6500]), rng.standard_normal(n)) * np.exp(-_t(n) / 0.0035)
            i = int(t * SR)
            out[i:i + n] += c * rng.uniform(0.55, 1.0)
            t += rng.uniform(0.055, 0.11)
        return _stereo(out / np.abs(out).max(), pan=rng.uniform(0.4, 0.6))
    if k == 'click':  # mouse button: press and release 70 ms apart
        def snap(f):
            n = int(0.025 * SR)
            return signal.sosfilt(_sos('bandpass', [f, f * 2.6]), rng.standard_normal(n)) * np.exp(-_t(n) / 0.003)
        return _stereo(_seq([(0, snap(2400)), (0.07, 0.6 * snap(3000))]))
    if k in ('impact', 'thud'):  # a landing: falling sub tone + a felt transient
        dur = 0.5 if k == 'impact' else 0.8
        n = int(dur * 1.6 * SR)  # ends near -50 dB instead of being cut at -30 dB
        t = _t(n)
        f0, f1 = (110, 48) if k == 'impact' else (80, 36)
        body = np.sin(2 * np.pi * np.cumsum(f1 + (f0 - f1) * np.exp(-t / 0.05)) / SR) * np.exp(-t / (dur / 3.5))
        click_ = signal.sosfilt(_sos('lowpass', 3000), rng.standard_normal(n)) * np.exp(-t / 0.008)
        return _stereo(np.tanh(1.6 * (body + 0.35 * click_)))
    if k == 'tick':  # a small dry tick for staccato words and counters
        n = int(0.05 * SR)
        x = signal.sosfilt(_sos('bandpass', [3000, 9000]), rng.standard_normal(n)) * np.exp(-_t(n) / 0.004)
        return _stereo(x + 0.4 * np.sin(2 * np.pi * 1800 * _t(n)) * np.exp(-_t(n) / 0.01))
    if k == 'whip':  # a fast whoosh for a whip pan or a push through
        return _stereo(_noise_sweep(0.32, rng, 500, 6000, width=0.5))
    if k == 'riser':  # noise rising into a reveal; place it to end where the reveal lands
        d = ev.get('d', 1.2)
        n = int(d * SR)
        t = _t(n)
        x = _noise_sweep(d, rng, 300, 7000, width=0.9)
        return _stereo(_fade_tail(x * (t / d) ** 2 / (np.abs(x * (t / d) ** 2).max() + 1e-9), 0.04))
    raise KeyError(k)


# peak level of each effect; calibrated so the loudest 50 ms of a pop/tone sits
# ~10 dB under the voice's loud syllables (voice p90 ≈ -15 dBFS in the final mix)
GAIN = {'pop': .092, 'tone': .078, 'bar': .032, 'chime': .10, 'wrong': .11, 'whoosh': .10, 'wipe': .075, 'swish': .05,
        'keys': .05, 'click': .09, 'impact': .16, 'thud': .15, 'tick': .06, 'whip': .085, 'riser': .07}


def sfx_for(el):
    """Default effect for an element (None = silent)."""
    if el.get('sfx', 'auto') != 'auto':
        return el['sfx']
    a, k = el['a'], el.get('kind')
    if a in ('pop', 'zoom'):
        return 'pop'
    return {'mark': 'swish', 'cross': 'wrong', 'box': 'tone', 'bar': 'bar', 'row': 'wipe',
            'check': 'pop', 'prompt': 'keys', 'marker': 'swish', 'strike': 'swish',
            'card': 'tone', 'step': 'tone', 'stat': 'tone'}.get(k)


def sfx_events(plan, elem, slide_sfx):
    """Effect cues from the timeline: [{'t', 'k', ...}] sorted by time."""
    ev = []
    for si, s in enumerate(plan['slides']):
        if si and slide_sfx[si]:
            ev.append({'t': s['start'] - 0.12, 'k': slide_sfx[si]})
    trig = sorted(plan['trig'].items(), key=lambda kv: kv[1][0])
    seq = {}  # family -> (last_t, step), so quick runs climb the scale
    for eid, (st, d) in trig:
        el = elem[eid]
        k = sfx_for(el)
        if not k:
            continue
        e = {'t': st, 'k': k}
        if k in ('pop', 'tone', 'chime'):
            last, step = seq.get(k, (-9, -1))
            step = step + 1 if st - last < 1.4 else 0
            seq[k] = (st, step)
            e['m'] = penta({'pop': 72, 'tone': 72, 'chime': 79}[k], min(step, 7))
        elif k == 'bar':  # a run of bars climbs the scale like a harp
            last, step = seq.get(k, (-9, -1))
            step = step + 1 if st - last < 0.4 else 0
            seq[k] = (st, step)
            e['m'] = penta(67, step % 10)
        elif k in ('swish', 'keys'):
            e['d'] = d
        elif k == 'wrong':
            e['t'] = st + d * 0.5
        ev.append(e)
    ev.sort(key=lambda e: e['t'])
    out, last = [], {}
    for e in ev:  # drop near-duplicates of the same sound
        gap = 0.035 if e['k'] == 'bar' else 0.08
        if e['t'] - last.get(e['k'], -9) >= gap:
            out.append(e)
            last[e['k']] = e['t']
    return out


def pitch_run(events):
    """Scene sounds (Slide.sound) with pitches: quick runs of tones climb the scale like entrances do."""
    out, seq = [], {}
    for e in sorted(events, key=lambda e: e['t']):
        e = dict(e)
        if e['k'] in ('pop', 'tone', 'chime') and 'm' not in e:
            last, step = seq.get(e['k'], (-9, -1))
            step = step + 1 if e['t'] - last < 1.4 else 0
            seq[e['k']] = (e['t'], step)
            e['m'] = penta({'pop': 72, 'tone': 72, 'chime': 79}[e['k']], min(step, 7))
        out.append(e)
    return out


def render_sfx_track(events, total, seed=5, gain=1.0):
    rng = np.random.default_rng(seed)
    buf = np.zeros((2, int((total + 2) * SR)))
    for e in events:
        x = render_sfx(e, rng)
        _add(buf, x / np.abs(x).max() * GAIN[e['k']] * gain, e['t'])  # _add fades every tail
    return buf[:, :int(total * SR)].astype(np.float32)


# ---------------------------------------------------------------- loudness + mix

def lufs(x):
    """Integrated loudness (ITU-R BS.1770-4) of a (channels, n) array at 48 kHz."""
    x = np.atleast_2d(np.asarray(x, dtype=np.float64))
    b1, a1 = [1.53512485958697, -2.69169618940638, 1.19839281085285], [1, -1.69065929318241, 0.73248077421585]
    b2, a2 = [1.0, -2.0, 1.0], [1, -1.99004745483398, 0.99007225036621]
    y = signal.lfilter(b2, a2, signal.lfilter(b1, a1, x, axis=1), axis=1)
    blk, hop = int(0.4 * SR), int(0.1 * SR)
    n = 1 + (y.shape[1] - blk) // hop
    if n <= 0:
        return -70.0
    cs = np.cumsum(np.pad(y ** 2, ((0, 0), (1, 0))), axis=1)
    ms = ((cs[:, blk::hop][:, :n] - cs[:, 0:-blk:hop][:, :n]) / blk).sum(0)
    with np.errstate(divide='ignore'):
        lk = -0.691 + 10 * np.log10(ms)
    g = ms[lk > -70]
    if not len(g):
        return -70.0
    rel = -0.691 + 10 * np.log10(g.mean()) - 10
    g = ms[(lk > -70) & (lk > rel)]
    return float(-0.691 + 10 * np.log10(g.mean()))


def duck_curve(voice, depth_db, attack=0.08, release=0.5):
    """Gain curve that dips the music while the voice is talking."""
    hop = SR // 100
    n = len(voice) // hop
    rms = np.sqrt((voice[:n * hop].reshape(n, hop) ** 2).mean(1) + 1e-12)
    db = 20 * np.log10(rms)
    act = (db > db.max() - 38).astype(float)
    sm = np.zeros(n)
    ka, kr = 1 - np.exp(-1 / (attack * 100)), 1 - np.exp(-1 / (release * 100))
    v = 0.0
    for i in range(n):
        v += (ka if act[i] > v else kr) * (act[i] - v)
        sm[i] = v
    g = 10 ** (-depth_db * sm / 20)
    return np.interp(np.arange(len(voice)), np.arange(n) * hop + hop / 2, g)


def mix(voice, bgm, sfx, bgm_lu=-21.0, duck_db=4.0, target=-16.0, ref_lufs=None):
    """voice mono; bgm/sfx stereo. Returns (mix, stems) all scaled to the target loudness.

    bgm_lu: music loudness relative to the voice (before ducking). Effect gains
    in GAIN are tuned for a voice at -18 LUFS and follow the voice level.
    """
    n = len(voice)
    v = np.stack([voice, voice])
    lv = lufs(v) if ref_lufs is None else ref_lufs  # no narration: a nominal voice level keeps the balance
    b = np.zeros((2, n), np.float32)
    s = np.zeros((2, n), np.float32)
    if bgm is not None:
        m = min(n, bgm.shape[1])
        b[:, :m] = bgm[:, :m] * 10 ** ((lv + bgm_lu - lufs(bgm[:, :m])) / 20)
        if ref_lufs is None:
            b *= duck_curve(voice, duck_db)
    if sfx is not None:
        m = min(n, sfx.shape[1])
        s[:, :m] = sfx[:, :m] * 10 ** ((lv + 18) / 20)
    out = v + b + s
    g = 10 ** ((target - lufs(out)) / 20)
    return out * g, {'voice': v * g, 'bgm': b * g, 'sfx': s * g}


def limit(x, ceiling=0.78, release=0.08):
    """Look-ahead peak limiter on 1 ms blocks (sample peaks at -2.2 dBFS, so true peaks after AAC stay under -1.5)."""
    from scipy.ndimage import minimum_filter1d
    x = np.atleast_2d(x)
    blk = SR // 1000
    n = x.shape[1]
    nb = -(-n // blk)
    pk = np.pad(np.abs(x).max(0), (0, nb * blk - n)).reshape(nb, blk).max(1)
    g = minimum_filter1d(np.minimum(1.0, ceiling / np.maximum(pk, 1e-9)), 7)
    step = 1 - np.exp(-1 / (release * 1000))
    out = g.copy()
    for i in range(1, nb):  # gain recovers slowly, drops instantly
        out[i] = min(g[i], out[i - 1] + (1 - out[i - 1]) * step)
    gs = np.interp(np.arange(n), np.arange(nb) * blk + blk / 2, out)
    return np.clip(x * gs, -ceiling, ceiling).astype(np.float32)
