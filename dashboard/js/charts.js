// charts.js — ECharts option factories. Every chart in the app is built here so they share
// one visual language: glass tooltips, smooth glowing trend lines with a lit latest-point,
// gradient area/bar fills, clean gridless axes, the indigo/violet palette, and dataZoom on
// long histories.

import { compactNum, fmtInt, fmtPct, periodLabel, periodLabelLong } from './format.js';

const echarts = window.echarts;

export const PALETTE = ['#4f46e5', '#06b6d4', '#10b981', '#f59e0b', '#ec4899',
  '#8b5cf6', '#ef4444', '#14b8a6', '#3b82f6', '#f97316', '#a855f7', '#0ea5e9'];

export function colorAt(i) { return PALETTE[i % PALETTE.length]; }

function hexA(hex, a) {
  const h = hex.replace('#', '');
  const r = parseInt(h.slice(0, 2), 16), g = parseInt(h.slice(2, 4), 16), b = parseInt(h.slice(4, 6), 16);
  return `rgba(${r},${g},${b},${a})`;
}

// --- value formatters per unit -------------------------------------------------------
function axisFmt(unit) {
  if (unit === 'pct') return (v) => (v == null ? '' : v.toFixed(0) + '%');
  if (unit === 'pp') return (v) => (v == null ? '' : (v > 0 ? '+' : '') + v.toFixed(0));
  if (unit === 'index') return (v) => (v == null ? '' : v.toFixed(0));
  return (v) => compactNum(v);
}
function tipFmt(unit) {
  if (unit === 'pct') return (v) => (v == null ? '—' : fmtPct(v, 1));
  if (unit === 'pp') return (v) => (v == null ? '—' : (v > 0 ? '+' : '') + v.toFixed(2) + ' pp');
  if (unit === 'index') return (v) => (v == null ? '—' : v.toFixed(1));
  return (v) => (v == null ? '—' : fmtInt(v));
}

// --- shared option chrome ------------------------------------------------------------
const GLASS = {
  backgroundColor: 'rgba(15,23,42,.94)', borderWidth: 0, borderRadius: 10,
  padding: [9, 12], textStyle: { color: '#fff', fontSize: 12, fontFamily: 'Inter' },
  extraCssText: 'box-shadow:0 12px 32px rgba(15,23,42,.22);backdrop-filter:blur(8px);',
};

function axisPointer() {
  return { type: 'line', lineStyle: { color: '#cbd2dc', width: 1, type: 'dashed' } };
}
function xAxis(labels) {
  return {
    type: 'category', data: labels, boundaryGap: false,
    axisLine: { show: false }, axisTick: { show: false },
    axisLabel: { color: '#94a3b8', fontSize: 10.5, margin: 14, showMaxLabel: true, hideOverlap: true },
    axisPointer: { label: { show: false } },
  };
}
function yAxis(unit, opts = {}) {
  return {
    type: 'value', scale: opts.scale !== false && unit === 'num' ? false : opts.scale === true,
    axisLine: { show: false }, axisTick: { show: false },
    splitLine: { show: true, lineStyle: { color: '#f1f5f9' } },
    axisLabel: { color: '#94a3b8', fontSize: 10.5, margin: 12, formatter: axisFmt(unit) },
    ...(opts.max != null ? { max: opts.max } : {}),
    ...(opts.min != null ? { min: opts.min } : {}),
  };
}
function gridFor(hasZoom) {
  return { left: 10, right: 16, top: 16, bottom: hasZoom ? 42 : 12, containLabel: true };
}
function dataZoom(nPeriods) {
  return [{
    type: 'slider', height: 16, bottom: 10, borderColor: 'transparent',
    backgroundColor: '#eef1f7', fillerColor: 'rgba(79,70,229,.12)',
    handleStyle: { color: '#fff', borderColor: '#4f46e5', borderWidth: 1.5 },
    moveHandleStyle: { color: '#c7cdf5' }, dataBackground: { lineStyle: { color: '#c8d0dc' }, areaStyle: { color: '#e3e6ec' } },
    selectedDataBackground: { lineStyle: { color: '#4f46e5' }, areaStyle: { color: 'rgba(79,70,229,.15)' } },
    textStyle: { color: '#94a3b8', fontSize: 10 }, start: 0, end: 100,
  }, { type: 'inside' }];
}

