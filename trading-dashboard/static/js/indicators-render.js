// indicators-render.js — DOM/chart rendering for all indicators
// Depends on: indicators.js (calc functions), LightweightCharts global, state, fmt()

const IND_DEFAULT_COLORS = {
  'sma20':'#f7c948','sma50':'#35c2c1','sma200':'#ea3943',
  'ema20':'#f7c948','ema50':'#35c2c1','ema200':'#ea3943',
  'vwap':'#a78bfa',
  'bb':'#35c2c1','donchian':'#f7c948','keltner':'#a78bfa',
  'psar':'#f97316','supertrend':'#16c784','ichimoku':'#35c2c1',
  'pivot':'#ffffff','fvg':'#16c784','vpvr':'#35c2c1','frvp':'#35c2c1',
  'volume':'#35c2c1','obv':'#35c2c1','mfi':'#a78bfa',
  'rsi':'#f7c948','macd':'#35c2c1','stoch':'#35c2c1',
  'cci':'#f97316','williams':'#a78bfa','atr':'#f7c948','adx':'#35c2c1',
};

function renderDrawer(paneId, ps) {
  const drawer = document.querySelector(`.pane[data-id="${paneId}"] .drawer`);
  if (!drawer) return;
  drawer.innerHTML = '';
  const hdr = document.createElement('div');
  hdr.className = 'drawer-hdr';
  hdr.innerHTML = '<span>Indicators</span>';
  const cl = document.createElement('button');
  cl.className = 'drawer-close'; cl.textContent = '✕';
  cl.onclick = () => drawer.classList.remove('open');
  hdr.appendChild(cl);
  drawer.appendChild(hdr);
  IND_SECTIONS.forEach((sec, si) => {
    if (si > 0) { const sep = document.createElement('div'); sep.className = 'ind-sep'; drawer.appendChild(sep); }
    const title = document.createElement('div');
    title.className = 'sec-title'; title.textContent = sec.title;
    drawer.appendChild(title);
    sec.items.forEach(item => {
      const row = document.createElement('label');
      row.className = 'ind-item';
      const cb = document.createElement('input');
      cb.type = 'checkbox';
      cb.checked = !!(ps.indicators && ps.indicators[item.id]);
      cb.addEventListener('change', () => {
        ps.indicators = ps.indicators || {};
        ps.indicators[item.id] = cb.checked;
        saveState();
        renderIndicators(paneId);
      });
      row.appendChild(cb);
      // Color swatch for simple line indicators
      const noSwatch = ['Trend', 'Price Action', 'Bands & Channels'];
      const noSwatchIds = ['volume', 'macd', 'stoch'];
      if (!noSwatch.includes(sec.title) && !noSwatchIds.includes(item.id)) {
        const col = (ps.indColors && ps.indColors[item.id]) || IND_DEFAULT_COLORS[item.id] || '#35c2c1';
        const cp = document.createElement('input');
        cp.type = 'color'; cp.value = col;
        cp.style.cssText = 'position:absolute;width:0;height:0;opacity:0;pointer-events:none;';
        const sw = document.createElement('span');
        sw.style.cssText = `display:inline-block;width:13px;height:13px;border-radius:2px;flex-shrink:0;cursor:pointer;border:1px solid rgba(255,255,255,.3);box-sizing:border-box;background:${col};`;
        sw.title = 'Change color';
        sw.addEventListener('click', e => { e.preventDefault(); e.stopPropagation(); cp.click(); });
        cp.addEventListener('input', e => {
          sw.style.background = e.target.value;
          ps.indColors = ps.indColors || {};
          ps.indColors[item.id] = e.target.value;
          saveState(); renderIndicators(paneId);
        });
        row.appendChild(sw); row.appendChild(cp);
      }
      row.appendChild(document.createTextNode(item.label));
      drawer.appendChild(row);
    });
  });
}

