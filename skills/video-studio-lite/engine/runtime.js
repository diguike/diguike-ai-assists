// Frame runtime. build.py calls window.__frame(state) once per unique frame:
// state = {cur, prev, alpha, p: {element id: progress 0..1}, sub, tr, cam, pcam}.
// Everything is a pure function of the state, so frames can render in any order.
const EL = {};
const MO = window.__MOTION || {};
const ROOT = getComputedStyle(document.documentElement);
const W = parseFloat(ROOT.getPropertyValue('--W')), H = parseFloat(ROOT.getPropertyValue('--H'));
function wrapChars(el){
  const spans = [];
  const walk = node => {
    for (const c of Array.from(node.childNodes)) {
      if (c.nodeType === 3) {
        const f = document.createDocumentFragment();
        for (const ch of Array.from(c.textContent)) {
          const s = document.createElement('span'); s.className = 'ch'; s.textContent = ch; f.appendChild(s); spans.push(s);
        }
        node.replaceChild(f, c);
      } else if (c.nodeType === 1 && c.tagName !== 'BR') walk(c);
    }
  };
  walk(el); return spans;
}
// numbers inside an element, so 'count' can roll them up from zero
const NUM = /\d[\d,]*(?:\.\d+)?/g;
function numbers(el){
  const out = [], roots = el.querySelectorAll('.num').length ? el.querySelectorAll('.num') : [el];
  const walk = node => {
    for (const c of Array.from(node.childNodes)) {
      if (c.nodeType === 3 && NUM.test(c.textContent)) out.push({node: c, text: c.textContent});
      else if (c.nodeType === 1) walk(c);
      NUM.lastIndex = 0;
    }
  };
  roots.forEach(walk); return out;
}
function rollTo(t, k){
  return t.replace(NUM, m => {
    const dec = (m.split('.')[1] || '').length, v = parseFloat(m.replace(/,/g, '')) * k;
    let s = v.toFixed(dec);
    if (m.includes(',')) { const [i, d] = s.split('.'); s = i.replace(/\B(?=(\d{3})+(?!\d))/g, ',') + (d ? '.' + d : ''); }
    return s;
  });
}
// the dash pattern laid along the first `upto` px of a path, then one gap over the rest
function dashTo(pat, upto, len){
  const out = [];
  for (let at = 0, i = 0; at < upto; i++) {
    const seg = Math.min(pat[i % pat.length], upto - at);
    out.push(i % 2 ? seg : seg.toFixed(2));
    at += pat[i % pat.length];
  }
  if (out.length % 2) out.push(len + 1);        // ends in a dash: hide the rest
  else if (out.length) out[out.length - 1] = len + 1;  // ends in a gap: stretch it
  else out.push(0, len + 1);
  return out.join(' ');
}
function prep(){
  document.querySelectorAll('[data-a]').forEach(el => {
    const r = {el, a: el.dataset.a, svg: el instanceof SVGElement};
    if (r.a === 'type') r.spans = wrapChars(el);
    if (r.a === 'draw') {
      r.len = el.getTotalLength();
      // a dashed line keeps its dashes while it draws (the plain trick would turn it solid)
      const pat = (el.getAttribute('stroke-dasharray') || '').split(/[\s,]+/).map(Number).filter(v => v > 0);
      if (pat.length) { r.dash = pat.length % 2 ? pat.concat(pat) : pat; r.dashRaw = el.getAttribute('stroke-dasharray'); }
      else el.style.strokeDasharray = r.len + ' ' + r.len;
    }
    if (r.a === 'count') r.nums = numbers(el);
    if (['words', 'letters', 'lines', 'pops'].includes(r.a)) r.kids = Array.from(el.querySelectorAll(':scope .kp'));
    EL[el.id] = r;
  });
}
// easing curves; the theme's motion preset picks one for fades, draws, wipes and masks
const EASE = {
  linear: p => p,
  sineOut: p => Math.sin(p * Math.PI / 2),
  quadOut: p => 1 - (1 - p) * (1 - p),
  cubicOut: p => 1 - Math.pow(1 - p, 3),
  quartOut: p => 1 - Math.pow(1 - p, 4),
  quintOut: p => 1 - Math.pow(1 - p, 5),
  expoOut: p => p >= 1 ? 1 : (1 - Math.pow(2, -10 * p)) / (1 - Math.pow(2, -10)),
  backOut: p => { const c1 = 1.70158, c3 = c1 + 1; return 1 + c3 * Math.pow(p - 1, 3) + c1 * Math.pow(p - 1, 2); },
  sineInOut: p => -(Math.cos(Math.PI * p) - 1) / 2,
  cubicInOut: p => p < 0.5 ? 4 * p * p * p : 1 - Math.pow(-2 * p + 2, 3) / 2,
  quartInOut: p => p < 0.5 ? 8 * p * p * p * p : 1 - Math.pow(-2 * p + 2, 4) / 2,
  cubicIn: p => p * p * p,
  expoInOut: p => p <= 0 ? 0 : p >= 1 ? 1 : p < 0.5 ? Math.pow(2, 20 * p - 10) / 2 : (2 - Math.pow(2, -20 * p + 10)) / 2,
};
const ease = EASE[MO.ease] || EASE.cubicOut;
const back = EASE.backOut;
const cap = p => Math.min(1, ease(p));  // for moves that must not overshoot (strokes, clips)
// damped spring from 0 to 1 over p in 0..1: overshoots a little, settled by p = 1
function spring(p, z = 0.52, w = 13){
  if (p >= 1) return 1;
  const wd = w * Math.sqrt(1 - z * z);
  return 1 - Math.exp(-z * w * p) * (Math.cos(wd * p) + (z * w / wd) * Math.sin(wd * p));
}
function apply(r, p){
  const s = r.el.style;
  switch (r.a) {
    case 'type': {
      const n = r.spans.length, k = p >= 1 ? n : Math.round(p * n);
      r.spans.forEach((sp, i) => { sp.style.visibility = i < k ? 'visible' : 'hidden'; sp.classList.toggle('cur', p > 0 && p < 1 && i === k - 1); });
      break;
    }
    case 'fade': s.opacity = ease(p); if (!r.svg) s.transform = `translateY(${((1 - ease(p)) * 16).toFixed(2)}px)`; break;
    case 'pop': s.opacity = Math.min(1, p * 2.5); if (!r.svg) s.transform = `scale(${(0.55 + 0.45 * back(p)).toFixed(4)})`; break;
    case 'draw':
      if (r.dash) s.strokeDasharray = cap(p) >= 1 ? r.dashRaw : dashTo(r.dash, r.len * cap(p), r.len);
      else s.strokeDashoffset = r.len * (1 - cap(p));
      s.opacity = p > 0 ? 1 : 0; break;
    case 'growY': s.transform = `scaleY(${ease(p).toFixed(4)})`; s.opacity = p > 0 ? 1 : 0; break;
    case 'growX': s.transform = `scaleX(${ease(p).toFixed(4)})`; s.opacity = p > 0 ? 1 : 0; break;
    case 'wipe': s.clipPath = `inset(-4px ${((1 - cap(p)) * 100).toFixed(2)}% -4px -4px)`; s.opacity = p > 0 ? 1 : 0; break;
    // springs up a few pixels and settles
    case 'rise': {
      const k = spring(p);
      s.opacity = Math.min(1, p * 3);
      if (!r.svg) s.transform = `translateY(${((1 - k) * 42).toFixed(2)}px) scale(${(0.97 + 0.03 * k).toFixed(4)})`;
      break;
    }
    // rises from behind its own bottom edge
    case 'mask': {
      const k = 1 - cap(p);
      s.opacity = p > 0 ? 1 : 0;
      if (!r.svg) { s.transform = `translateY(${(k * 100).toFixed(2)}%)`; s.clipPath = `inset(-40% -8% calc(${(k * 100).toFixed(2)}% - 8px) -8%)`; }
      break;
    }
    // stamped down from 1.5x
    case 'zoom': {
      s.opacity = Math.min(1, p * 4);
      if (!r.svg) s.transform = `scale(${(1 + 0.5 * (1 - spring(p, 0.45, 10))).toFixed(4)})`;
      break;
    }
    // out of focus into focus
    case 'blur': {
      const e = cap(p);
      s.opacity = e;
      if (!r.svg) { s.filter = p >= 1 ? '' : `blur(${((1 - e) * 14).toFixed(2)}px)`; s.transform = `translateY(${((1 - e) * 10).toFixed(2)}px)`; }
      break;
    }
    case 'slide': s.opacity = Math.min(1, p * 2.5); if (!r.svg) s.transform = `translateX(${((1 - ease(p)) * -60).toFixed(2)}px)`; break;
    // settles into place: a slow fade with a short rise and a little focus pull, no bounce
    case 'soft': {
      const e = EASE.cubicInOut(Math.min(1, p)), f = EASE.quartOut(Math.min(1, p));
      s.opacity = e;
      if (!r.svg) { s.transform = `translateY(${((1 - f) * 22).toFixed(2)}px)`; s.filter = p >= 1 ? '' : `blur(${((1 - f) * 8).toFixed(2)}px)`; }
      break;
    }
    // numbers roll up from zero
    case 'count': {
      s.opacity = Math.min(1, p * 4);
      const k = p >= 1 ? 1 : EASE.quartOut(p);
      r.nums.forEach(n => { n.node.textContent = p >= 1 ? n.text : rollTo(n.text, k); });
      break;
    }
    // highlighter / strike-through sweeping across inline text
    case 'marker': s.backgroundSize = `${(cap(p) * 100).toFixed(2)}% 100%`; break;
    case 'cut': s.opacity = p > 0 ? 1 : 0; break;
    // kinetic text: each word / letter / line of a kinetic() element enters on its own, staggered
    case 'words': case 'letters': case 'lines': case 'pops': {
      s.opacity = p > 0 ? 1 : 0;
      const sf = +r.el.dataset.sf, df = +r.el.dataset.df;
      r.kids.forEach((k, i) => {
        const q = Math.min(1, Math.max(0, (p - i * sf) / df)), ks = k.style;
        if (r.a === 'words') {
          const v = spring(q); ks.opacity = Math.min(1, q * 3);
          ks.transform = `translateY(${((1 - v) * 0.55).toFixed(3)}em) scale(${(0.92 + 0.08 * v).toFixed(4)})`;
        } else if (r.a === 'letters') {  // drops in; speed flattens it, the spring restores it
          const v = spring(q, 0.48, 12), dv = (v - spring(Math.max(0, q - 0.02), 0.48, 12)) / 0.02, sq = Math.min(0.25, Math.abs(dv) * 0.018);
          ks.opacity = Math.min(1, q * 4);
          ks.transform = `translateY(${(-(1 - v) * 0.8).toFixed(3)}em) scale(${(1 + sq * 0.6).toFixed(4)},${(1 - sq).toFixed(4)})`;
        } else if (r.a === 'lines') {
          const v = 1 - cap(q); ks.opacity = q > 0 ? 1 : 0;
          ks.transform = `translateY(${(v * 100).toFixed(2)}%)`; ks.clipPath = `inset(-30% -4% calc(${(v * 100).toFixed(2)}% - 6px) -4%)`;
        } else {
          ks.opacity = Math.min(1, q * 2.5); ks.transform = `scale(${(0.5 + 0.5 * back(q)).toFixed(4)})`;
        }
      });
      break;
    }
  }
}

