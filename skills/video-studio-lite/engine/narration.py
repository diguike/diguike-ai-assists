"""Level independently generated sentences without removing speech or changing time.

TTS takes can have identical words and very different loudness. A single gain on
the whole page preserves those jumps. Gains here stay constant within a sentence
and blend at its boundary; this is not a fast compressor riding every syllable.
"""
import re

import numpy as np


def active_rms(x, sr):
    hop = max(1, int(sr * .02))
    n = len(x) // hop
    if not n:
        return 0.0
    rms = np.sqrt(np.mean(x[:n * hop].reshape(n, hop) ** 2, axis=1))
    voiced = rms[rms > 10 ** (-45 / 20)]
    return float(np.sqrt(np.mean(voiced ** 2))) if len(voiced) else 0.0


def level_sentences(x, sr, text, words, target_db=-21.0, max_gain_db=8.0):
    """Return same-length audio and measurements; word events are left untouched."""
    spans, start = [], 0
    for m in re.finditer(r'[。！？!?；;\n]+', text):
        spans.append((start, m.end()))
        start = m.end()
    if start < len(text):
        spans.append((start, len(text)))
    regions = []
    for a, b in spans:
        ws = [w for w in words if a <= w[0] < b]
        if ws:
            lo = max(0, int(ws[0][2] * sr))
            hi = min(len(x), int(ws[-1][3] * sr))
            rms = active_rms(x[lo:hi], sr)
            before = 20 * np.log10(rms) if rms else None
            gain = float(np.clip(target_db - before, -max_gain_db, max_gain_db)) if rms else 0.0
            regions.append({'text': text[a:b], 'start': lo / sr, 'end': hi / sr,
                            'before_dbfs': float(before) if before is not None else None,
                            'gain_db': gain})
    if not regions:
        return x.copy(), []
    boundaries = [0] + [int((a['end'] + b['start']) * .5 * sr)
                        for a, b in zip(regions, regions[1:])] + [len(x)]
    boundaries = np.maximum.accumulate(np.clip(boundaries, 0, len(x)))
    envelope = np.ones(len(x), np.float32)
    for i, r in enumerate(regions):
        envelope[boundaries[i]:boundaries[i + 1]] = 10 ** (r['gain_db'] / 20)
    # Blend gains over 20 ms, leaving the original speech and pauses in place.
    radius = int(.01 * sr)
    for i, point in enumerate(boundaries[1:-1]):
        lo, hi = max(0, point - radius), min(len(x), point + radius)
        phase = (1 - np.cos(np.linspace(0, np.pi, hi - lo))) * .5
        a, b = (10 ** (regions[k]['gain_db'] / 20) for k in (i, i + 1))
        envelope[lo:hi] = a + (b - a) * phase
    out = (x * envelope).astype(np.float32)
    for r in regions:
        rms = active_rms(out[int(r['start'] * sr):int(r['end'] * sr)], sr)
        r['after_dbfs'] = float(20 * np.log10(rms)) if rms else None
    return out, regions


def _gauss(sigma_frames):
    r = max(1, int(3 * sigma_frames))
    k = np.exp(-.5 * (np.arange(-r, r + 1) / sigma_frames) ** 2)
    return k / k.sum()


def _filt(v, k, pad='constant'):
    """Same-length convolution with an odd kernel, also when v is shorter than k."""
    r = len(k) // 2
    return np.convolve(np.pad(v, r, mode=pad), k, 'valid')


def ride(x, sr, target_db=-21.0, tol_db=2.5, max_db=6.0, sigma=.3):
    """Slow leveller inside sentences: a stretch that sags (or swells) more than tol_db from the
    target is brought back to tol_db; the rest is left alone.

    A clone take often fades over a long sentence (「……的钱去扛回撤」 ends 12 dB below its start),
    which a gain per sentence cannot fix. The level is a 0.3 s average over speech frames, so a
    syllable's own stress and the dip between syllables keep their shape. Frames 30 dB under the
    loudest are not speech (breaths, room, the decay of a word) and never set the level.
    """
    hop = int(sr * .01)
    n = len(x) // hop
    if n < 10:
        return x.copy(), {'max_lift_db': 0.0, 'max_cut_db': 0.0, 'seconds_changed': 0.0}
    p = (x[:n * hop].reshape(n, hop).astype(np.float64) ** 2).mean(1)
    db = 10 * np.log10(p + 1e-12)
    voiced = ((db > -45) & (db > db.max() - 30)).astype(np.float64)
    k = _gauss(sigma / .01)
    num, den = _filt(p * voiced, k), _filt(voiced, k)
    ok = den > .2  # enough speech under the window to call it a level
    corr = np.zeros(n)
    if ok.any():
        c = target_db - 10 * np.log10(num[ok] / den[ok])
        c = np.clip(np.sign(c) * np.maximum(0, np.abs(c) - tol_db), -max_db, max_db)
        corr = _filt(np.interp(np.arange(n), np.flatnonzero(ok), c), _gauss(.08 / .01), 'edge')
    g = np.interp(np.arange(len(x)), np.arange(n) * hop + hop / 2, 10 ** (corr / 20))
    return (x * g).astype(np.float32), {'max_lift_db': round(float(corr.max()), 2),
                                        'max_cut_db': round(float(-corr.min()), 2),
                                        'seconds_changed': round(float((np.abs(corr) > 1).sum() * .01), 2)}