function renderIndicators(paneId) {
  const ps = state.panes.find(p => p.id === paneId);
  const inst = state.charts.get(paneId);
  const pane = document.querySelector(`.pane[data-id="${paneId}"]`);
  if (!ps || !inst || !pane) return;
  const data = inst.candles;
  if (!data || !data.length) return;
  const { chart, series } = inst;
  const C = (id, fb) => (ps.indColors && ps.indColors[id]) || IND_DEFAULT_COLORS[id] || fb;

  _cleanupIndicators(paneId, inst, chart, series, pane);

  const active = ps.indicators || {};

  // ── Overlay: Moving Averages ─────────────────────────────────────────────
  if (active.sma20)  _addLine(inst, chart, calcSMA(data, 20),  C('sma20',  '#f7c948'), 1);
  if (active.sma50)  _addLine(inst, chart, calcSMA(data, 50),  C('sma50',  '#35c2c1'), 1);
  if (active.sma200) _addLine(inst, chart, calcSMA(data, 200), C('sma200', '#ea3943'), 1);
  if (active.ema20)  _addLine(inst, chart, calcEMA(data, 20),  C('ema20',  '#f7c948'), 1, 1);
  if (active.ema50)  _addLine(inst, chart, calcEMA(data, 50),  C('ema50',  '#35c2c1'), 1, 1);
  if (active.ema200) _addLine(inst, chart, calcEMA(data, 200), C('ema200', '#ea3943'), 1, 1);
  if (active.vwap)   _addLine(inst, chart, calcVWAP(data),     C('vwap',   '#a78bfa'), 1);

  // ── Overlay: Bands ───────────────────────────────────────────────────────
  if (active.bb) {
    const bb = calcBB(data); const col = C('bb', '#35c2c1');
    _addLine(inst, chart, bb.map(d => ({ time: d.time, value: d.upper })), col, 1);
    _addLine(inst, chart, bb.map(d => ({ time: d.time, value: d.mid   })), col, 1, 2);
    _addLine(inst, chart, bb.map(d => ({ time: d.time, value: d.lower })), col, 1);
  }
  if (active.donchian) {
    const dc = calcDonchian(data); const col = C('donchian', '#f7c948');
    _addLine(inst, chart, dc.map(d => ({ time: d.time, value: d.upper })), col, 1);
    _addLine(inst, chart, dc.map(d => ({ time: d.time, value: d.lower })), col, 1);
  }
  if (active.keltner) {
    const kc = calcKeltner(data); const col = C('keltner', '#a78bfa');
    _addLine(inst, chart, kc.map(d => ({ time: d.time, value: d.upper })), col, 1);
    _addLine(inst, chart, kc.map(d => ({ time: d.time, value: d.mid   })), col, 1, 2);
    _addLine(inst, chart, kc.map(d => ({ time: d.time, value: d.lower })), col, 1);
  }

  // ── Overlay: Trend ───────────────────────────────────────────────────────
  if (active.psar) _renderPSAR(inst, chart, data);
  if (active.supertrend) _addLine(inst, chart, calcSupertrend(data).map(d => ({ time: d.time, value: d.value })), C('supertrend', '#16c784'), 2);
  if (active.ichimoku) {
    const ich = calcIchimoku(data);
    const colors = ['#35c2c1', '#f7c948', 'rgba(22,199,132,.3)', 'rgba(234,57,67,.3)'];
    ['tenkan', 'kijun', 'senkA', 'senkB'].forEach((k, i) =>
      _addLine(inst, chart, ich.map(d => ({ time: d.time, value: d[k] })), colors[i], 1));
  }
  if (active.pivot) {
    const pv = calcPivot(data);
    [{ v: pv.pp, c: '#ffffff' }, { v: pv.r1, c: '#16c784' }, { v: pv.r2, c: '#16c784' },
     { v: pv.s1, c: '#ea3943' }, { v: pv.s2, c: '#ea3943' }].forEach(({ v, c }) =>
      _addLine(inst, chart, data.map(d => ({ time: d.time, value: v })), c, 1, 2));
  }

  // ── Canvas: FVG ──────────────────────────────────────────────────────────
  if (active.fvg) _renderFVG(inst, chart, series, data, pane);

  // ── Canvas: VPVR ─────────────────────────────────────────────────────────
  if (active.vpvr) _renderVPVR(inst, chart, series, data, pane);

  // ── Canvas: FRVP ─────────────────────────────────────────────────────────
  if (active.frvp) _renderFRVP(inst, chart, series, data, pane, ps, paneId);

  // ── Sub-panels ───────────────────────────────────────────────────────────
  _renderSubPanels(inst, chart, data, ps, pane, paneId, active);
}

// ── Helpers ──────────────────────────────────────────────────────────────────

function _addLine(inst, chart, data, color, lineWidth, lineStyle = 0) {
  const s = chart.addLineSeries({ color, lineWidth, lineStyle, priceLineVisible: false, lastValueVisible: false });
  s.setData(data);
  inst.indSeries.push(s);
  return s;
}

function _renderPSAR(inst, chart, data) {
  const psarData = calcPSAR(data);
  const segments = []; let current = [], prevBull = null;
  psarData.forEach((pt, i) => {
    if (i === 0) { current.push(pt); prevBull = true; return; }
    const curBull = data[i].close >= pt.value;
    if (prevBull !== curBull) { segments.push({ bull: prevBull, points: current }); current = [pt]; prevBull = curBull; }
    else { current.push(pt); }
  });
  if (current.length) segments.push({ bull: prevBull, points: current });
  segments.forEach(seg => {
    const s = chart.addLineSeries({ color: seg.bull ? '#16c784' : '#ea3943', lineWidth: 0, lineVisible: false, pointMarkersVisible: true, priceLineVisible: false, lastValueVisible: false, crosshairMarkerVisible: false });
    s.setData(seg.points);
    inst.indSeries.push(s);
  });
}

function _cleanupIndicators(paneId, inst, chart, series, pane) {
  if (inst.syncFns) {
    inst.syncFns.forEach(({ chart: sc, rangeFn, crossFn }) => {
      try { chart.timeScale().unsubscribeVisibleLogicalRangeChange(rangeFn); } catch {}
      try { chart.unsubscribeCrosshairMove(crossFn); } catch {}
      try { sc.remove(); } catch {}
    });
    inst.syncFns = [];
  }
  if (inst.indSeries) inst.indSeries.forEach(s => { try { chart.removeSeries(s); } catch {} });
  inst.indSeries = [];
  if (inst.fvgDraw) {
    try { chart.timeScale().unsubscribeVisibleLogicalRangeChange(inst.fvgDraw); } catch {}
    try { chart.unsubscribeCrosshairMove(inst.fvgDraw); } catch {}
    inst.fvgDraw = null;
  }
  inst.vpvrDraw = null;
  if (inst.vpvrLines) { inst.vpvrLines.forEach(pl => { try { series.removePriceLine(pl); } catch {} }); inst.vpvrLines = []; }
  const subPanels = pane.querySelector('.sub-panels');
  if (subPanels) while (subPanels.firstChild) subPanels.removeChild(subPanels.firstChild);
  pane.querySelector('.overlay-canvas')?.remove();
  pane.querySelector('.vpvr-canvas')?.remove();
  pane.querySelector('.frvp-canvas')?.remove();
  pane.querySelector('.frvp-reset')?.remove();
  if (inst.frvpClickHandler) { try { chart.unsubscribeClick(inst.frvpClickHandler); } catch {} inst.frvpClickHandler = null; }
  inst.frvpDraw = null;
}