// ---------------------------------------------------------------- cues
// Timed actions on elements after (or instead of) their entrance: emphasis, exits,
// moves, focus, loops, cursor clicks. build.py sends q = {cue index: [seconds since
// the cue started, start time]}; a finished emphasis is left out, a finished
// move/exit/dim is sent with tau = its duration so its end state holds, and the
// start time orders actions that are both finished. Several cues on one element
// compose (translate / scale / rotate / opacity / filter), on top of its entrance.
const CUES = window.__CUES || [];
let cueDirty = [];
function clearCues(){
  for (const e of cueDirty) { const s = e.style; s.translate = ''; s.scale = ''; s.rotate = ''; s.filter = ''; s.opacity = ''; s.transformOrigin = ''; s.transformBox = ''; }
  cueDirty = [];
}
const smooth = u => u * u * (3 - 2 * u);
const CURVE = {smooth: EASE.cubicInOut, snap: EASE.expoOut, soft: EASE.sineInOut, linear: EASE.linear, spring: u => spring(u, 0.55, 11), arc: EASE.sineInOut};
const lerp = (a, b, k) => a + (b - a) * k;
function applyCues(q){
  const pose = new Map(), get = el => {
    let p = pose.get(el);
    if (!p) { p = {tx: 0, ty: 0, sx: 1, sy: 1, rot: 0, op: 1, f: [], moves: []}; pose.set(el, p); }
    return p;
  };
  let focus = [];
  for (const [i, v] of Object.entries(q)) {
    const c = CUES[i], [tau, t0] = Array.isArray(v) ? v : [v, 0];
    if (!c || c.el === '@cam') continue;
    if (c.k === 'focus' || c.k === 'unfocus') { focus.push([tau, c, t0]); continue; }
    const el = document.getElementById(c.el);
    if (!el) continue;
    const P = get(el), a = c.a || {}, u = Math.min(1, Math.max(0, tau / c.d));
    switch (c.k) {
      case 'pulse': { const k = 1 + (a.amp ?? 0.12) * Math.sin(Math.PI * u); P.sx *= k; P.sy *= k; break; }
      case 'punch': { const r = Math.exp(-6 * tau) * Math.sin(24 * tau); P.sx *= 1 + 0.18 * r; P.sy *= 1 - 0.2 * r; break; }
      case 'shake': P.tx += (a.amp ?? 16) * Math.exp(-5 * tau) * Math.sin(2 * Math.PI * 9 * tau); break;
      case 'wiggle': P.rot += (a.amp ?? 7) * Math.exp(-3.5 * u) * Math.sin(2 * Math.PI * 3 * u); break;
      case 'jump': {
        if (u < 0.55) P.ty -= (a.h ?? 46) * Math.sin(Math.PI * u / 0.55);
        else { const r = Math.exp(-5 * (u - 0.55)) * Math.sin(Math.PI * 4 * (u - 0.55)); P.sx *= 1 + 0.12 * r; P.sy *= 1 - 0.14 * r; }
        break;
      }
      case 'glow': { const r = (a.r ?? 26) * (a.hold ? Math.min(1, u * 2.5) : Math.sin(Math.PI * u)); P.f.push(`drop-shadow(0 0 ${r.toFixed(1)}px ${a.color || 'var(--primary)'})`); break; }
      case 'flash': P.f.push(`brightness(${(1 + 0.55 * Math.sin(Math.PI * u)).toFixed(3)})`); break;
      case 'out': {
        const e = smooth(u), st = a.style || 'fade';
        P.op *= 1 - e;
        if (st === 'fade') P.ty -= 12 * e;
        else if (st === 'drop') P.ty += 90 * e * e;
        else if (st === 'shrink') { P.sx *= 1 - 0.35 * e; P.sy *= 1 - 0.35 * e; }
        else if (st === 'blur') { P.f.push(`blur(${(12 * e).toFixed(2)}px)`); P.ty -= 30 * e; P.sx *= 1 + 0.03 * e; P.sy *= 1 + 0.03 * e; }
        else if (st === 'up') P.ty -= 140 * e;
        else if (st === 'left') P.tx -= 180 * e;
        else if (st === 'right') P.tx += 180 * e;
        else if (st === 'zoom') { P.sx *= 1 + 0.4 * e; P.sy *= 1 + 0.4 * e; }
        else if (st === 'cut') P.op = tau > 0 ? 0 : P.op;
        break;
      }
      case 'move': P.moves.push([tau, c, t0]); break;
      case 'loop': {
        const w = 2 * Math.PI * tau / (a.period ?? 3);
        if (a.kind === 'spin') P.rot += 360 * tau / (a.period ?? 3);
        else if (a.kind === 'breathe') { const k = 1 + (a.amp ?? 0.03) * Math.sin(w); P.sx *= k; P.sy *= k; }
        else P.ty += (a.amp ?? 10) * Math.sin(w);
        break;
      }
      case 'click': {
        if (tau < 0.14) { P.sx *= 0.86; P.sy *= 0.86; }
        const rip = el.querySelector('.rip');
        if (rip) { const R = get(rip), k = Math.min(1, tau / 0.5); R.sx = R.sy = 0.2 + 2.4 * EASE.cubicOut(k); R.op = 0.9 * (1 - k); R.show = true; }
        break;
      }
    }
  }
  // moves: each starts from wherever the previous one on that element had got to
  for (const P of pose.values()) {
    if (!P.moves.length) continue;
    P.moves.sort((x, y) => x[2] - y[2]);
    let cur = {dx: 0, dy: 0, s: 1, rot: 0, op: 1}, lift = 0;
    for (const [tau, c] of P.moves) {
      const a = c.a, e = (CURVE[a.curve] || CURVE.smooth)(Math.min(1, tau / c.d));
      const to = {dx: a.dx ?? cur.dx, dy: a.dy ?? cur.dy, s: a.s ?? cur.s, rot: a.rot ?? cur.rot, op: a.op ?? cur.op};
      lift = a.curve === 'arc' && tau < c.d ? (a.h ?? 120) * Math.sin(Math.PI * e) : 0;
      for (const k in cur) cur[k] = lerp(cur[k], to[k], e);
    }
    P.tx += cur.dx; P.ty += cur.dy - lift; P.sx *= cur.s; P.sy *= cur.s; P.rot += cur.rot; P.op *= cur.op;
  }
  // focus: everything else on the slide steps back; unfocus brings it back
  if (focus.length) {
    focus.sort((x, y) => y[2] - x[2]);  // the one that started last decides
    const [tau, c] = focus[0], f = focus.find(x => x[1].k === 'focus');
    if (f) {
      const keep = f[1].a.keep.map(id => document.getElementById(id)).filter(Boolean);
      const sl = keep.length && keep[0].closest('.slide');
      const k = EASE.cubicInOut(Math.min(1, tau / c.d)), dimTo = f[1].a.op ?? 0.22;
      const level = c.k === 'focus' ? lerp(1, dimTo, k) : lerp(dimTo, 1, k);
      if (sl) sl.querySelectorAll('[data-a]').forEach(el => {
        if (keep.some(x => x === el || x.contains(el) || el.contains(x)) || el.closest('.cursor')) return;
        get(el).op *= level;
      });
    }
  }
  for (const [el, P] of pose) {
    const s = el.style, svg = el instanceof SVGElement;
    if (P.tx || P.ty) s.translate = `${P.tx.toFixed(2)}px ${P.ty.toFixed(2)}px`;
    if (P.sx !== 1 || P.sy !== 1) s.scale = `${P.sx.toFixed(4)} ${P.sy.toFixed(4)}`;
    if (P.rot) s.rotate = `${P.rot.toFixed(3)}deg`;
    if (P.op !== 1 || P.show) s.opacity = ((s.opacity === '' ? 1 : +s.opacity) * P.op).toFixed(4);
    if (P.f.length) s.filter = P.f.join(' ');
    if (svg) { s.transformBox = 'fill-box'; s.transformOrigin = '50% 50%'; }
    cueDirty.push(el);
  }
}