// Build the tooltip formatter (glass card). `closest` picks the single nearest series to the
// cursor for busy multi-line charts.
function makeFormatter(keys, freq, unit, provisional, getCursorVal, closest) {
  const f = tipFmt(unit);
  const provSet = provisional || new Set();
  return (params) => {
    if (!Array.isArray(params)) params = [params];
    if (!params.length) return '';
    let rows = params;
    if (closest && getCursorVal) {
      const yv = getCursorVal();
      if (yv != null) {
        let best = null, bd = Infinity;
        for (const p of params) {
          const val = Array.isArray(p.value) ? p.value[1] : p.value;
          if (val == null) continue;
          const d = Math.abs(val - yv);
          if (d < bd) { bd = d; best = p; }
        }
        if (best) rows = [best];
      }
    }
    const idx = params[0].dataIndex;
    const key = keys[idx];
    let head = periodLabelLong(key, freq);
    if (provSet.has(key)) head += ' · <span style="color:#fbbf24">provisional</span>';
    let html = `<div style="font-weight:700;margin-bottom:6px;font-size:11.5px">${head}</div>`;
    rows.sort((a, b) => {
      const av = Array.isArray(a.value) ? a.value[1] : a.value;
      const bv = Array.isArray(b.value) ? b.value[1] : b.value;
      return (bv == null ? -Infinity : bv) - (av == null ? -Infinity : av);
    });
    for (const p of rows) {
      const val = Array.isArray(p.value) ? p.value[1] : p.value;
      html += `<div style="display:flex;align-items:center;gap:8px;margin:2px 0;font-size:12px">` +
        `<span style="width:8px;height:8px;border-radius:2px;background:${p.color};display:inline-block"></span>` +
        `<span style="flex:1;color:#cbd5e1">${p.seriesName}</span>` +
        `<span style="font-weight:700;font-variant-numeric:tabular-nums">${f(val)}</span></div>`;
    }
    return html;
  };
}

// --- line / area chart ---------------------------------------------------------------
// cfg: { periods(keys), freq, unit, series:[{name,values,color?}], area, zeroLine, provisional(Set) }
export function lineOption(cfg) {
  const { periods = [], freq = 'monthly', unit = 'num', series = [], area = false, zeroLine = false } = cfg;
  const labels = periods.map((k) => periodLabel(k, freq));
  const hasZoom = periods.length > 40;

  const ecSeries = series.map((s, i) => {
    const color = s.color || colorAt(i);
    // latest lit point
    let li = -1;
    for (let j = s.values.length - 1; j >= 0; j--) { if (s.values[j] != null) { li = j; break; } }
    const mark = li >= 0 ? {
      symbol: 'circle', symbolSize: 8, silent: true,
      data: [{ coord: [li, s.values[li]] }],
      itemStyle: { color: '#fff', borderColor: color, borderWidth: 2.5, shadowColor: hexA(color, .5), shadowBlur: 10 },
      label: { show: false },
    } : undefined;
    return {
      name: s.name, type: 'line', data: s.values, smooth: 0.35, smoothMonotone: 'x',
      showSymbol: false, symbolSize: 6, connectNulls: false,
      lineStyle: { width: 2.4, cap: 'round', join: 'round', color, shadowColor: hexA(color, .28), shadowBlur: 8, shadowOffsetY: 4 },
      itemStyle: { color },
      emphasis: { focus: 'series', lineStyle: { width: 3.1 } },
      ...(area ? {
        areaStyle: {
          color: new echarts.graphic.LinearGradient(0, 0, 0, 1, [
            { offset: 0, color: hexA(color, .20) }, { offset: .6, color: hexA(color, .06) }, { offset: 1, color: hexA(color, 0) },
          ]),
        },
      } : {}),
      ...(mark ? { markPoint: mark } : {}),
    };
  });

  const opt = {
    color: PALETTE,
    grid: gridFor(hasZoom),
    tooltip: { trigger: 'axis', axisPointer: axisPointer(), ...GLASS,
      formatter: makeFormatter(periods, freq, unit, cfg.provisional) },
    xAxis: xAxis(labels),
    yAxis: yAxis(unit, { scale: unit === 'num' }),
    series: ecSeries,
    animationDuration: 620, animationEasing: 'cubicOut',
  };
  if (zeroLine || unit === 'pct' || unit === 'pp') {
    opt.yAxis.splitLine = { show: true, lineStyle: { color: '#f1f5f9' } };
    ecSeries.forEach(() => {});
    opt.series.push({ type: 'line', data: labels.map(() => 0), silent: true, symbol: 'none',
      lineStyle: { color: '#cbd2dc', width: 1, type: 'dashed' }, tooltip: { show: false }, z: 1, name: '__zero' });
  }
  if (hasZoom) opt.dataZoom = dataZoom(periods.length);
  // meta used by TrendCard to wire closest-series tooltip
  opt.__meta = { keys: periods, freq, unit, provisional: cfg.provisional, closestEligible: series.length > 5 };
  return opt;
}