function _renderFVG(inst, chart, series, data, pane) {
  const wrap = pane.querySelector('.chart-wrap');
  let cv = pane.querySelector('.overlay-canvas');
  if (!cv) {
    cv = document.createElement('canvas');
    cv.className = 'overlay-canvas';
    cv.style.cssText = 'position:absolute;inset:0;pointer-events:none;z-index:4;';
    wrap.appendChild(cv);
  }
  const PRICE_SCALE_W = 70;
  const drawFVG = () => {
    const w = wrap.clientWidth, h = wrap.clientHeight;
    if (!w || !h) return;
    cv.width = w; cv.height = h;
    const ctx = cv.getContext('2d');
    ctx.clearRect(0, 0, w, h);
    const gaps = calcFVG(data);
    if (!gaps.length) return;
    const ts = chart.timeScale();
    const rightEdge = w - PRICE_SCALE_W;
    gaps.forEach(g => {
      try {
        const x1 = ts.timeToCoordinate(g.time);
        if (x1 == null || x1 > rightEdge) return;
        const y1 = series.priceToCoordinate(g.top), y2 = series.priceToCoordinate(g.bot);
        if (y1 == null || y2 == null) return;
        const rectX = Math.max(0, x1), rectW = rightEdge - rectX;
        if (rectW <= 0) return;
        const rectY = Math.min(y1, y2), rectH = Math.max(1, Math.abs(y2 - y1));
        const bull = g.type === 'bull';
        ctx.fillStyle = bull ? 'rgba(22,199,132,.15)' : 'rgba(234,57,67,.15)';
        ctx.fillRect(rectX, rectY, rectW, rectH);
        ctx.strokeStyle = bull ? 'rgba(22,199,132,.55)' : 'rgba(234,57,67,.55)';
        ctx.lineWidth = 1;
        ctx.beginPath();
        ctx.moveTo(rectX, rectY); ctx.lineTo(rectX + rectW, rectY);
        ctx.moveTo(rectX, rectY + rectH); ctx.lineTo(rectX + rectW, rectY + rectH);
        ctx.stroke();
      } catch {}
    });
  };
  requestAnimationFrame(drawFVG);
  chart.timeScale().subscribeVisibleLogicalRangeChange(drawFVG);
  chart.subscribeCrosshairMove(drawFVG);
  inst.fvgDraw = drawFVG;
}

function _renderVPVR(inst, chart, series, data, pane) {
  const wrap = pane.querySelector('.chart-wrap');
  let cv = pane.querySelector('.vpvr-canvas');
  if (!cv) {
    cv = document.createElement('canvas');
    cv.className = 'vpvr-canvas';
    cv.style.cssText = 'position:absolute;top:0;right:70px;bottom:0;width:80px;pointer-events:none;z-index:4;';
    wrap.appendChild(cv);
  }
  const BAR_AREA = 80;
  const drawVPVR = () => {
    const cssW = BAR_AREA, cssH = wrap.clientHeight;
    if (!cssH) return;
    const dpr = window.devicePixelRatio || 1;
    cv.width = cssW * dpr; cv.height = cssH * dpr;
    const ctx = cv.getContext('2d');
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    ctx.clearRect(0, 0, cssW, cssH);
    const vp = calcVPVR(data);
    if (!vp.bars.length) return;
    const barH = Math.max(1.5, cssH / vp.bars.length * 0.85);
    vp.bars.forEach(b => {
      const y = series.priceToCoordinate(b.price);
      if (y == null || y < 0 || y > cssH) return;
      const barW = Math.max(2, b.pct * (cssW - 2));
      ctx.fillStyle = b.isPoc ? '#f7c948' : b.isVa ? 'rgba(53,194,193,.55)' : 'rgba(53,194,193,.28)';
      ctx.fillRect(cssW - barW, y - barH / 2, barW, barH);
    });
  };
  requestAnimationFrame(drawVPVR);
  chart.timeScale().subscribeVisibleLogicalRangeChange(drawVPVR);
  chart.subscribeCrosshairMove(drawVPVR);
  inst.vpvrDraw = drawVPVR;
  const vp0 = calcVPVR(data);
  inst.vpvrLines = [
    series.createPriceLine({ price: vp0.poc, color: '#f7c948', lineWidth: 2, lineStyle: LightweightCharts.LineStyle.Solid, axisLabelVisible: true, title: 'POC' }),
    series.createPriceLine({ price: vp0.vahMid, color: '#16c784', lineWidth: 1, lineStyle: LightweightCharts.LineStyle.Dotted, axisLabelVisible: true, title: 'VAH' }),
    series.createPriceLine({ price: vp0.valMid, color: '#ea3943', lineWidth: 1, lineStyle: LightweightCharts.LineStyle.Dotted, axisLabelVisible: true, title: 'VAL' }),
  ];
}

