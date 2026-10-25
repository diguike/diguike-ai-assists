"""Narration text normalisation and polyphone checking for edge-tts.

edge-tts takes plain text only (no SSML <phoneme>), so pronunciation is fixed by
rewriting the TTS text: the digit rules below, plus a lexicon of homophone swaps
(global LEXICON here, per-episode META['pron']).

The polyphone check finds out which reading the voice actually used. The voice
renders identical phonemes as near-identical audio, so for each polyphonic
character we re-synthesise the line with the character swapped for an
unambiguous homophone of each candidate reading and see which variant sounds
closest around that character (DTW over log-mel frames).
"""
import re
from functools import lru_cache

import numpy as np

# ---------------------------------------------------------------- normalisation

# word -> spoken form, applied to every narration line before TTS.
# Add an entry whenever the voice is caught using a non-standard reading.
LEXICON = {
    '成分股': '成份股',  # chéngfèn; YunxiNeural says chéngfēn
    '成分': '成份',
}

MEASURE = '个只年元块天位种次家倍条张份项名件手周岁层万千亿成'
DIGITS = '零一二三四五六七八九'


def _code_digits(m):
    return ''.join(DIGITS[int(c)] for c in m.group(0))


def normalize(text, lexicon=None):
    t = text
    for k, v in {**LEXICON, **(lexicon or {})}.items():
        t = t.replace(k, v)
    t = re.sub(r'(?<=[A-Za-z])\+(?=\d)', '加', t)                          # T+0 -> T加0
    t = re.sub(r'(?<![\d.第])2(?=[' + MEASURE + '])', '两', t)              # 2年 -> 两年
    t = re.sub(r'(?<![\d.])\d{6}(?![\d.万亿元份股年%])', _code_digits, t)    # 513100 -> 五一三一零零
    return t


# ---------------------------------------------------------------- polyphones

# polyphones worth checking, with the readings that occur in practice
POLY = {
    '行': 'hang2 xing2', '长': 'chang2 zhang3', '重': 'zhong4 chong2', '只': 'zhi1 zhi3', '处': 'chu3 chu4',
    '差': 'cha1 cha4 chai1', '薄': 'bao2 bo2', '抹': 'mo3 ma1', '扎': 'zha1 za1 zha2', '当': 'dang1 dang4',
    '降': 'jiang4 xiang2', '调': 'diao4 tiao2', '数': 'shu4 shu3', '分': 'fen1 fen4', '还': 'hai2 huan2',
    '便': 'bian4 pian2', '空': 'kong1 kong4', '量': 'liang4 liang2', '种': 'zhong3 zhong4', '为': 'wei2 wei4',
    '应': 'ying1 ying4', '相': 'xiang1 xiang4', '少': 'shao3 shao4', '好': 'hao3 hao4', '发': 'fa1 fa4',
    '曾': 'ceng2 zeng1', '藏': 'cang2 zang4', '强': 'qiang2 qiang3', '背': 'bei4 bei1', '倒': 'dao3 dao4',
    '率': 'lv4 shuai4', '冲': 'chong1 chong4', '称': 'cheng1 chen4', '供': 'gong1 gong4', '中': 'zhong1 zhong4',
    '正': 'zheng4 zheng1', '盛': 'sheng4 cheng2', '系': 'xi4 ji4', '给': 'gei3 ji3', '会': 'hui4 kuai4',
    '角': 'jiao3 jue2', '结': 'jie2 jie1', '散': 'san4 san3', '落': 'luo4 la4 lao4', '看': 'kan4 kan1',
    '载': 'zai4 zai3', '卡': 'ka3 qia3', '朝': 'chao2 zhao1', '乘': 'cheng2 sheng4', '识': 'shi2 zhi4',
    '似': 'si4 shi4', '露': 'lu4 lou4', '模': 'mo2 mu2', '参': 'can1 shen1', '传': 'chuan2 zhuan4',
    '转': 'zhuan3 zhuan4', '几': 'ji3 ji1', '尽': 'jin3 jin4', '间': 'jian1 jian4', '解': 'jie3 xie4',
    '省': 'sheng3 xing3', '占': 'zhan4 zhan1', '涨': 'zhang3 zhang4', '创': 'chuang4 chuang1', '华': 'hua2 hua4',
    '弹': 'tan2 dan4', '场': 'chang3 chang2', '单': 'dan1 shan4', '券': 'quan4 xuan4', '折': 'zhe2 she2 zhe1',
    '都': 'dou1 du1', '要': 'yao4 yao1', '没': 'mei2 mo4', '宁': 'ning4 ning2', '担': 'dan1 dan4',
    '压': 'ya1 ya4', '挑': 'tiao1 tiao3', '横': 'heng2 heng4', '得': 'de2 dei3', '着': 'zhao2 zhuo2',
    '大': 'da4 dai4', '奇': 'qi2 ji1', '曲': 'qu1 qu3', '干': 'gan1 gan4', '更': 'geng4 geng1',
    '教': 'jiao4 jiao1', '觉': 'jue2 jiao4', '假': 'jia3 jia4', '乐': 'le4 yue4', '难': 'nan2 nan4',
    '兴': 'xing1 xing4', '与': 'yu3 yu4', '号': 'hao4 hao2', '别': 'bie2 bie4', '暴': 'bao4 pu4',
    '舍': 'she3 she4', '扫': 'sao3 sao4', '据': 'ju4 ju1', '提': 'ti2 di1', '劲': 'jin4 jing4',
    '冠': 'guan4 guan1', '禁': 'jin4 jin1', '累': 'lei3 lei4', '将': 'jiang1 jiang4', '铺': 'pu1 pu4',
    '查': 'cha2 zha1', '血': 'xue4 xie3', '削': 'xue1 xiao1', '恶': 'e4 wu4', '答': 'da2 da1',
    '混': 'hun4 hun2', '屏': 'ping2 bing3', '盖': 'gai4 ge3', '合': 'he2 ge3', '和': 'he2 he4 huo4',
    '厦': 'sha4 xia4', '叶': 'ye4 xie2', '期': 'qi1 ji1', '估': 'gu1 gu4', '尾': 'wei3 yi3',
}

