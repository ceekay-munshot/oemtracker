// tabs/common.js — helpers shared across tabs: entity resolution, stat tiles, and the
// period × OEM trend table (with recomputed share + YoY).

import { freqBlock, metricBlock, toYoY, denomSeries, toShare, latestStat } from '../compute.js';
import { fmtInt, fmtPct, fmtDelta, fmtPP, periodLabel, periodLabelLong, priorYearKey } from '../format.js';
import { el } from '../ui.js';
import { colorAt } from '../charts.js';

export function selEntities(ds, state) {
  const map = new Map(ds.entities.map((e) => [e.id, e]));
  return state.entities.map((id) => map.get(id)).filter(Boolean);
}
export function metricLabel(ds, metric) {
  const m = (ds.metrics || []).find((x) => x.id === metric);
  return m ? m.label : (metric || '');
}
export function provSet(ds, freq) { return new Set((ds.provisional && ds.provisional[freq]) || []); }

// Colored delta node (YoY etc.).
export function deltaNode(v, unit = '%') {
  if (v == null || Number.isNaN(v)) return el('span', { class: 'na', text: '—' });
  const cls = v > 0 ? 'delta-up' : (v < 0 ? 'delta-down' : '');
  const arrow = v > 0 ? '▲' : (v < 0 ? '▼' : '·');
  const txt = unit === 'pp' ? fmtPP(v) : fmtDelta(v, 1, unit);
  return el('span', { class: cls, text: `${arrow} ${txt.replace(/^[+−]/, '')}` });
}

// Stat tile.
export function statTile(label, valueStr, delta, sub) {
  const tile = el('div', { class: 'tile' });
  tile.appendChild(el('div', { class: 'tl', text: label }));
  tile.appendChild(el('div', { class: 'tv', text: valueStr }));
  if (delta) {
    const d = el('div', { class: 'td' });
    d.appendChild(delta);
    tile.appendChild(d);
  }
  if (sub) tile.appendChild(el('div', { class: 'ts', text: sub }));
  return tile;
}

// Fiscal-year-to-date stat for the industry/total of a metric.
export function fytdStat(ds, metric) {
  const base = ds.frequencies[0];
  const blk = freqBlock(ds, base);
  const mb = metricBlock(ds, base, metric);
  if (!blk || !mb) return null;
  const periods = blk.periods;
  const vals = mb.industry && mb.industry.some((v) => v != null) ? mb.industry : denomSeries(mb.entities, periods.length);
  // find latest FY
  const fyOf = (k) => {
    if (base === 'monthly') { const m = /^(\d{4})-(\d{2})$/.exec(k); if (m) return (+m[2] >= 4 ? +m[1] + 1 : +m[1]); }
    if (base === 'quarterly') { const m = /^Q\dFY(\d{2})$/.exec(k); if (m) return 2000 + +m[1]; }
    return null;
  };
  let li = -1; for (let i = vals.length - 1; i >= 0; i--) { if (vals[i] != null) { li = i; break; } }
  if (li < 0) return null;
  const curFy = fyOf(periods[li]);
  if (curFy == null) return null;
  const curIdx = []; for (let i = 0; i <= li; i++) if (fyOf(periods[i]) === curFy) curIdx.push(i);
  const priorIdx = curIdx.map((i) => i - (base === 'monthly' ? 12 : 4)).filter((i) => i >= 0);
  const sum = (idxs) => idxs.reduce((a, i) => a + (vals[i] || 0), 0);
  const cur = sum(curIdx);
  const prior = priorIdx.length === curIdx.length ? sum(priorIdx) : null;
  const yoy = (prior && prior > 0) ? (cur / prior - 1) * 100 : null;
  return { value: cur, yoy, fy: curFy, nPeriods: curIdx.length };
}

// Market leader (latest period) for a metric.
export function leaderStat(ds, metric) {
  const base = ds.frequencies[0];
  const blk = freqBlock(ds, base);
  const mb = metricBlock(ds, base, metric);
  if (!blk || !mb) return null;
  const n = blk.periods.length;
  const denom = denomSeries(mb.entities, n);
  let li = -1; for (let i = n - 1; i >= 0; i--) { if (denom[i] != null) { li = i; break; } }
  if (li < 0) return null;
  let best = null;
  for (const e of ds.entities) {
    const arr = mb.entities[e.id];
    const v = arr ? arr[li] : null;
    if (v == null) continue;
    if (!best || v > best.v) best = { id: e.id, name: e.name, v };
  }
  if (!best) return null;
  best.share = denom[li] ? (best.v / denom[li]) * 100 : null;
  best.period = blk.periods[li];
  return best;
}

