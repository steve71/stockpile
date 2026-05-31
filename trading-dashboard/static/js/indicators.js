// indicators.js — pure calculation functions, no DOM/chart dependencies

function calcSMA(data, n) {
  return data.map((d, i) => {
    if (i < n - 1) return null;
    const avg = data.slice(i - n + 1, i + 1).reduce((s, x) => s + x.close, 0) / n;
    return { time: d.time, value: avg };
  }).filter(Boolean);
}

function calcEMA(data, n) {
  const k = 2 / (n + 1); let ema = null;
  return data.map((d, i) => {
    if (i === 0) { ema = d.close; return null; }
    ema = d.close * k + ema * (1 - k);
    if (i < n - 1) return null;
    return { time: d.time, value: ema };
  }).filter(Boolean);
}

function calcVWAP(data) {
  let cumPV = 0, cumV = 0;
  return data.map(d => {
    const tp = (d.high + d.low + d.close) / 3;
    cumPV += tp * d.volume; cumV += d.volume;
    return { time: d.time, value: cumV ? cumPV / cumV : tp };
  });
}

function calcBB(data, n = 20, mult = 2) {
  return data.map((d, i) => {
    if (i < n - 1) return null;
    const sl = data.slice(i - n + 1, i + 1);
    const mean = sl.reduce((s, x) => s + x.close, 0) / n;
    const sd = Math.sqrt(sl.reduce((s, x) => s + (x.close - mean) ** 2, 0) / n);
    return { time: d.time, mid: mean, upper: mean + mult * sd, lower: mean - mult * sd };
  }).filter(Boolean);
}

function calcDonchian(data, n = 20) {
  return data.map((d, i) => {
    if (i < n - 1) return null;
    const sl = data.slice(i - n + 1, i + 1);
    return { time: d.time, upper: Math.max(...sl.map(x => x.high)), lower: Math.min(...sl.map(x => x.low)) };
  }).filter(Boolean);
}

function calcATR(data, n = 14) {
  const trs = data.map((d, i) => {
    if (i === 0) return d.high - d.low;
    const pc = data[i - 1].close;
    return Math.max(d.high - d.low, Math.abs(d.high - pc), Math.abs(d.low - pc));
  });
  let atr = trs.slice(0, n).reduce((a, b) => a + b, 0) / n;
  return data.map((d, i) => {
    if (i < n) return null;
    atr = (atr * (n - 1) + trs[i]) / n;
    return { time: d.time, value: atr };
  }).filter(Boolean);
}

function calcKeltner(data, n = 20, mult = 1.5) {
  const emas = calcEMA(data, n);
  const atrs = calcATR(data, n);
  const em = new Map(emas.map(e => [e.time, e.value]));
  const am = new Map(atrs.map(a => [a.time, a.value]));
  return data.map(d => {
    const e = em.get(d.time), a = am.get(d.time);
    if (e == null || a == null) return null;
    return { time: d.time, upper: e + mult * a, mid: e, lower: e - mult * a };
  }).filter(Boolean);
}

function calcPSAR(data, step = 0.02, max = 0.2) {
  if (data.length < 2) return [];
  let bull = true, sar = data[0].low, ep = data[0].high, af = step;
  return data.map((d, i) => {
    if (i === 0) return { time: d.time, value: sar };
    sar = sar + af * (ep - sar);
    if (bull) {
      if (d.low < sar) { bull = false; sar = ep; ep = d.low; af = step; }
      else { if (d.high > ep) { ep = d.high; af = Math.min(af + step, max); } sar = Math.min(sar, data[i - 1].low, d.low); }
    } else {
      if (d.high > sar) { bull = true; sar = ep; ep = d.high; af = step; }
      else { if (d.low < ep) { ep = d.low; af = Math.min(af + step, max); } sar = Math.max(sar, data[i - 1].high, d.high); }
    }
    return { time: d.time, value: sar };
  });
}