function _renderFRVP(inst, chart, series, data, pane, ps, paneId) {
  const wrap = pane.querySelector('.chart-wrap');
  let cv = pane.querySelector('.frvp-canvas');
  if (!cv) {
    cv = document.createElement('canvas');
    cv.className = 'frvp-canvas';
    cv.style.cssText = 'position:absolute;inset:0;width:100%;height:100%;pointer-events:none;z-index:3;';
    wrap.appendChild(cv);
  }
  const BINS = 16;

  const drawFRVP = () => {
    const w = wrap.clientWidth, h = wrap.clientHeight;
    if (!w || !h) return;
    const dpr = window.devicePixelRatio || 1;
    cv.width = w * dpr; cv.height = h * dpr;
    const ctx = cv.getContext('2d');
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    ctx.clearRect(0, 0, w, h);
    const rng = ps.frvpRange;
    if (!rng || !rng.startTime || !rng.endTime) {
      const step = ps._frvpStep || 0;
      ctx.fillStyle = 'rgba(53,194,193,0.75)';
      ctx.font = 'bold 11px system-ui,sans-serif';
      ctx.textAlign = 'center';
      ctx.fillText(step === 1 ? '🔹 Click candle to set FRVP end' : '🔹 Click any candle to set FRVP start', w / 2, 22);
      return;
    }
    const ts = chart.timeScale();
    const st = Math.min(rng.startTime, rng.endTime), et = Math.max(rng.startTime, rng.endTime);
    const x1 = ts.timeToCoordinate(st), x2 = ts.timeToCoordinate(et);
    if (x1 == null || x2 == null) return;
    const lx = Math.min(x1, x2), rx = Math.max(x1, x2), rngW = rx - lx;
    if (rngW < 4) return;
    const vp = calcFRVP(data, st, et, BINS);
    if (!vp.bars.length) return;

    const startIdx = data.findIndex(d => d.time >= st);
    let barPitch = rngW / Math.max(1, vp.candleCount);
    if (startIdx > 0) {
      const pa = ts.timeToCoordinate(data[startIdx - 1].time), pb = ts.timeToCoordinate(data[startIdx].time);
      if (pa != null && pb != null) barPitch = Math.abs(pb - pa);
    } else if (startIdx >= 0 && startIdx < data.length - 1) {
      const pa = ts.timeToCoordinate(data[startIdx].time), pb = ts.timeToCoordinate(data[startIdx + 1].time);
      if (pa != null && pb != null) barPitch = Math.abs(pb - pa);
    }
    const profLeft = x1 - barPitch * 0.5, profRight = x1 + barPitch * 0.5, maxBarW = barPitch;

    // Range highlight
    ctx.fillStyle = 'rgba(255,255,255,0.022)';
    ctx.fillRect(lx, 0, rngW, h);
    ctx.save();
    ctx.strokeStyle = 'rgba(255,255,255,0.18)'; ctx.lineWidth = 1; ctx.setLineDash([5, 4]);
    [lx, rx].forEach(x => { ctx.beginPath(); ctx.moveTo(x, 0); ctx.lineTo(x, h); ctx.stroke(); });
    ctx.restore();

    const topPxY = series.priceToCoordinate(vp.priceMax), botPxY = series.priceToCoordinate(vp.priceMin);
    const rangePixH = (topPxY != null && botPxY != null) ? Math.abs(botPxY - topPxY) : h;
    const binPixH = rangePixH / BINS, barH = Math.max(1, binPixH * 0.80);

    vp.bars.forEach(b => {
      if (b.vol <= 0) return;
      const y = series.priceToCoordinate(b.price);
      if (y == null || y < -barH || y > h + barH) return;
      const bw = b.pct * maxBarW;
      if (bw < 0.3) return;
      const sellVol = b.vol - b.buyVol;
      const sellW = bw * (sellVol / b.vol), buyW = bw * (b.buyVol / b.vol);
      const yTop = y - barH / 2;
      if (b.isPoc) { ctx.fillStyle = 'rgba(247,201,72,0.15)'; ctx.fillRect(profLeft, yTop, bw, barH); }
      ctx.fillStyle = b.isPoc ? 'rgba(234,57,67,0.92)' : 'rgba(234,57,67,0.62)';
      if (sellW > 0.3) ctx.fillRect(profLeft, yTop, sellW, barH);
      ctx.fillStyle = b.isPoc ? 'rgba(22,199,132,0.92)' : 'rgba(22,199,132,0.62)';
      if (buyW > 0.3) ctx.fillRect(profLeft + sellW, yTop, buyW, barH);
      if (b.isPoc) { ctx.strokeStyle = 'rgba(247,201,72,0.80)'; ctx.lineWidth = 1; ctx.strokeRect(profLeft, yTop, bw, barH); }
    });

    const labelX = rx + 5;
    const drawHLine = (py, color, dash, label, price) => {
      if (py == null || py < 0 || py > h) return;
      ctx.save(); ctx.strokeStyle = color; ctx.lineWidth = 1; ctx.setLineDash(dash);
      ctx.beginPath(); ctx.moveTo(profLeft, py); ctx.lineTo(w - 72, py); ctx.stroke(); ctx.restore();
      ctx.fillStyle = color; ctx.font = 'bold 10px system-ui,sans-serif'; ctx.textAlign = 'left';
      ctx.fillText(`${label}  ${fmt(price)}`, labelX, py - 2);
    };
    drawHLine(series.priceToCoordinate(vp.poc), 'rgba(247,201,72,0.9)', [6, 3], 'POC', vp.poc);
    drawHLine(series.priceToCoordinate(vp.vah), 'rgba(22,199,132,0.8)', [4, 3], 'VAH', vp.vah);
    drawHLine(series.priceToCoordinate(vp.val), 'rgba(234,57,67,0.8)', [4, 3], 'VAL', vp.val);
    ctx.fillStyle = 'rgba(154,168,199,0.6)'; ctx.font = '9px system-ui,sans-serif'; ctx.textAlign = 'center';
    ctx.fillText(`${vp.candleCount} bars`, lx + rngW / 2, h - 5);
  };

  ps._frvpStep = ps.frvpRange ? 2 : 0;
  let tempStart = null;

  const showResetBtn = () => {
    if (pane.querySelector('.frvp-reset')) return;
    const btn = document.createElement('button');
    btn.className = 'frvp-reset'; btn.title = 'Reselect FRVP range';
    btn.style.cssText = 'position:absolute;top:6px;left:8px;z-index:10;font-size:9px;padding:2px 7px;min-height:20px;background:rgba(53,194,193,.13);border:1px solid rgba(53,194,193,.35);color:var(--primary);border-radius:3px;cursor:pointer;';
    btn.textContent = '⟳ Reselect';
    wrap.appendChild(btn);
    btn.addEventListener('click', () => {
      ps.frvpRange = null; ps._frvpStep = 0; tempStart = null;
      saveState(); btn.remove(); drawFRVP();
      chart.subscribeClick(frvpClickHandler);
      inst.frvpClickHandler = frvpClickHandler;
    });
  };

  const frvpClickHandler = (param) => {
    if (!param || param.time == null) return;
    const t = Number(param.time);
    if (!Number.isFinite(t)) return;
    if (ps._frvpStep === 0) { tempStart = t; ps._frvpStep = 1; drawFRVP(); }
    else if (ps._frvpStep === 1) {
      ps.frvpRange = { startTime: Math.min(tempStart, t), endTime: Math.max(tempStart, t) };
      ps._frvpStep = 2;
      try { chart.unsubscribeClick(frvpClickHandler); } catch {} inst.frvpClickHandler = null;
      saveState(); drawFRVP(); showResetBtn();
    }
  };

  if (!ps.frvpRange) { chart.subscribeClick(frvpClickHandler); inst.frvpClickHandler = frvpClickHandler; }
  requestAnimationFrame(() => { drawFRVP(); if (ps.frvpRange) showResetBtn(); });
  chart.timeScale().subscribeVisibleLogicalRangeChange(drawFRVP);
  chart.subscribeCrosshairMove(drawFRVP);
  inst.frvpDraw = drawFRVP;
}