# words pypinyin gets wrong; expected tone3 reading per character ('_' = skip)
EXPECT = {
    '摊薄': 'tan1 bo2', '处在': 'chu3 zai4', '处于': 'chu3 yu2', '时差': 'shi2 cha1', '当天': 'dang1 tian1',
    '供给': 'gong1 ji3', '单日': 'dan1 ri4', '倒是': 'dao4 _', '为例': 'wei2 _', '两行': '_ hang2',
    '一行': '_ hang2', '这一行': '_ _ hang2', '成份': 'cheng2 fen4', '弹出': 'tan2 _',
    '重算': 'chong2 _', '重做': 'chong2 _', '重新': 'chong2 _', '重来': 'chong2 _', '出处': '_ chu4',
    '越长': '_ chang2', '很长': '_ chang2', '更长': '_ chang2', '多长': '_ chang2',
    # 差 as「difference」is chā; pypinyin gives chà after most characters
    '速差': '_ cha1', '期差': '_ cha1', '落差': '_ cha1', '偏差': '_ cha1', '误差': '_ cha1', '反差': '_ cha1',
    '温差': '_ cha1', '价差': '_ cha1', '差距': 'cha1 _', '差异': 'cha1 _', '差别': 'cha1 _', '差额': 'cha1 _',
    '参与': 'can1 yu4', '参加': 'can1 jia1', '参考': 'can1 kao3',
    # Repaying money: a correct huán must not be flagged as the adverb hái.
    # Keep the context narrow; 还会 / 还没 / 还不去 remain hái.
    '欠钱不还': '_ _ _ huan2', '还不上钱': 'huan2 _ _ _',
    '少付或不还': '_ _ _ _ huan2',
}
# measure word 只 (zhī) after numerals / 多 / 每 / 这 / 那 ...
MEASURE_ZHI = re.compile(r'(?<=[0-9一二两三四五六七八九十几多每这那哪])只(?![有是能要需会在])')


FUNCTION_CHARS = set('之的了着么吗呢吧啊呀哦嘛啦而且或及与其所以于乎矣焉哉也')


@lru_cache(None)
def _homophones():
    """tone3 reading -> most frequent character whose default reading it is.

    Polyphones from POLY are excluded; rare archaic alternates are tolerated
    (份 also has an obscure bīn but the voice reads it fèn).
    """
    import jieba
    from pypinyin import pinyin, Style
    jieba.setLogLevel(60)
    jieba.initialize()
    best = {}
    for w, f in jieba.dt.FREQ.items():
        # rare chars may be outside the voice's lexicon; function words carry odd prosody
        if len(w) != 1 or f < 80 or not ('\u4e00' <= w <= '\u9fff') or w in POLY or w in FUNCTION_CHARS:
            continue
        rd = pinyin(w, style=Style.TONE3, neutral_tone_with_five=True)[0][0]
        if rd not in best or f > best[rd][1]:
            best[rd] = (w, f)
    return {k: v[0] for k, v in best.items()}