function calcSupertrend(data, n = 10, mult = 3) {
  const atrs = calcATR(data, n);
  const am = new Map(atrs.map(a => [a.time, a.value]));
  let trend = 1, st = 0;
  return data.map((d, i) => {
    const atr = am.get(d.time);
    if (!atr) return null;
    const mid = (d.high + d.low) / 2;
    const up = mid + mult * atr, dn = mid - mult * atr;
    if (i === 0) { st = dn; return { time: d.time, value: st, color: '#16c784' }; }
    if (trend === 1) { st = Math.max(dn, st); if (d.close < st) { trend = -1; st = up; } }
    else { st = Math.min(up, st); if (d.close > st) { trend = 1; st = dn; } }
    return { time: d.time, value: st, color: trend === 1 ? '#16c784' : '#ea3943' };
  }).filter(Boolean);
}

function calcIchimoku(data) {
  const hi = (arr, n) => Math.max(...arr.slice(-n).map(x => x.high));
  const lo = (arr, n) => Math.min(...arr.slice(-n).map(x => x.low));
  return data.map((d, i) => {
    if (i < 52) return null;
    const sl = data.slice(0, i + 1);
    const tenkan = (hi(sl, 9) + lo(sl, 9)) / 2;
    const kijun = (hi(sl, 26) + lo(sl, 26)) / 2;
    const senkA = (tenkan + kijun) / 2;
    const senkB = (hi(sl, 52) + lo(sl, 52)) / 2;
    return { time: d.time, tenkan, kijun, senkA, senkB };
  }).filter(Boolean);
}

function calcPivot(data) {
  const last = data[data.length - 1];
  const pp = (last.high + last.low + last.close) / 3;
  return { pp, r1: 2 * pp - last.low, r2: pp + (last.high - last.low), s1: 2 * pp - last.high, s2: pp - (last.high - last.low) };
}

function calcRSI(data, n = 14) {
  if (data.length < n + 2) return [];
  let ag = 0, al = 0;
  for (let i = 1; i <= n; i++) {
    const d = data[i].close - data[i - 1].close;
    if (d > 0) ag += d; else al -= d;
  }
  ag /= n; al /= n;
  const result = [];
  for (let i = n; i < data.length; i++) {
    if (i > n) {
      const d2 = data[i].close - data[i - 1].close;
      ag = (ag * (n - 1) + (d2 > 0 ? d2 : 0)) / n;
      al = (al * (n - 1) + (d2 < 0 ? -d2 : 0)) / n;
    }
    const rs = al === 0 ? 100 : ag / al;
    result.push({ time: data[i].time, value: 100 - (100 / (1 + rs)) });
  }
  return result;
}

function calcMACD(data, fast = 12, slow = 26, sig = 9) {
  const ef = calcEMA(data, fast), es = calcEMA(data, slow);
  const ef2 = new Map(ef.map(e => [e.time, e.value]));
  const es2 = new Map(es.map(e => [e.time, e.value]));
  const macdLine = data.map(d => {
    const f = ef2.get(d.time), s = es2.get(d.time);
    if (f == null || s == null) return null;
    return { time: d.time, value: f - s };
  }).filter(Boolean);
  if (!macdLine.length) return [];
  const k = 2 / (sig + 1); let sigEMA = macdLine[0].value;
  return macdLine.map((d, i) => {
    if (i > 0) sigEMA = d.value * k + sigEMA * (1 - k);
    return { time: d.time, macd: d.value, signal: sigEMA, hist: d.value - sigEMA };
  });
}

function calcStoch(data, kp = 14, dp = 3) {
  const kArr = data.map((d, i) => {
    if (i < kp - 1) return null;
    const sl = data.slice(i - kp + 1, i + 1);
    const lo = Math.min(...sl.map(x => x.low)), hi = Math.max(...sl.map(x => x.high));
    const k = (hi === lo) ? 50 : (d.close - lo) / (hi - lo) * 100;
    return { time: d.time, k };
  }).filter(Boolean);
  return kArr.map((d, i, arr) => {
    const dk = arr.slice(Math.max(0, i - dp + 1), i + 1);
    return { ...d, d: dk.reduce((s, x) => s + x.k, 0) / dk.length };
  });
}