// ---------------------------------------------------------------- slide transitions + camera
const SL = Array.from(document.querySelectorAll('.slide'));
let shown = [], dirty = [];
const touch = (...els) => { dirty.push(...els); };
function clearDirty(){
  for (const e of dirty) { const s = e.style; s.transform = ''; s.translate = ''; s.scale = ''; s.opacity = ''; s.clipPath = ''; s.background = ''; s.zIndex = ''; s.transformOrigin = ''; }
  dirty = [];
}
function camera(sec, c){
  const w = sec.querySelector(':scope > .cam');
  if (!w) return;
  w.style.transform = c ? `translate(${(W / 2 - c[0] * c[2]).toFixed(2)}px,${(H / 2 - c[1] * c[2]).toFixed(2)}px) scale(${c[2].toFixed(4)})` : '';
}
function fadeExcept(node, keep, alpha){
  for (const ch of node.children) {
    if (keep.has(ch)) continue;
    if ([...keep].some(k => ch.contains(k))) { fadeExcept(ch, keep, alpha); continue; }
    ch.style.opacity = alpha * (ch.style.opacity === '' ? 1 : +ch.style.opacity); touch(ch);
  }
}
// Keynote's magic move: an element on the old slide flies and scales into its
// counterpart on the new one while the rest of the old slide fades away.
function magic(tr, p, pe, c){
  const e = EASE.cubicInOut(p);
  const bg = getComputedStyle(pe).backgroundColor.match(/[\d.]+/g) || [255, 255, 255];
  c.style.opacity = 1;
  pe.style.zIndex = 3;
  pe.style.background = `rgba(${bg[0]},${bg[1]},${bg[2]},${(1 - e).toFixed(4)})`;
  touch(pe, c);
  const pairs = (tr.c || []).map(([a, b]) => [document.getElementById(a), document.getElementById(b)]).filter(([a, b]) => a && b);
  const rects = pairs.map(([a, b]) => [a.getBoundingClientRect(), b.getBoundingClientRect()]);
  fadeExcept(pe, new Set(pairs.map(x => x[0])), 1 - e);
  pairs.forEach(([a, b], i) => {
    const [ra, rb] = rects[i];
    if (!ra.width || !rb.width) return;
    const dx = (ra.left + ra.width / 2) - (rb.left + rb.width / 2), dy = (ra.top + ra.height / 2) - (rb.top + rb.height / 2);
    const sx = ra.width / rb.width, sy = ra.height / rb.height;
    b.style.translate = `${(dx * (1 - e)).toFixed(2)}px ${(dy * (1 - e)).toFixed(2)}px`;
    b.style.scale = `${(sx + (1 - sx) * e).toFixed(4)} ${(sy + (1 - sy) * e).toFixed(4)}`;
    b.style.opacity = Math.min(1, e * 2);
    a.style.translate = `${(-dx * e).toFixed(2)}px ${(-dy * e).toFixed(2)}px`;
    a.style.scale = `${(1 + (1 / sx - 1) * e).toFixed(4)} ${(1 + (1 / sy - 1) * e).toFixed(4)}`;
    a.style.opacity = 1 - e;
    touch(a, b);
  });
}
function transition(tr, p, pe, c){
  const e = EASE.cubicInOut(p);
  switch (tr.k) {
    case 'push': c.style.opacity = 1; pe.style.transform = `translateX(${(-e * W).toFixed(2)}px)`; c.style.transform = `translateX(${((1 - e) * W).toFixed(2)}px)`; break;
    case 'up': c.style.opacity = 1; pe.style.transform = `translateY(${(-e * H).toFixed(2)}px)`; c.style.transform = `translateY(${((1 - e) * H).toFixed(2)}px)`; break;
    case 'zoom': {
      pe.style.transform = `scale(${(1 + 0.12 * e).toFixed(4)})`; c.style.opacity = EASE.quadOut(p); c.style.transform = `scale(${(0.94 + 0.06 * EASE.cubicOut(p)).toFixed(4)})`;
      const wm = pe.querySelector(':scope > .wm');  // one watermark, not two drifting apart
      if (wm) { wm.style.opacity = 0; touch(wm); }
      break;
    }
    case 'wipe': c.style.opacity = 1; c.style.clipPath = `inset(0 ${((1 - e) * 100).toFixed(2)}% 0 0)`; break;
    case 'iris': {
      const [x, y] = tr.o || [W / 2, H / 2];
      const R = Math.hypot(Math.max(x, W - x), Math.max(y, H - y));
      c.style.opacity = 1; c.style.clipPath = `circle(${(Math.pow(p, 1.6) * R).toFixed(1)}px at ${x}px ${y}px)`;
      break;
    }
    case 'magic': return magic(tr, p, pe, c);
    // the camera pushes into an element of the old slide until it fills the frame; the new slide is inside it
    case 'through': {
      const el = typeof tr.o === 'string' && document.getElementById(tr.o);
      if (!el) { c.style.opacity = p; break; }
      const r = el.getBoundingClientRect(), cx = r.left + r.width / 2, cy = r.top + r.height / 2;
      const k = EASE.cubicIn(Math.min(1, p / 0.8)), sc = Math.exp(Math.log(Math.max(W / r.width, H / r.height) * 1.15) * k);
      const px = lerp(cx, W / 2, k), py = lerp(cy, H / 2, k);
      pe.style.transformOrigin = '0 0';
      pe.style.transform = `translate(${(px - sc * cx).toFixed(2)}px,${(py - sc * cy).toFixed(2)}px) scale(${sc.toFixed(4)})`;
      c.style.opacity = smooth(Math.min(1, Math.max(0, (p - 0.55) / 0.45)));
      break;
    }
    default: return;
  }
  touch(pe, c);
}
// ---------------------------------------------------------------- scenes: continuous motion
// A slide can carry a scene (Slide.animate): a function of time that runs on every frame of the
// slide, after entrances and cues. It moves, morphs and draws whatever it likes (SVG, HTML, a
// canvas), always from the time it is given and never from the previous frame, so frames can
// still render in any order. build.py sends sc = {t: seconds since the slide began, d: slide
// length, bt: [beat starts], bk: {key: beat start}}; a still is t = 1e4 (everything finished).
const SCENES = window.__SCENES || {};
const SCENE_STATE = {};
const clamp = (v, a = 0, b = 1) => Math.min(b, Math.max(a, v));
// hash noise: the same (i, j) always gives the same number in [0, 1)
function hash(i, j = 0){
  let h = (Math.imul(i | 0, 374761393) + Math.imul(j | 0, 668265263)) | 0;
  h = Math.imul(h ^ (h >>> 13), 1274126177);
  return ((h ^ (h >>> 16)) >>> 0) / 4294967296;
}
// smooth value noise in [-1, 1]: drifting that never repeats exactly
function noise1(x, seed = 0){
  const i = Math.floor(x), f = x - i, u = f * f * (3 - 2 * f);
  return lerp(hash(i, seed), hash(i + 1, seed), u) * 2 - 1;
}
const NUMS = /-?\d*\.?\d+(?:e[-+]?\d+)?/gi;
// two path strings with the same commands, point for point: the shape between them
function lerpPath(a, b, k){
  const nb = b.match(NUMS) || [];
  let i = 0;
  return a.replace(NUMS, m => { const v = +m, w = nb[i++]; return w === undefined ? m : (v + (+w - v) * k).toFixed(2); });
}
// '#rrggbb' colours mixed
function lerpColor(a, b, k){
  const p = c => [1, 3, 5].map(i => parseInt(c.slice(i, i + 2), 16));
  const x = p(a), y = p(b);
  return '#' + x.map((v, i) => Math.round(v + (y[i] - v) * k).toString(16).padStart(2, '0')).join('');
}
const PATHS = new WeakMap();
// point and direction at a fraction u (0..1) of a path's length; the lookup is built once
function along(path, u){
  let lut = PATHS.get(path);
  if (!lut) {
    const L = path.getTotalLength(), n = 240, pts = [];
    for (let i = 0; i <= n; i++) { const q = path.getPointAtLength(L * i / n); pts.push([q.x, q.y]); }
    lut = {L, n, pts};
    PATHS.set(path, lut);
  }
  const x = clamp(u) * lut.n, i = Math.min(lut.n - 1, Math.floor(x)), f = x - i;
  const [x0, y0] = lut.pts[i], [x1, y1] = lut.pts[i + 1];
  return {x: x0 + (x1 - x0) * f, y: y0 + (y1 - y0) * f, a: Math.atan2(y1 - y0, x1 - x0) * 180 / Math.PI, L: lut.L};
}
// transform + opacity of one element in one call: {x, y, s, sx, sy, r, o, blur, ox, oy}
function setPose(el, o){
  if (!el) return;
  const s = el.style, sv = el instanceof SVGElement;
  const parts = [];
  if (o.x || o.y) parts.push(`translate(${(o.x || 0).toFixed(2)}px,${(o.y || 0).toFixed(2)}px)`);
  if (o.r) parts.push(`rotate(${o.r.toFixed(3)}deg)`);
  const sx = o.sx ?? o.s ?? 1, sy = o.sy ?? o.s ?? 1;
  if (sx !== 1 || sy !== 1) parts.push(`scale(${sx.toFixed(4)},${sy.toFixed(4)})`);
  s.transform = parts.join(' ');
  if (sv) { s.transformBox = 'fill-box'; s.transformOrigin = o.origin || 'center'; }
  else if (o.origin) s.transformOrigin = o.origin;
  if (o.o !== undefined) s.opacity = clamp(o.o).toFixed(4);
  if (o.blur !== undefined) s.filter = o.blur > 0.05 ? `blur(${o.blur.toFixed(2)}px)` : '';
}
function sceneTools(sec, sc, frame){
  const bt = sc.bt || [], bk = sc.bk || {}, t = sc.t;
  // a time on the slide: seconds, a beat key ('open'), a beat number ('b2'), each with an optional +/- offset
  const at = a => {
    if (typeof a === 'number') return a;
    const m = String(a).match(/^([^+-]+)([+-][\d.]+)?$/);
    const base = !m ? 0 : m[1] in bk ? bk[m[1]] : /^b\d+$/.test(m[1]) ? (bt[+m[1].slice(1)] ?? 0) : 0;
    return base + (m && m[2] ? parseFloat(m[2]) : 0);
  };
  const cache = {}, bw = sc.bw || [];
  const S = {
    t, d: sc.d || 0, t0: sc.s || 0, f: frame || 0, still: !!sc.still, root: sec, W, H, state: SCENE_STATE[sec.id] || (SCENE_STATE[sec.id] = {}),
    at, clamp, lerp, hash, noise: noise1, spring, ease: EASE, lerpPath, lerpColor, along, set: setPose,
    // 0..1 from time `a` over `dur` seconds, through an easing curve (default cubicInOut)
    p: (a, dur = 1, e = 'cubicInOut') => { const u = clamp((t - at(a)) / Math.max(dur, 1e-6)); return (EASE[e] || EASE.cubicInOut)(u); },
    // seconds since time `a` (negative before it)
    since: a => t - at(a),
    el: id => cache[id] || (cache[id] = document.getElementById(id)),
    q: sel => sec.querySelector(sel),
    qa: sel => Array.from(sec.querySelectorAll(sel)),
    // a canvas's 2D context, cleared for this frame
    ctx: id => { const c = document.getElementById(id); const g = c.getContext('2d'); g.setTransform(1, 0, 0, 1, 0, 0); g.clearRect(0, 0, c.width, c.height); return g; },
    morph: (el, a, b, k) => { if (el) el.setAttribute('d', k <= 0 ? a : k >= 1 ? b : lerpPath(a, b, k)); },
    // stroke drawn along its own length from 0 to k (any path, line or polyline)
    stroke: (el, k) => {
      if (!el) return;
      const L = el.__len || (el.__len = el.getTotalLength());
      el.style.strokeDasharray = `${L} ${L}`; el.style.strokeDashoffset = (L * (1 - clamp(k))).toFixed(2);
      el.style.visibility = k <= 0 ? 'hidden' : '';  // a round cap would leave a dot before the stroke starts
    },
    show: (el, k) => { if (el) el.style.opacity = clamp(k).toFixed(4); },
    text: (el, v) => { if (el && el.textContent !== v) el.textContent = v; },
    // when `word` is heard in a beat ('b2' or its key), plus an offset; the beat's start if the word is not in it
    word: (beat, word, off = 0, nth = 0) => {
      const i = /^b\d+$/.test(beat) ? +beat.slice(1) : Object.keys(bk).indexOf(beat) < 0 ? -1 : bt.indexOf(bk[beat]);
      const [text, ct] = bw[i] || ['', []];
      let k = -1;
      for (let n = 0; n <= nth; n++) k = text.indexOf(word, k + 1);
      return (k >= 0 && ct[k] !== undefined ? ct[k] : at(beat)) + off;
    },
    // settle an element in: progress k fades it up, lifts it dy px and pulls it into focus
    soft: (el, k, dy = 18, blur = 6) => setPose(typeof el === 'string' ? document.getElementById(el) : el, {o: k, y: dy * (1 - k), blur: blur * (1 - k)}),
    // a line of type that drifts into focus at time `a` (1.6 s) and out again at `b` (1 s)
    line: (el, a, b = 1e9, dy = 14) => {
      const k = S.p(a, 1.6, 'sineInOut') * (1 - S.p(b, 1.0, 'sineInOut'));
      S.soft(el, k, dy, 10);
    },
    // an SVG bar (or any element) scaled vertically about its centre: waveforms, meters
    scaleY: (el, v) => {
      el = typeof el === 'string' ? document.getElementById(el) : el;
      if (!el) return;
      el.style.transformBox = 'fill-box'; el.style.transformOrigin = '50% 50%';
      el.style.transform = `scaleY(${Math.max(.03, v).toFixed(4)})`;
    },
    // dust drifting up through a light, on a canvas: n motes in box [x, y, w, h], colour 'r,g,b'
    dust: (cv, n, seed, box, rgb, lift = 14) => {
      const g = S.ctx(cv);
      for (let i = 0; i < n; i++) {
        const x = box[0] + box[2] * hash(i, seed) + 40 * noise1(t * .07 + i, seed + 1);
        const y = box[1] + ((box[3] * hash(i, seed + 2) - t * lift * (.4 + hash(i, seed + 3))) % box[3] + box[3]) % box[3];
        const a = .15 + .55 * (.5 + .5 * Math.sin(t * (.6 + hash(i, seed + 4)) + i));
        g.fillStyle = `rgba(${rgb},${a.toFixed(3)})`;
        g.beginPath(); g.arc(x, y, 1 + 2.6 * hash(i, seed + 5), 0, 6.2832); g.fill();
      }
    },
    // [text, time of each character] of a beat ('b2' or its key), for labels that show real timings
    chars: beat => bw[/^b\d+$/.test(beat) ? +beat.slice(1) : bt.indexOf(bk[beat])] || ['', []],
    // camera over a world element: keys [[time, x, y, zoom, dur = 1.6, ease]]; each move starts from
    // wherever the previous one had got to, so overlapping moves blend. Returns [x, y, zoom].
    cam: (el, keys, sway = 0) => {
      let [x, y, z] = [keys[0][1], keys[0][2], keys[0][3]];
      for (const k of keys.slice(1)) {
        const t0 = typeof k[0] === 'number' ? k[0] : at(k[0]);
        if (t < t0) break;
        const u = (EASE[k[5]] || EASE.cubicInOut)(clamp((t - t0) / (k[4] ?? 1.6)));
        x = lerp(x, k[1], u); y = lerp(y, k[2], u); z = Math.exp(lerp(Math.log(z), Math.log(k[3]), u));
      }
      if (sway && !sc.still) { x += sway * noise1(t * .23, 11); y += sway * .6 * noise1(t * .19, 12); }
      if (el) { el.style.transformOrigin = '0 0'; el.style.transform = `translate(${(W / 2 - x * z).toFixed(2)}px,${(H / 2 - y * z).toFixed(2)}px) scale(${z.toFixed(5)})`; }
      return [x, y, z];
    },
  };
  return S;
}
function runScene(sec, sc, frame){
  const def = SCENES[sec.id];
  if (!def || !sc) return;
  const S = sceneTools(sec, sc, frame);
  if (def.setup && !S.state.__ready) { def.setup(S); S.state.__ready = true; }
  def.run(S);
}
// slow push on a slide (theme fx.drift or Slide(drift=)): never quite still, like a camera on a slider
function drift(sec, sc){
  const w = sec.querySelector(':scope > .drift');
  if (!w || !sc) return;
  const amt = +w.dataset.drift || 0, u = sc.still ? 0 : clamp(sc.t / Math.max(sc.d, 1));
  w.style.transform = `scale(${(1 + amt * EASE.sineInOut(u)).toFixed(5)})`;
}