# Shortest pause after each mark, in seconds: a hierarchy, not one length for every mark. A full
# stop or a question gets a clear beat (listeners heard sentences "crash into each other" at
# 0.35 s); a comma only gets a breath. 、 is a list separator and keeps whatever the voice did.
GAPS = {'，': .15, ',': .15, '：': .22, ':': .22, '；': .3, ';': .3,
        '。': .5, '！': .5, '!': .5, '？': .55, '?': .55}


def open_pauses(x, sr, text, words, gaps=None, min_quiet=.02):
    """Lengthen pauses shorter than gaps[mark] between two words. Returns (audio, words, report).

    Silence only goes into a pause the voice already took (at least min_quiet of quiet): the pause
    gets longer, nothing is cut. Where the take runs straight through a mark there is no such spot;
    it is reported (how: 'run-on') and left alone. Cutting into a gliding syllable to force a pause
    sounded like a catch of breath (2026-10-21), so the fix for a run-on is another take: myvoice-tts
    already prefers takes that pause at commas.
    """
    gaps = GAPS if gaps is None else gaps
    hop = max(1, int(sr * .005))
    n = len(x) // hop
    if not gaps or len(words) < 2 or n < 4:
        return x.copy(), list(words), []
    db = 10 * np.log10((x[:n * hop].reshape(n, hop).astype(np.float64) ** 2).mean(1) + 1e-12)
    quiet = max(db.max() - 40, -60)
    plan, report = [], []
    for i in range(len(words) - 1):
        (_, b, _, t1), (a2, _, t0n, _) = words[i], words[i + 1]
        marks = [c for c in text[b:a2] if c in gaps]
        if not marks:
            continue
        want = max(gaps[c] for c in marks)
        lo, hi = max(0, int((min(t1, t0n) - .06) / .005)), min(n, int((max(t1, t0n) + .06) / .005) + 1)
        if hi - lo < 2:
            continue
        best = run = 0
        best_at = lo
        for j, q in enumerate(db[lo:hi] < quiet):
            run = run + 1 if q else 0
            if run > best:
                best, best_at = run, lo + j - run + 1
        have = best * .005
        ctx = f'{text[max(0, b - 6):b]}{"".join(marks)}|{text[a2:a2 + 6]}'
        if have >= want:
            continue
        if have < min_quiet:
            report.append({'at': round(t1, 3), 'text': ctx, 'have': round(have, 3), 'added': 0.0, 'how': 'run-on'})
            continue
        at = (best_at + best / 2) * hop
        plan.append((int(at), int((want - have) * sr), i))
        report.append({'at': round(t1, 3), 'text': ctx, 'have': round(have, 3), 'added': round(want - have, 3), 'how': 'silence'})
    out, pos, shift = [], 0, [0.0] * len(words)
    for at, add, i in plan:
        if at <= pos:
            continue
        out += [x[pos:at], np.zeros(add, np.float32)]
        pos = at
        for w in range(i + 1, len(words)):
            shift[w] += add / sr
    out.append(x[pos:])
    moved = [(a, b, t0 + shift[w], t1 + shift[w]) for w, (a, b, t0, t1) in enumerate(words)]
    return np.concatenate(out).astype(np.float32), moved, report


def tame_breaths(x, sr, text, words, cut_db=10.0):
    """Turn down a loud inhale in front of a sentence. Returns (audio, report).

    The stretch before a sentence's first word is checked for 120 ms or more of aperiodic sound
    (not a vowel) between 45 and 12 dB under the speech. Everything up to 120 ms before the word is
    lowered by cut_db, then it ramps back to full level 60 ms before the word, so a fricative at the
    start of the word (s, sh, x) is never touched and the breath fades in instead of popping out of
    silence.
    """
    hop = int(sr * .01)
    n = len(x) // hop
    if n < 20 or not words:
        return x.copy(), []
    fr = x[:n * hop].reshape(n, hop).astype(np.float64)
    db = 10 * np.log10((fr ** 2).mean(1) + 1e-12)
    level = np.percentile(db, 95)
    starts = [0] + [k + 1 for k in range(len(words) - 1) if re.search(r'[。！？!?；;\n]', text[words[k][1]:words[k + 1][0]])]
    gain, report = np.ones(len(x), np.float32), []
    for k in starts:
        t_word = words[k][2]
        a, b = max(0, int((t_word - .45) / .01)), int((t_word - .03) / .01)
        if b - a < 12:
            continue
        loud = (db[a:b] > level - 45) & (db[a:b] < level - 12) & ~_periodic(fr[a:b], sr)
        run = 0
        for j in range(len(loud) - 1, -1, -1):  # the stretch that ends at the word
            if not loud[j]:
                break
            run += 1
        if run < 12:
            continue
        s0, s1, s2 = (b - run) * hop, max((b - run) * hop, int((t_word - .12) * sr)), int((t_word - .06) * sr)
        if s1 - s0 < int(.04 * sr):
            continue
        g = 10 ** (-cut_db / 20)
        ramp = int(.02 * sr)
        gain[max(0, s0 - ramp):s0] *= np.linspace(1, g, s0 - max(0, s0 - ramp))
        gain[s0:s1] *= g
        gain[s1:s2] *= np.linspace(g, 1, s2 - s1)
        report.append({'at': round(t_word, 3), 'text': text[words[k][0]:words[k][0] + 8], 'breath_s': round(run * .01, 2)})
    return (x * gain).astype(np.float32), report