// Build the period × OEM table spec for TrendCard. Columns = last `nCols` periods (absolute),
// plus recomputed YoY% and latest market-share%. Rows = selected OEMs, sorted by latest value.
export function periodTable(ds, { metric, freq, entities, nCols = 6 }) {
  const blk = freqBlock(ds, freq);
  const mb = metricBlock(ds, freq, metric);
  if (!blk || !mb) return null;
  const periods = blk.periods;
  const n = periods.length;
  const prov = provSet(ds, freq);
  const start = Math.max(0, n - nCols);
  const cols = [];
  for (let i = start; i < n; i++) cols.push({ idx: i, key: periods[i] });
  const denom = denomSeries(mb.entities, n);
  const li = n - 1;

  const rows = entities.map((e) => {
    const arr = mb.entities[e.id] || [];
    const row = { id: e.id, name: e.name };
    for (const c of cols) row['p_' + c.idx] = arr[c.idx];
    row.latest = arr[li];
    // YoY latest vs prior-year period
    const pk = priorYearKey(periods[li], freq);
    const pi = pk ? periods.indexOf(pk) : -1;
    row.yoy = (pi >= 0 && arr[li] != null && arr[pi] != null && arr[pi] > 0) ? (arr[li] / arr[pi] - 1) * 100 : null;
    row.share = (arr[li] != null && denom[li]) ? (arr[li] / denom[li]) * 100 : null;
    return row;
  });

  const columns = [];
  columns.push({
    key: 'name', label: 'OEM', align: 'left', sortVal: (r) => r.name,
    fmt: (v, r) => {
      const rank = rowRank(rows, r);
      const pill = el('span', { class: 'rank-pill' + (rank <= 3 ? ' top' : ''), text: String(rank) });
      const dot = el('span', { class: 'sw-dot', style: { background: colorAt(entities.findIndex((x) => x.id === r.id)) } });
      const nm = el('span', { text: r.name });
      const frag = el('span', {}, [pill, dot, nm]);
      return frag;
    },
    exportVal: (r) => r.name,
  });
  for (const c of cols) {
    columns.push({
      key: 'p_' + c.idx, label: periodLabel(c.key, freq) + (prov.has(c.key) ? ' ◐' : ''),
      align: 'right', sortVal: (r) => r['p_' + c.idx],
      fmt: (v) => v == null ? '<span class="na">—</span>' : fmtInt(v),
      exportVal: (r) => (r['p_' + c.idx] == null ? '' : r['p_' + c.idx]),
    });
  }
  columns.push({
    key: 'yoy', label: 'YoY %', align: 'right', sortVal: (r) => r.yoy,
    fmt: (v) => { const node = deltaNode(v, '%'); return node; },
    exportVal: (r) => (r.yoy == null ? '' : +r.yoy.toFixed(1)),
  });
  columns.push({
    key: 'share', label: 'Share %', align: 'right', sortVal: (r) => r.share,
    fmt: (v) => v == null ? '<span class="na">—</span>' : fmtPct(v, 1),
    exportVal: (r) => (r.share == null ? '' : +r.share.toFixed(2)),
  });

  return { columns, rows, sortKey: 'latest', sortDir: 'desc', initialShow: 10,
    // sort by latest even though it's not a column: expose a hidden sortVal via 'share'? use latest
    sortKeyResolved: 'latest' };
}

function rowRank(rows, r) {
  const sorted = rows.slice().sort((a, b) => (b.latest == null ? -Infinity : b.latest) - (a.latest == null ? -Infinity : a.latest));
  return sorted.findIndex((x) => x.id === r.id) + 1;
}

// Frequency display label.
export function freqLabel(freq) {
  return { monthly: 'Monthly', quarterly: 'Quarterly', yearly: 'Yearly (FY)' }[freq] || freq;
}

// Build an array-of-arrays for Excel export from a set of series aligned to periods.
export function seriesAoa(periods, freq, seriesArr) {
  const header = ['Period', ...seriesArr.map((s) => s.name)];
  const rows = periods.map((k, i) => [periodLabelLong(k, freq), ...seriesArr.map((s) => (s.values[i] == null ? '' : s.values[i]))]);
  return [header, ...rows];
}

// Section title element.
export function sectionTitle(text) { return el('div', { class: 'section-title', text }); }