// ---------------------------------------------------------------- film fx: grain, vignette, letterbox
const FX = window.__FX || {};
const GRAIN = [];
function grainTiles(){
  if (!FX.grain) return;
  const n = 192;
  for (let k = 0; k < 6; k++) {
    const c = document.createElement('canvas'); c.width = c.height = n;
    const g = c.getContext('2d'), im = g.createImageData(n, n);
    for (let i = 0; i < n * n; i++) { const v = 128 + (hash(i, k + 7) + hash(i, k + 31) - 1) * 150; im.data[4 * i] = im.data[4 * i + 1] = im.data[4 * i + 2] = v; im.data[4 * i + 3] = 255; }
    g.putImageData(im, 0, 0);
    GRAIN.push(`url(${c.toDataURL()})`);
  }
}
function grain(frame){
  const el = document.getElementById('fx-grain');
  if (!el || !GRAIN.length) return;
  el.style.backgroundImage = GRAIN[frame % GRAIN.length];
  el.style.backgroundPosition = `${Math.floor(hash(frame, 3) * 192)}px ${Math.floor(hash(frame, 5) * 192)}px`;
}

window.__frame = st => {
  for (const el of shown) el.style.display = 'none';
  shown = [];
  clearDirty();
  clearCues();
  let pe = null;
  if (st.prev !== null) { pe = SL[st.prev]; pe.style.display = 'block'; pe.style.opacity = 1; pe.style.zIndex = 1; shown.push(pe); }
  const c = SL[st.cur]; c.style.display = 'block'; c.style.opacity = st.alpha; c.style.zIndex = 2; shown.push(c);
  for (const [id, p] of Object.entries(st.p)) apply(EL[id], p);
  if (st.q) applyCues(st.q);
  runScene(c, st.sc, st.f);
  drift(c, st.sc);
  camera(c, st.cam);
  if (pe) {
    runScene(pe, st.psc, st.f);
    drift(pe, st.psc);
    camera(pe, st.pcam);
    if (st.tr && st.tr.k !== 'fade') transition(st.tr, st.alpha, pe, c);
  }
  grain(st.f || 0);
  const sub = document.getElementById('sub');
  sub.textContent = st.sub || '';
  sub.classList.toggle('ony', c.classList.contains('bg-cover'));
};