// --- bar chart -----------------------------------------------------------------------
export function barOption(cfg) {
  const { periods = [], freq = 'monthly', unit = 'num', series = [] } = cfg;
  const labels = periods.map((k) => periodLabel(k, freq));
  const hasZoom = periods.length > 40;
  const ecSeries = series.map((s, i) => {
    const color = s.color || colorAt(i);
    return {
      name: s.name, type: 'bar', data: s.values, barMaxWidth: 26,
      itemStyle: {
        borderRadius: [3, 3, 0, 0],
        color: new echarts.graphic.LinearGradient(0, 0, 0, 1, [
          { offset: 0, color: hexA(color, 1) }, { offset: 1, color: hexA(color, .62) },
        ]),
      },
      emphasis: { focus: 'series' },
    };
  });
  const opt = {
    color: PALETTE, grid: gridFor(hasZoom),
    tooltip: { trigger: 'axis', axisPointer: { type: 'shadow', shadowStyle: { color: 'rgba(79,70,229,.06)' } }, ...GLASS,
      formatter: makeFormatter(periods, freq, unit, cfg.provisional) },
    xAxis: xAxis(labels), yAxis: yAxis(unit, { scale: false }),
    series: ecSeries, animationDuration: 560, animationEasing: 'cubicOut',
  };
  if (hasZoom) opt.dataZoom = dataZoom(periods.length);
  opt.__meta = { keys: periods, freq, unit, provisional: cfg.provisional, closestEligible: false };
  return opt;
}

// --- stacked area (segment / share mix), optional 100% ------------------------------
export function stackedOption(cfg) {
  const { periods = [], freq = 'monthly', unit = 'num', groups = [], percent = false } = cfg;
  const labels = periods.map((k) => periodLabel(k, freq));
  const hasZoom = periods.length > 40;

  // For percent mode, normalise each period to 100.
  let data = groups.map((g) => g.values.slice());
  if (percent) {
    const n = labels.length;
    for (let i = 0; i < n; i++) {
      let sum = 0; for (const d of data) sum += (d[i] || 0);
      if (sum > 0) for (const d of data) d[i] = d[i] == null ? null : (d[i] / sum) * 100;
    }
  }
  const ecSeries = groups.map((g, i) => {
    const color = g.color || colorAt(i);
    return {
      name: g.name, type: 'line', stack: 'total', data: data[i], smooth: 0.2, showSymbol: false,
      lineStyle: { width: 1.4, color }, itemStyle: { color },
      areaStyle: { color: hexA(color, percent ? .72 : .5), opacity: 1 },
      emphasis: { focus: 'series' },
    };
  });
  const opt = {
    color: PALETTE, grid: gridFor(hasZoom),
    tooltip: { trigger: 'axis', axisPointer: axisPointer(), ...GLASS,
      formatter: makeFormatter(periods, freq, percent ? 'pct' : unit, cfg.provisional) },
    xAxis: xAxis(labels),
    yAxis: yAxis(percent ? 'pct' : unit, percent ? { max: 100, min: 0 } : { scale: false }),
    series: ecSeries, animationDuration: 620, animationEasing: 'cubicOut',
  };
  if (hasZoom) opt.dataZoom = dataZoom(periods.length);
  opt.__meta = { keys: periods, freq, unit: percent ? 'pct' : unit, provisional: cfg.provisional, closestEligible: false };
  return opt;
}