def expected(text):
    """Per-character expected tone3 reading (None for non-Han)."""
    from pypinyin import pinyin, Style
    out = [None] * len(text)
    for m in re.finditer(r'[一-鿿]+', text):
        rd = pinyin(m.group(0), style=Style.TONE3, neutral_tone_with_five=True)
        for i, r in enumerate(rd):
            out[m.start() + i] = r[0]
    for w, r in EXPECT.items():
        for m in re.finditer(re.escape(w), text):
            for i, x in enumerate(r.split()):
                if x != '_':
                    out[m.start() + i] = x
    for m in MEASURE_ZHI.finditer(text):
        out[m.start()] = 'zhi1'
    return out


def variants(text, i, exp):
    """{reading: text with char i swapped for a homophone of that reading}."""
    hom = _homophones()
    cands = POLY[text[i]].split()
    if exp not in cands:
        cands = [exp] + cands
    return {r: text[:i] + hom[r] + text[i + 1:] for r in cands if r in hom}


def poly_units(text, words, skip=''):
    """Polyphones of a narration paragraph, each with the short unit to test it in.

    words: the voice's own word segmentation of `text` as [(char_start, char_end, ...)],
    taken from the TTS word boundaries. The unit is the voice's word holding the
    char (plus neighbours when that word is the single char), so the reading the
    voice chose in context ("100只|有" vs "只有") is what gets tested. Synthesised
    on its own, the unit and its homophone variants keep the same shape, so the
    variant with the voice's reading usually comes out acoustically identical.
    Returns [(pos_in_text, unit, pos_in_unit, expected, {reading: variant})].
    """
    exp = expected(text)
    tok = re.compile(r'^[\u4e00-\u9fff0-9.%]+$')
    han = re.compile(r'^[\u4e00-\u9fff]+$')
    out = []
    for wi, (a, b, *_) in enumerate(words):
        for i in range(a, b):
            ch = text[i]
            if ch not in POLY or ch in skip or exp[i] is None:
                continue
            ua, ub = a, b
            if b - a == 1:  # a lone char needs its neighbours to keep the reading (很多只基金)
                if wi > 0 and tok.match(text[words[wi - 1][0]:words[wi - 1][1]]):
                    ua = words[wi - 1][0]
                if wi + 1 < len(words) and han.match(text[words[wi + 1][0]:words[wi + 1][1]]):
                    ub = words[wi + 1][1]
            unit = text[ua:ub]
            if not tok.match(unit):
                continue
            vs = variants(unit, i - ua, exp[i])
            if exp[i] in vs and len(vs) >= 2:
                out.append((i, unit, i - ua, exp[i], vs))
    return out


def seg_glitches(text, words):
    """Voice words that straddle two dictionary words, e.g. 博|时标|普 for 博时·标普.

    These groupings are where the voice sounds machine-like (odd stress and
    rhythm) even when every syllable is right. A voice word is flagged when a
    jieba boundary falls strictly inside it and one of its own ends cuts into a
    jieba word. Returns [(char_start, char_end)].
    """
    import jieba
    jieba.setLogLevel(60)
    bounds, inside = set(), set()
    for w, a, b in jieba.tokenize(text):
        bounds.update((a, b))
        inside.update(range(a + 1, b))
    tok = re.compile(r'^[\u4e00-\u9fff0-9]+$')
    out = []
    for a, b, *_ in words:
        w = text[a:b]
        if len(w) < 2 or not tok.match(w) or not re.search(r'[\u4e00-\u9fff]', w):
            continue
        m = re.match(r'^[0-9]+([\u4e00-\u9fff])$', w)
        if m and m.group(1) not in POLY:  # 116块|钱, 3点|前: number + measure word is fine
            continue
        if any(k in bounds for k in range(a + 1, b)) and (a in inside or b in inside):
            out.append((a, b))
    return out


# ---------------------------------------------------------------- audio compare