// ---------------------------------------------------------------- layout check (stills)
// Boxes on the current slide that leave the canvas, overlap each other, overflow
// their own box or sit in the subtitle band.
window.__layout = (band, avoid) => {
  const c = shown[shown.length - 1], items = [];
  const sel = '.txt,.box,.title,.qrow,.chip,.stat,.pq,.crd,.stp,.tg,.prompt,.coverbox,.cover-row,.kcard,.circle,img.abs,.tbl';
  c.querySelectorAll(sel).forEach(el => {
    if (el.closest('.wm')) return;
    const cs = getComputedStyle(el);
    if (cs.display === 'none' || cs.visibility === 'hidden' || +cs.opacity === 0) return;
    let r = el.getBoundingClientRect();
    if (el.matches('.txt,.title,.qrow,.cover-row')) { const rg = document.createRange(); rg.selectNodeContents(el); r = rg.getBoundingClientRect(); }
    if (r.width < 1 || r.height < 1) return;
    items.push({el, r, name: el.id || el.className.split(' ').filter(x => x !== 'abs')[0] || el.tagName.toLowerCase(),
                text: el.textContent.replace(/\s+/g, '').slice(0, 12)});
  });
  const out = [], tag = it => `${it.name}「${it.text}」`;
  for (const it of items) {
    const r = it.r;
    if (r.left < -2 || r.top < -2 || r.right > W + 2 || r.bottom > H + 2) out.push(`出界 ${tag(it)} (${Math.round(r.left)},${Math.round(r.top)})-(${Math.round(r.right)},${Math.round(r.bottom)})`);
    if (band && r.bottom > band.top && r.top < band.bottom && r.right > band.left && r.left < band.right) out.push(`压字幕 ${tag(it)} 下沿 y=${Math.round(r.bottom)}，字幕区从 y=${Math.round(band.top)} 开始`);
    if (it.el.matches('.box,.chip,.crd,.tg,.stp') && it.el.scrollWidth > it.el.clientWidth + 2) out.push(`溢出 ${tag(it)} 内容宽 ${it.el.scrollWidth}px > 框宽 ${it.el.clientWidth}px`);
  }
  it: for (let i = 0; i < items.length; i++) for (let j = i + 1; j < items.length; j++) {
    const a = items[i], b = items[j];
    if (a.el.contains(b.el) || b.el.contains(a.el)) continue;
    const w = Math.min(a.r.right, b.r.right) - Math.max(a.r.left, b.r.left), h = Math.min(a.r.bottom, b.r.bottom) - Math.max(a.r.top, b.r.top);
    if (w <= 0 || h <= 0) continue;
    const share = w * h / Math.min(a.r.width * a.r.height, b.r.width * b.r.height);
    if (share > 0.08 && w * h > 300) out.push(`重叠 ${tag(a)} × ${tag(b)} ${Math.round(share * 100)}%`);
  }
  document.querySelectorAll('.td').forEach(td => { if (c.contains(td) && td.scrollWidth > td.clientWidth + 2) out.push(`溢出 表格「${td.textContent.slice(0, 12)}」`); });
  // text (any element, line by line) inside an area the theme keeps clear, e.g. the app's buttons
  for (const z of avoid || []) {
    const [x0, y0, x1, y1] = z.box, walk = document.createTreeWalker(c, NodeFilter.SHOW_TEXT);
    for (let n = walk.nextNode(); n; n = walk.nextNode()) {
      const host = n.parentElement;
      if (!n.textContent.trim() || host.closest('.wm')) continue;
      const cs = getComputedStyle(host);
      if (cs.display === 'none' || cs.visibility === 'hidden') continue;
      const rg = document.createRange(); rg.selectNodeContents(n);
      const r = [...rg.getClientRects()].find(r => r.right > x0 && r.left < x1 && r.bottom > y0 && r.top < y1);
      if (r) out.push(`进${z.name || '避让区'} ${host.id || host.className || host.tagName.toLowerCase()}「${n.textContent.replace(/\s+/g, '').slice(0, 12)}」 (${Math.round(r.left)},${Math.round(r.top)})-(${Math.round(r.right)},${Math.round(r.bottom)})`);
    }
  }
  return out;
};

// Theme fonts come from @font-face, which the browser only fetches on first
// use; load them up front and report whether they arrived (else frames would
// quietly fall back to a system font).
window.__ready = (async () => {
  // every @font-face the theme declares (main font plus any extra faces)
  const faces = [...document.fonts];
  await Promise.allSettled(faces.map(f => f.load()));
  await document.fonts.ready;
  prep();
  grainTiles();
  const bad = faces.filter(f => f.status !== 'loaded').map(f => f.family.replace(/^['"]|['"]$/g, ''));
  return {font: bad.join(', '), ok: bad.length === 0, faces: faces.length};
})();