function _renderSubPanels(inst, chart, data, ps, pane, paneId, active) {
  const subPanels = pane.querySelector('.sub-panels');
  const SUB_INDS = [
    { id: 'volume', label: 'Volume' }, { id: 'obv',     label: 'OBV' },
    { id: 'mfi',    label: 'MFI (14)' }, { id: 'rsi',    label: 'RSI (14)' },
    { id: 'macd',   label: 'MACD' },     { id: 'stoch',  label: 'Stochastic' },
    { id: 'cci',    label: 'CCI (20)' }, { id: 'williams',label: 'Williams %R' },
    { id: 'atr',    label: 'ATR (14)' }, { id: 'adx',    label: 'ADX (14)' },
  ];
  const C = (id, fb) => (ps.indColors && ps.indColors[id]) || fb;
  const PSW = 70;
  const lwcSubOpts = () => ({
    ...lwcOpts(),
    width: 400, height: 140,
    rightPriceScale: { scaleMargins: { top: 0.1, bottom: 0.1 }, borderColor: '#283348', minimumWidth: PSW },
    leftPriceScale: { visible: false },
    timeScale: { visible: false },
    crosshair: { mode: 0 },
    handleScroll: false, handleScale: false,
    overlayPriceScales: { minimumWidth: PSW },
  });

  SUB_INDS.forEach(({ id, label }) => {
    if (!active[id]) return;
    const panel = document.createElement('div');
    panel.className = 'sub-panel';
    const lbl = document.createElement('div');
    lbl.className = 'sub-label'; lbl.textContent = label;
    const el = document.createElement('div');
    el.className = 'sub-el';
    panel.appendChild(lbl); panel.appendChild(el);
    subPanels.appendChild(panel);

    const subChart = LightweightCharts.createChart(el, lwcSubOpts());
    requestAnimationFrame(() => {
      try {
        const chartEl = pane.querySelector('.chart-el');
        const scaleEl = chartEl && chartEl.querySelector('tr>td:last-child');
        const w = Math.max(scaleEl ? scaleEl.offsetWidth : PSW, PSW);
        chart.applyOptions({ rightPriceScale: { minimumWidth: w } });
        subChart.applyOptions({ rightPriceScale: { minimumWidth: w } });
      } catch {}
    });

    let subDataLen = data.length, updateLabel = null, recalcFn = null;

    if (id === 'volume') {
      const vd = data.map(d => ({ time: d.time, value: d.volume, color: d.close >= d.open ? 'rgba(22,199,132,.7)' : 'rgba(234,57,67,.7)' }));
      subDataLen = vd.length;
      const s = subChart.addHistogramSeries({ color: '#35c2c1', priceFormat: { type: 'volume' }, priceScaleId: '' });
      s.setData(vd);
      let volMap = new Map(vd.map(d => [d.time, d.value])), latestVol = vd.length ? vd[vd.length - 1].value : null;
      const fmtVol = v => v == null ? '--' : v >= 1e9 ? (v / 1e9).toFixed(2) + 'B' : v >= 1e6 ? (v / 1e6).toFixed(2) + 'M' : v >= 1e3 ? (v / 1e3).toFixed(2) + 'K' : v.toFixed(0);
      const setLabel = v => { lbl.innerHTML = `Volume${v == null ? '' : ` <span style="color:#35c2c1;font-weight:700">${fmtVol(v)}</span>`}`; };
      setLabel(latestVol);
      updateLabel = time => { if (time == null) { setLabel(latestVol); return; } const val = volMap.get(time); if (val != null) setLabel(val); };
      recalcFn = () => { const nv = data.map(d => ({ time: d.time, value: d.volume, color: d.close >= d.open ? 'rgba(22,199,132,.7)' : 'rgba(234,57,67,.7)' })); s.setData(nv); volMap = new Map(nv.map(d => [d.time, d.value])); latestVol = nv.length ? nv[nv.length - 1].value : null; setLabel(latestVol); };
    } else if (id === 'obv') {
      const obvData = calcOBV(data); subDataLen = obvData.length;
      const s = subChart.addLineSeries({ color: C('obv', '#35c2c1'), lineWidth: 1, priceLineVisible: false, lastValueVisible: false, priceFormat: { type: 'volume' } });
      s.setData(obvData);
      let obvMap = new Map(obvData.map(d => [d.time, d.value])), latestOBV = obvData.length ? obvData[obvData.length - 1].value : null;
      const fmtObv = v => v == null ? '--' : v >= 1e9 ? (v / 1e9).toFixed(2) + 'B' : v >= 1e6 ? (v / 1e6).toFixed(2) + 'M' : v >= 1e3 ? (v / 1e3).toFixed(2) + 'K' : v.toFixed(0);
      const setLabel = v => { lbl.innerHTML = `OBV${v == null ? '' : ` <span style="color:#35c2c1;font-weight:700">${fmtObv(v)}</span>`}`; };
      setLabel(latestOBV);
      updateLabel = time => { if (time == null) { setLabel(latestOBV); return; } const val = obvMap.get(time); if (val != null) setLabel(val); };
      recalcFn = () => { const nd = calcOBV(data); s.setData(nd); obvMap = new Map(nd.map(d => [d.time, d.value])); latestOBV = nd.length ? nd[nd.length - 1].value : null; setLabel(latestOBV); };
    } else if (id === 'mfi') {
      const mfiData = calcMFI(data); subDataLen = mfiData.length;
      const s = subChart.addLineSeries({ color: C('mfi', '#a78bfa'), lineWidth: 1, priceLineVisible: false, lastValueVisible: false });
      s.setData(mfiData);
      let mfiMap = new Map(mfiData.map(d => [d.time, d.value])), latestMFI = mfiData.length ? mfiData[mfiData.length - 1].value : null;
      const mfiColor = v => v > 80 ? '#ea3943' : v < 20 ? '#16c784' : '#a78bfa';
      const setLabel = v => { lbl.innerHTML = v == null ? 'MFI (14)' : `MFI (14) <span style="color:${mfiColor(v)};font-weight:700">${v.toFixed(2)}</span>`; };
      setLabel(latestMFI);
      updateLabel = time => { if (time == null) { setLabel(latestMFI); return; } const val = mfiMap.get(time); if (val != null) setLabel(val); };
      recalcFn = () => { const nd = calcMFI(data); s.setData(nd); mfiMap = new Map(nd.map(d => [d.time, d.value])); latestMFI = nd.length ? nd[nd.length - 1].value : null; setLabel(latestMFI); };
    } else if (id === 'rsi') {
      const rsiData = calcRSI(data); subDataLen = rsiData.length;
      const s = subChart.addLineSeries({ color: C('rsi', '#f7c948'), lineWidth: 1, priceLineVisible: false, lastValueVisible: false });
      s.setData(rsiData);
      s.createPriceLine({ price: 70, color: 'rgba(234,57,67,.5)', lineWidth: 1, lineStyle: LightweightCharts.LineStyle.Dashed, axisLabelVisible: true, title: '' });
      s.createPriceLine({ price: 30, color: 'rgba(22,199,132,.5)', lineWidth: 1, lineStyle: LightweightCharts.LineStyle.Dashed, axisLabelVisible: true, title: '' });
      let rsiMap = new Map(rsiData.map(d => [d.time, d.value])), latestRSI = rsiData.length ? rsiData[rsiData.length - 1].value : null;
      const rsiColor = v => v > 70 ? '#ea3943' : v < 30 ? '#16c784' : '#f7c948';
      const setLabel = v => { lbl.innerHTML = v == null ? 'RSI (14)' : `RSI (14) <span style="color:${rsiColor(v)};font-weight:700">${v.toFixed(2)}</span>`; };
      setLabel(latestRSI);
      updateLabel = time => { if (time == null) { setLabel(latestRSI); return; } const val = rsiMap.get(time); if (val != null) setLabel(val); };
      recalcFn = () => { const nd = calcRSI(data); s.setData(nd); rsiMap = new Map(nd.map(d => [d.time, d.value])); latestRSI = nd.length ? nd[nd.length - 1].value : null; setLabel(latestRSI); };
    } else if (id === 'macd') {
      const md = calcMACD(data); subDataLen = md.length;
      const sh = subChart.addHistogramSeries({ priceLineVisible: false, lastValueVisible: false });
      sh.setData(md.map(d => ({ time: d.time, value: d.hist, color: d.hist >= 0 ? 'rgba(22,199,132,.7)' : 'rgba(234,57,67,.7)' })));
      const sm = subChart.addLineSeries({ color: C('macd', '#35c2c1'), lineWidth: 1, priceLineVisible: false, lastValueVisible: false });
      sm.setData(md.map(d => ({ time: d.time, value: d.macd })));
      const ss = subChart.addLineSeries({ color: C('macd', '#f7c948'), lineWidth: 1, priceLineVisible: false, lastValueVisible: false });
      ss.setData(md.map(d => ({ time: d.time, value: d.signal })));
      let macdMap = new Map(md.map(d => [d.time, d])), latestMACD = md.length ? md[md.length - 1] : null;
      const histColor = v => v >= 0 ? '#16c784' : '#ea3943';
      const setLabel = entry => {
        lbl.innerHTML = !entry ? 'MACD' :
          `MACD <span style="color:#35c2c1;font-weight:700">${entry.macd.toFixed(2)}</span>` +
          ` <span style="color:#f7c948;font-size:9px">SIG</span> <span style="color:#f7c948;font-weight:700">${entry.signal.toFixed(2)}</span>` +
          ` <span style="color:${histColor(entry.hist)};font-weight:700">${entry.hist >= 0 ? '+' : ''}${entry.hist.toFixed(2)}</span>`;
      };
      setLabel(latestMACD);
      updateLabel = time => { if (time == null) { setLabel(latestMACD); return; } const e = macdMap.get(time); if (e != null) setLabel(e); };
      recalcFn = () => { const nd = calcMACD(data); sh.setData(nd.map(d => ({ time: d.time, value: d.hist, color: d.hist >= 0 ? 'rgba(22,199,132,.7)' : 'rgba(234,57,67,.7)' }))); sm.setData(nd.map(d => ({ time: d.time, value: d.macd }))); ss.setData(nd.map(d => ({ time: d.time, value: d.signal }))); macdMap = new Map(nd.map(d => [d.time, d])); latestMACD = nd.length ? nd[nd.length - 1] : null; setLabel(latestMACD); };
    } else if (id === 'stoch') {
      const st = calcStoch(data); subDataLen = st.length;
      const sk = subChart.addLineSeries({ color: '#35c2c1', lineWidth: 1, priceLineVisible: false, lastValueVisible: false });
      sk.setData(st.map(d => ({ time: d.time, value: d.k })));
      const sd = subChart.addLineSeries({ color: '#f7c948', lineWidth: 1, priceLineVisible: false, lastValueVisible: false });
      sd.setData(st.map(d => ({ time: d.time, value: d.d })));
      let stochMap = new Map(st.map(d => [d.time, d])), latestStoch = st.length ? st[st.length - 1] : null;
      const stochColor = v => v > 80 ? '#ea3943' : v < 20 ? '#16c784' : '#35c2c1';
      const setLabel = entry => { lbl.innerHTML = !entry ? 'Stochastic' : `Stoch <span style="color:${stochColor(entry.k)};font-weight:700">K ${entry.k.toFixed(1)}</span> <span style="color:#f7c948;font-weight:700">D ${entry.d.toFixed(1)}</span>`; };
      setLabel(latestStoch);
      updateLabel = time => { if (time == null) { setLabel(latestStoch); return; } const e = stochMap.get(time); if (e != null) setLabel(e); };
      recalcFn = () => { const nd = calcStoch(data); sk.setData(nd.map(d => ({ time: d.time, value: d.k }))); sd.setData(nd.map(d => ({ time: d.time, value: d.d }))); stochMap = new Map(nd.map(d => [d.time, d])); latestStoch = nd.length ? nd[nd.length - 1] : null; setLabel(latestStoch); };
    } else if (id === 'cci') {
      const cciData = calcCCI(data); subDataLen = cciData.length;
      const s = subChart.addLineSeries({ color: C('cci', '#f97316'), lineWidth: 1, priceLineVisible: false, lastValueVisible: false });
      s.setData(cciData);
      let cciMap = new Map(cciData.map(d => [d.time, d.value])), latestCCI = cciData.length ? cciData[cciData.length - 1].value : null;
      const cciColor = v => v > 100 ? '#ea3943' : v < -100 ? '#16c784' : '#f97316';
      const setLabel = v => { lbl.innerHTML = v == null ? 'CCI (20)' : `CCI (20) <span style="color:${cciColor(v)};font-weight:700">${v.toFixed(1)}</span>`; };
      setLabel(latestCCI);
      updateLabel = time => { if (time == null) { setLabel(latestCCI); return; } const val = cciMap.get(time); if (val != null) setLabel(val); };
      recalcFn = () => { const nd = calcCCI(data); s.setData(nd); cciMap = new Map(nd.map(d => [d.time, d.value])); latestCCI = nd.length ? nd[nd.length - 1].value : null; setLabel(latestCCI); };
    } else if (id === 'williams') {
      const wrData = calcWilliamsR(data); subDataLen = wrData.length;
      const s = subChart.addLineSeries({ color: C('williams', '#a78bfa'), lineWidth: 1, priceLineVisible: false, lastValueVisible: false });
      s.setData(wrData);
      let wrMap = new Map(wrData.map(d => [d.time, d.value])), latestWR = wrData.length ? wrData[wrData.length - 1].value : null;
      const wrColor = v => v > -20 ? '#ea3943' : v < -80 ? '#16c784' : '#a78bfa';
      const setLabel = v => { lbl.innerHTML = v == null ? 'Williams %R (14)' : `%R (14) <span style="color:${wrColor(v)};font-weight:700">${v.toFixed(1)}</span>`; };
      setLabel(latestWR);
      updateLabel = time => { if (time == null) { setLabel(latestWR); return; } const val = wrMap.get(time); if (val != null) setLabel(val); };
      recalcFn = () => { const nd = calcWilliamsR(data); s.setData(nd); wrMap = new Map(nd.map(d => [d.time, d.value])); latestWR = nd.length ? nd[nd.length - 1].value : null; setLabel(latestWR); };
    } else if (id === 'atr') {
      const atrData = calcATR(data); subDataLen = atrData.length;
      const s = subChart.addLineSeries({ color: C('atr', '#f7c948'), lineWidth: 1, priceLineVisible: false, lastValueVisible: false });
      s.setData(atrData);
      let atrMap = new Map(atrData.map(d => [d.time, d.value])), latestATR = atrData.length ? atrData[atrData.length - 1].value : null;
      const setLabel = v => { lbl.innerHTML = v == null ? 'ATR (14)' : `ATR (14) <span style="color:#f7c948;font-weight:700">${v.toFixed(4)}</span>`; };
      setLabel(latestATR);
      updateLabel = time => { if (time == null) { setLabel(latestATR); return; } const val = atrMap.get(time); if (val != null) setLabel(val); };
      recalcFn = () => { const nd = calcATR(data); s.setData(nd); atrMap = new Map(nd.map(d => [d.time, d.value])); latestATR = nd.length ? nd[nd.length - 1].value : null; setLabel(latestATR); };
    } else if (id === 'adx') {
      const ad = calcADX(data); subDataLen = ad.length;
      const s = subChart.addLineSeries({ color: C('adx', '#35c2c1'), lineWidth: 1, priceLineVisible: false, lastValueVisible: false });
      s.setData(ad.map(d => ({ time: d.time, value: d.value })));
      const adxMap = new Map(ad.map(d => [d.time, d])), latestADX = ad.length ? ad[ad.length - 1] : null;
      const adxStrColor = v => v >= 25 ? '#16c784' : v >= 20 ? '#f7c948' : '#9aa8c7';
      const setLabel = entry => {
        lbl.innerHTML = !entry ? 'ADX (14)' :
          `ADX (14) <span style="color:${adxStrColor(entry.value)};font-weight:700">${entry.value.toFixed(1)}</span>` +
          ` <span style="color:#16c784;font-size:9px">+DI</span> <span style="color:#16c784;font-weight:700">${entry.pdi.toFixed(1)}</span>` +
          ` <span style="color:#ea3943;font-size:9px">-DI</span> <span style="color:#ea3943;font-weight:700">${entry.ndi.toFixed(1)}</span>`;
      };
      setLabel(latestADX);
      updateLabel = time => { if (time == null) { setLabel(latestADX); return; } const e = adxMap.get(time); if (e != null) setLabel(e); };
    }

    // Sync time range & crosshair with main chart
    const indOffset = data.length - subDataLen;
    const syncRange = () => {
      try {
        const range = chart.timeScale().getVisibleLogicalRange();
        if (range) subChart.timeScale().setVisibleLogicalRange({ from: range.from - indOffset, to: range.to - indOffset });
        subChart.resize(el.clientWidth || 400, 140);
      } catch {}
    };
    syncRange();
    chart.timeScale().subscribeVisibleLogicalRangeChange(syncRange);
    const syncCrosshair = (param) => {
      try {
        if (!param || !param.time) { subChart.clearCrosshairPosition(); if (updateLabel) updateLabel(null); return; }
        const price = subChart.priceScale('right').coordinateToPrice(param.point?.y ?? 0);
        subChart.setCrosshairPosition(price, param.time, subChart.getSeries()[0] || null);
        if (updateLabel) updateLabel(param.time);
      } catch {}
    };
    chart.subscribeCrosshairMove(syncCrosshair);
    if (!inst.syncFns) inst.syncFns = [];
    inst.syncFns.push({ chart: subChart, rangeFn: syncRange, crossFn: syncCrosshair });
  });
}