// --- dual-axis: bars (volume) + line (penetration %) — for EV tracker ---------------
export function comboBarLineOption(cfg) {
  const { periods = [], freq = 'monthly', bars, line } = cfg;
  const labels = periods.map((k) => periodLabel(k, freq));
  const hasZoom = periods.length > 40;
  const barColor = bars.color || '#10b981';
  const lineColor = line.color || '#4f46e5';
  const opt = {
    grid: gridFor(hasZoom),
    tooltip: { trigger: 'axis', axisPointer: { type: 'cross', crossStyle: { color: '#cbd2dc' }, lineStyle: { color: '#cbd2dc', type: 'dashed' } }, ...GLASS,
      formatter: (params) => {
        const idx = params[0].dataIndex;
        let head = periodLabelLong(periods[idx], freq);
        if (cfg.provisional && cfg.provisional.has(periods[idx])) head += ' · <span style="color:#fbbf24">provisional</span>';
        let html = `<div style="font-weight:700;margin-bottom:6px;font-size:11.5px">${head}</div>`;
        for (const p of params) {
          const isPct = p.seriesName === line.name;
          const val = p.value == null ? '—' : (isPct ? fmtPct(p.value, 1) : fmtInt(p.value));
          html += `<div style="display:flex;align-items:center;gap:8px;margin:2px 0;font-size:12px">` +
            `<span style="width:8px;height:8px;border-radius:2px;background:${p.color};display:inline-block"></span>` +
            `<span style="flex:1;color:#cbd5e1">${p.seriesName}</span>` +
            `<span style="font-weight:700;font-variant-numeric:tabular-nums">${val}</span></div>`;
        }
        return html;
      } },
    xAxis: xAxis(labels),
    yAxis: [
      yAxis('num', { scale: false }),
      { type: 'value', min: 0, axisLine: { show: false }, axisTick: { show: false }, splitLine: { show: false },
        axisLabel: { color: '#94a3b8', fontSize: 10.5, margin: 12, formatter: (v) => v.toFixed(0) + '%' } },
    ],
    series: [
      { name: bars.name, type: 'bar', data: bars.values, yAxisIndex: 0, barMaxWidth: 30,
        itemStyle: { borderRadius: [3, 3, 0, 0],
          color: new echarts.graphic.LinearGradient(0, 0, 0, 1, [{ offset: 0, color: hexA(barColor, 1) }, { offset: 1, color: hexA(barColor, .62) }]) } },
      { name: line.name, type: 'line', data: line.values, yAxisIndex: 1, smooth: 0.35, showSymbol: false,
        lineStyle: { width: 2.6, color: lineColor, cap: 'round', shadowColor: hexA(lineColor, .3), shadowBlur: 8, shadowOffsetY: 4 },
        itemStyle: { color: lineColor }, z: 3 },
    ],
    animationDuration: 620,
  };
  if (hasZoom) opt.dataZoom = dataZoom(periods.length);
  opt.__meta = { keys: periods, freq, unit: 'num', provisional: cfg.provisional, closestEligible: false };
  return opt;
}

// Wire the "closest-series" tooltip: on a busy multi-line chart, hovering shows only the line
// nearest the cursor's Y. Called by TrendCard after setOption when meta.closestEligible.
export function enableClosestSeries(chart, dom, meta) {
  if (!meta || !meta.closestEligible) return;
  let cursorVal = null;
  const onMove = (e) => {
    const rect = dom.getBoundingClientRect();
    const y = e.clientY - rect.top;
    try { cursorVal = chart.convertFromPixel({ gridIndex: 0 }, [0, y])[1]; }
    catch (_) { cursorVal = null; }
  };
  dom.addEventListener('mousemove', onMove);
  chart.__onMove = onMove; chart.__moveDom = dom;
  chart.setOption({
    tooltip: { formatter: makeFormatter(meta.keys, meta.freq, meta.unit, meta.provisional, () => cursorVal, true) },
  });
}