function calcCCI(data, n = 20) {
  return data.map((d, i) => {
    if (i < n - 1) return null;
    const sl = data.slice(i - n + 1, i + 1);
    const tp = sl.map(x => (x.high + x.low + x.close) / 3);
    const mean = tp.reduce((a, b) => a + b, 0) / n;
    const md = tp.reduce((s, x) => s + Math.abs(x - mean), 0) / n;
    const tp0 = (d.high + d.low + d.close) / 3;
    return { time: d.time, value: md === 0 ? 0 : (tp0 - mean) / (0.015 * md) };
  }).filter(Boolean);
}

function calcWilliamsR(data, n = 14) {
  return data.map((d, i) => {
    if (i < n - 1) return null;
    const sl = data.slice(i - n + 1, i + 1);
    const hi = Math.max(...sl.map(x => x.high)), lo = Math.min(...sl.map(x => x.low));
    return { time: d.time, value: hi === lo ? -50 : ((hi - d.close) / (hi - lo)) * -100 };
  }).filter(Boolean);
}

function calcOBV(data) {
  let obv = 0;
  return data.map((d, i) => {
    if (i > 0) {
      if (d.close > data[i - 1].close) obv += d.volume;
      else if (d.close < data[i - 1].close) obv -= d.volume;
    }
    return { time: d.time, value: obv };
  });
}

function calcMFI(data, n = 14) {
  const mf = data.map((d, i) => {
    const tp = (d.high + d.low + d.close) / 3;
    const pos = i > 0 && tp > (data[i - 1].high + data[i - 1].low + data[i - 1].close) / 3;
    return { tp, vol: d.volume, pos };
  });
  return data.map((d, i) => {
    if (i < n) return null;
    const sl = mf.slice(i - n + 1, i + 1);
    const pmf = sl.filter(x => x.pos).reduce((s, x) => s + x.tp * x.vol, 0);
    const nmf = sl.filter(x => !x.pos).reduce((s, x) => s + x.tp * x.vol, 0);
    return { time: d.time, value: nmf === 0 ? 100 : 100 - (100 / (1 + pmf / nmf)) };
  }).filter(Boolean);
}

function calcADX(data, n = 14) {
  if (data.length < n + 1) return [];
  const result = [];
  let pdi = 0, ndi = 0, adx = 0;
  const trs = [], pdms = [], ndms = [];
  for (let i = 1; i < data.length; i++) {
    const upMove = data[i].high - data[i - 1].high;
    const downMove = data[i - 1].low - data[i].low;
    trs.push(Math.max(data[i].high - data[i].low, Math.abs(data[i].high - data[i - 1].close), Math.abs(data[i].low - data[i - 1].close)));
    pdms.push(upMove > downMove && upMove > 0 ? upMove : 0);
    ndms.push(downMove > upMove && downMove > 0 ? downMove : 0);
  }
  let atr = trs.slice(0, n).reduce((a, b) => a + b, 0);
  let spdm = pdms.slice(0, n).reduce((a, b) => a + b, 0);
  let sndm = ndms.slice(0, n).reduce((a, b) => a + b, 0);
  let dxSum = 0;
  for (let i = n; i < trs.length; i++) {
    if (i > n) { atr = atr - atr / n + trs[i]; spdm = spdm - spdm / n + pdms[i]; sndm = sndm - sndm / n + ndms[i]; }
    pdi = atr > 0 ? spdm / atr * 100 : 0; ndi = atr > 0 ? sndm / atr * 100 : 0;
    const dx = (pdi + ndi) > 0 ? Math.abs(pdi - ndi) / (pdi + ndi) * 100 : 0;
    if (i < n * 2 - 1) { dxSum += dx; }
    else if (i === n * 2 - 1) { dxSum += dx; adx = dxSum / n; result.push({ time: data[i + 1].time, value: adx, pdi, ndi }); }
    else { adx = (adx * (n - 1) + dx) / n; result.push({ time: data[i + 1].time, value: adx, pdi, ndi }); }
  }
  return result;
}

function calcFVG(data, maxGaps = 8) {
  const gaps = [];
  for (let i = 2; i < data.length; i++) {
    const prev = data[i - 2], curr = data[i];
    if (curr.low > prev.high)
      gaps.push({ type: 'bull', top: curr.low, bot: prev.high, time: data[i - 1].time, formIdx: i });
    else if (curr.high < prev.low)
      gaps.push({ type: 'bear', top: prev.low, bot: curr.high, time: data[i - 1].time, formIdx: i });
  }
  const active = gaps.filter(g => {
    for (let j = g.formIdx + 1; j < data.length; j++) {
      const c = data[j];
      if (g.type === 'bull' && c.low <= g.top) return false;
      if (g.type === 'bear' && c.high >= g.bot) return false;
    }
    return true;
  });
  return active.slice(-maxGaps);
}