def quiet_floor(x, sr, words, depth_db=14.0, hp_hz=70.0):
    """Turn the take's own background (the hiss and hum the clone copies from its reference) down
    between words. Returns (audio, report).

    A cloned voice carries the room of its reference under every word and in every pause. The old
    reference (a 2021 screen recording) put that noise only ~31 dB under the speech, and myvoice-tts
    joins sentences with digital silence, so the hiss switched on and off a dozen times a minute: the
    author heard it as an intermittent electric buzz (「滋滋滋」, V11, 2026-10-28). Speech is never
    touched: each aligned word keeps 60 ms before and 120 ms after it (quiet consonants, word tails),
    and so does any frame within 30 dB of the speech that stands 8 dB over the take's floor.
    Everything else ramps down by depth_db over about 70 ms, so at a sentence break the hiss fades
    out before the silence instead of stopping dead. A gentle high-pass at hp_hz takes out the hum
    below the voice.
    """
    from scipy import signal
    y = x.astype(np.float64)
    if hp_hz:
        y = signal.sosfiltfilt(signal.butter(2, hp_hz, 'hp', fs=sr, output='sos'), y)
    hop = int(sr * .01)
    n = len(y) // hop
    if n < 20:
        return y.astype(np.float32), {}
    db = 10 * np.log10((y[:n * hop].reshape(n, hop) ** 2).mean(1) + 1e-12)
    live = db > -90  # digital silence (pauses inserted between sentences) is not part of the floor
    if not live.any():
        return y.astype(np.float32), {}
    speech, floor = np.percentile(db[live], 95), np.percentile(db[live], 10)
    keep = (db > speech - 30) & (db > floor + 8)  # a noisy take's hiss can sit within 30 dB of the speech
    for _, _, t0, t1 in words:
        keep[max(0, int((t0 - .06) / .01)):min(n, int((t1 + .12) / .01) + 1)] = True
    r = 3  # widen by r frames, then smooth with a 2r+1 kernel: kept frames stay at exactly full level
    wide = _filt(keep.astype(np.float64), np.ones(2 * r + 1)) > 0
    k = np.hanning(2 * r + 3)[1:-1]
    s = np.clip(_filt(wide.astype(np.float64), k / k.sum(), 'edge'), 0, 1)
    g_lo = 10 ** (-depth_db / 20)
    g = g_lo + (1 - g_lo) * s
    gain = np.interp(np.arange(len(y)), np.arange(n) * hop + hop / 2, g)
    out = (y * gain).astype(np.float32)
    after = 10 * np.log10((out[:n * hop].reshape(n, hop).astype(np.float64) ** 2).mean(1) + 1e-12)
    return out, {'floor_db': round(float(floor - speech), 1),
                 'floor_after_db': round(float(np.percentile(after[live], 10) - speech), 1),
                 'seconds_lowered': round(float((s < .5).sum() * .01), 2)}


def _periodic(frames, sr):
    """True for frames with a clear pitch (70-400 Hz): vowels and voiced consonants."""
    f = frames - frames.mean(1, keepdims=True)
    ac = np.fft.irfft(np.abs(np.fft.rfft(f, 2 * f.shape[1], axis=1)) ** 2, axis=1)
    ac = ac / (ac[:, :1] + 1e-12)
    lo, hi = sr // 400, min(sr // 70, f.shape[1] - 1)
    return ac[:, lo:hi].max(1) > .45 if hi > lo else np.zeros(len(f), bool)


def trim_bounds(x, sr, words):
    """Keep quiet consonant/word tails as well as alignment uncertainty margins."""
    on = np.flatnonzero(np.abs(x) > 10 ** (-55 / 20))
    if not len(on):
        return 0.0, len(x) / sr
    head = max(0, on[0] / sr - .06)
    tail = min(len(x) / sr, on[-1] / sr + .16)
    if words:
        head = min(head, max(0, words[0][2] - .06))
        tail = max(tail, min(len(x) / sr, words[-1][3] + .14))
    return head, tail


def soften_quiet_edges(x, sr):
    """Remove clicks at quiet edit edges; never fade an audible consonant away."""
    out = x.copy()
    n = min(int(.004 * sr), len(x) // 2)
    if n and np.max(np.abs(x[:n])) < 10 ** (-40 / 20):
        out[:n] *= np.linspace(0, 1, n)
    if n and np.max(np.abs(x[-n:])) < 10 ** (-40 / 20):
        out[-n:] *= np.linspace(1, 0, n)
    return out