@lru_cache(None)
def _mel_fb(sr, n_fft, n_mels=40, fmin=60, fmax=8000):
    def hz2mel(f):
        return 2595 * np.log10(1 + f / 700)
    mels = np.linspace(hz2mel(fmin), hz2mel(fmax), n_mels + 2)
    hz = 700 * (10 ** (mels / 2595) - 1)
    bins = np.floor((n_fft + 1) * hz / sr).astype(int)
    fb = np.zeros((n_mels, n_fft // 2 + 1))
    for m in range(1, n_mels + 1):
        a, b, c = bins[m - 1], bins[m], bins[m + 1]
        for k in range(a, b):
            fb[m - 1, k] = (k - a) / max(1, b - a)
        for k in range(b, c):
            fb[m - 1, k] = (c - k) / max(1, c - b)
    return fb


def logmel(x, sr):
    n_fft, hop = 1024 if sr > 32000 else 512, sr // 100
    x = np.asarray(x, dtype=np.float64)
    if len(x) < n_fft:
        x = np.pad(x, (0, n_fft - len(x)))
    n = 1 + (len(x) - n_fft) // hop
    frames = np.stack([x[i * hop:i * hop + n_fft] for i in range(n)]) * np.hanning(n_fft)
    spec = np.abs(np.fft.rfft(frames, axis=1)) ** 2
    with np.errstate(all='ignore'):  # Accelerate BLAS raises spurious FP flags
        mel = spec @ _mel_fb(sr, n_fft).T
    return np.log10(np.maximum(mel, 1e-10))


def dtw(a, b):
    d = np.sqrt(((a[:, None, :] - b[None, :, :]) ** 2).sum(-1))
    n, m = d.shape
    acc = np.full((n + 1, m + 1), np.inf)
    acc[0, 0] = 0
    for i in range(1, n + 1):
        for j in range(1, m + 1):
            acc[i, j] = d[i - 1, j - 1] + min(acc[i - 1, j], acc[i, j - 1], acc[i - 1, j - 1])
    return acc[n, m] / (n + m)


def trim(x, sr, db=-42):
    idx = np.nonzero(np.abs(x) > 10 ** (db / 20))[0]
    return x[idx[0]:idx[-1] + 1] if len(idx) else x


def judge_units(orig, variants_audio, sr):
    """Whole-utterance comparison of a short unit and its variants -> (best, margin, dists)."""
    ref = logmel(trim(orig, sr), sr)
    lo = ref.max() - 6
    ref = np.maximum(ref, lo)
    dists = {r: dtw(ref, np.maximum(logmel(trim(x, sr), sr), lo)) for r, x in variants_audio.items()}
    order = sorted(dists, key=dists.get)
    margin = (dists[order[1]] - dists[order[0]]) / max(dists[order[0]], 0.05)
    return order[0], margin, dists


# ---------------------------------------------------------------- ASR read-back (sampling voices)

def _tokens(s):
    """Toneless pinyin per Han char, one token per latin/digit run: [(token, start, end)]."""
    from pypinyin import lazy_pinyin
    out = []
    for m in re.finditer(r'[一-鿿]+|[A-Za-z]+|\d+', s):
        w = m.group(0)
        if re.match(r'[一-鿿]', w):
            for k, py in enumerate(lazy_pinyin(w)):
                out.append((py, m.start() + k, m.start() + k + 1))
        else:
            out.append((w.lower(), m.start(), m.end()))
    return out


def readback_diff(ref, hyp):
    """Where an ASR transcript departs from the script, both in spoken form.

    Compared as toneless pinyin so the recogniser's homophone choices (联接/连接)
    don't count; what remains is words dropped, added or said differently.
    Returns (error_rate, [(ref_start, ref_end, hyp_text)]) with offsets into ref.
    """
    import difflib
    rt, ht = _tokens(ref), _tokens(hyp)
    sm = difflib.SequenceMatcher(None, [t[0] for t in rt], [t[0] for t in ht], autojunk=False)
    diffs, errs = [], 0
    for tag, a, b, c, d in sm.get_opcodes():
        if tag == 'equal':
            continue
        errs += max(b - a, d - c)
        ra = rt[a][1] if a < len(rt) else len(ref)
        rb = rt[b - 1][2] if b > a else ra
        h = hyp[ht[c][1]:ht[d - 1][2]] if d > c else ''
        diffs.append((ra, rb, h))
    return errs / max(1, len(rt)), diffs