function calcVPVR(data, bins = 24) {
  if (!data.length) return { bars: [], poc: 0, vah: 0, val: 0 };
  const hi = Math.max(...data.map(d => d.high));
  const lo = Math.min(...data.map(d => d.low));
  const range = hi - lo || 1, size = range / bins;
  const vols = new Array(bins).fill(0);
  data.forEach(d => {
    const vol = d.volume || 1;
    for (let b = 0; b < bins; b++) {
      const blo = lo + b * size, bhi = blo + size;
      const overlap = Math.min(d.high, bhi) - Math.max(d.low, blo);
      if (overlap > 0) vols[b] += vol * (overlap / (d.high - d.low || size));
    }
  });
  const maxV = Math.max(...vols);
  const poc = lo + (vols.indexOf(maxV) + 0.5) * size;
  const total = vols.reduce((a, b) => a + b, 0);
  let cum = 0;
  const sorted = [...vols.entries()].sort((a, b) => b[1] - a[1]);
  const vaSet = new Set();
  for (const [idx] of sorted) { cum += vols[idx]; vaSet.add(idx); if (cum >= total * 0.7) break; }
  const vaIdxs = [...vaSet].sort((a, b) => a - b);
  const vahIdx = vaIdxs[vaIdxs.length - 1], valIdx = vaIdxs[0];
  return {
    bars: vols.map((v, i) => ({ price: lo + (i + 0.5) * size, vol: v, maxV, isPoc: vols.indexOf(maxV) === i, isVa: vaSet.has(i), pct: v / maxV })),
    poc, vah: lo + (vahIdx + 1) * size, val: lo + valIdx * size,
    vahMid: lo + (vahIdx + 0.5) * size, valMid: lo + (valIdx + 0.5) * size,
    priceMin: lo, priceMax: hi,
  };
}

function calcFRVP(data, startTime, endTime, bins = 24) {
  const slice = data.filter(d => d.time >= startTime && d.time <= endTime);
  if (!slice.length) return { bars: [], poc: 0, vah: 0, val: 0, priceMin: 0, priceMax: 0, candleCount: 0 };
  const hi = Math.max(...slice.map(d => d.high));
  const lo = Math.min(...slice.map(d => d.low));
  const range = hi - lo || 1, size = range / bins;
  const vols = new Array(bins).fill(0), buyVols = new Array(bins).fill(0);
  slice.forEach(d => {
    const vol = d.volume || 1, isBull = d.close >= d.open;
    for (let b = 0; b < bins; b++) {
      const blo = lo + b * size, bhi = blo + size;
      const overlap = Math.min(d.high, bhi) - Math.max(d.low, blo);
      if (overlap > 0) {
        const portion = vol * (overlap / (d.high - d.low || size));
        vols[b] += portion;
        if (isBull) buyVols[b] += portion;
      }
    }
  });
  const maxV = Math.max(...vols) || 1;
  const total = vols.reduce((a, b) => a + b, 0);
  let cum = 0;
  const sorted = [...vols.entries()].sort((a, b) => b[1] - a[1]);
  const vaSet = new Set();
  for (const [idx] of sorted) { cum += vols[idx]; vaSet.add(idx); if (cum >= total * 0.7) break; }
  const pocIdx = vols.indexOf(maxV);
  const vaIdxs = [...vaSet].sort((a, b) => a - b);
  return {
    bars: vols.map((v, i) => ({ price: lo + (i + 0.5) * size, vol: v, buyVol: buyVols[i], maxV, isPoc: pocIdx === i, isVa: vaSet.has(i), pct: v / maxV })),
    poc: lo + (pocIdx + 0.5) * size,
    vah: lo + (vaIdxs[vaIdxs.length - 1] + 1) * size,
    val: lo + vaIdxs[0] * size,
    priceMin: lo, priceMax: hi,
    candleCount: slice.length,
  };
}
