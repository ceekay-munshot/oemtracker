// compute.js — derive YoY %, market share, share-delta (pp), rebase-100 and range slices
// from the compact absolute series emitted by the pipeline. One source in, one source out —
// nothing here ever mixes datasets.

import { priorYearKey } from './format.js';

export function freqBlock(ds, freq) {
  return (ds.series && ds.series[freq]) || null;
}

// Resolve a metric block, falling back to the dataset default / first available.
export function metricBlock(ds, freq, metric) {
  const blk = freqBlock(ds, freq);
  if (!blk) return null;
  const m = blk.metrics;
  return m[metric] || m[ds.default_metric] || m[Object.keys(m)[0]] || null;
}

// Index of the first visible period for a range preset ('1y','3y','5y','max').
export function rangeStart(periods, freq, range) {
  if (range === 'max' || !periods.length) return 0;
  const yrs = { '1y': 1, '3y': 3, '5y': 5 }[range] || 5;
  let count;
  if (freq === 'monthly') count = yrs * 12;
  else if (freq === 'quarterly') count = yrs * 4;
  else count = yrs; // yearly
  return Math.max(0, periods.length - count);
}

// YoY % array (same period one fiscal year prior). null where prior missing or non-positive.
export function toYoY(values, periods, freq) {
  const idx = new Map(periods.map((k, i) => [k, i]));
  return values.map((v, i) => {
    const pk = priorYearKey(periods[i], freq);
    if (pk == null || !idx.has(pk)) return null;
    const prev = values[idx.get(pk)];
    if (v == null || prev == null || prev <= 0) return null;
    return (v / prev - 1) * 100;
  });
}

// Per-period denominator = sum of all entity values present (missing excluded), so recomputed
// shares are internally consistent and sum to 100% across reporting entities.
export function denomSeries(entitiesObj, n) {
  const out = new Array(n).fill(null);
  for (const id in entitiesObj) {
    const arr = entitiesObj[id];
    for (let i = 0; i < n; i++) {
      const v = arr[i];
      if (v != null) out[i] = (out[i] || 0) + v;
    }
  }
  return out;
}

// Share % of one series against a denominator.
export function toShare(values, denom) {
  return values.map((v, i) => (v == null || !denom[i]) ? null : (v / denom[i]) * 100);
}

// YoY change in share, in percentage points.
export function toShareDelta(shareVals, periods, freq) {
  const idx = new Map(periods.map((k, i) => [k, i]));
  return shareVals.map((v, i) => {
    const pk = priorYearKey(periods[i], freq);
    if (pk == null || !idx.has(pk)) return null;
    const prev = shareVals[idx.get(pk)];
    if (v == null || prev == null) return null;
    return v - prev;
  });
}

// Rebase a (already-sliced) series so its first non-null point = 100.
export function rebase100(values) {
  let base = null;
  for (const v of values) { if (v != null && v > 0) { base = v; break; } }
  if (base == null) return values.map(() => null);
  return values.map((v) => (v == null ? null : (v / base) * 100));
}

// Convenience: build ready-to-plot entity series honouring metric/freq/valueMode/range/rebase.
// Returns { periods, periodsFull, startIdx, partial, series:[{id,name,values}], denomFull }.
export function seriesForEntities(ds, opts) {
  const { metric, freq, valueMode = 'abs', ids = [], range = '5y', rebase = false, names = {} } = opts;
  const blk = freqBlock(ds, freq);
  const mb = metricBlock(ds, freq, metric);
  if (!blk || !mb) return { periods: [], periodsFull: [], startIdx: 0, partial: [], series: [], denomFull: [] };

  const periodsFull = blk.periods;
  const n = periodsFull.length;
  const start = rangeStart(periodsFull, freq, range);
  const denomFull = denomSeries(mb.entities, n);

  const series = ids.map((id) => {
    let vals = mb.entities[id] ? mb.entities[id].slice() : new Array(n).fill(null);
    if (valueMode === 'yoy') vals = toYoY(vals, periodsFull, freq);
    let sliced = vals.slice(start);
    if (rebase && valueMode === 'abs') sliced = rebase100(sliced);
    return { id, name: names[id] || id, values: sliced };
  });

  return {
    periods: periodsFull.slice(start),
    periodsFull,
    startIdx: start,
    partial: (blk.partial || []).slice(start),
    series,
    denomFull,
  };
}

// Industry / category-total series for a metric+freq (absolute or YoY), range-sliced.
export function industrySeries(ds, opts) {
  const { metric, freq, valueMode = 'abs', range = '5y', useEntitySum = false } = opts;
  const blk = freqBlock(ds, freq);
  const mb = metricBlock(ds, freq, metric);
  if (!blk || !mb) return { periods: [], values: [], partial: [] };
  const periodsFull = blk.periods;
  const n = periodsFull.length;
  let full = (useEntitySum || !mb.industry) ? denomSeries(mb.entities, n) : mb.industry.slice();
  if (valueMode === 'yoy') full = toYoY(full, periodsFull, freq);
  const start = rangeStart(periodsFull, freq, range);
  return {
    periods: periodsFull.slice(start),
    values: full.slice(start),
    partial: (blk.partial || []).slice(start),
    periodsFull,
    startIdx: start,
  };
}

// Latest non-null value and its YoY for an entity (or industry) — for stat tiles.
export function latestStat(periodsFull, valuesFull, freq) {
  let li = -1;
  for (let i = valuesFull.length - 1; i >= 0; i--) { if (valuesFull[i] != null) { li = i; break; } }
  if (li < 0) return { value: null, yoy: null, period: null };
  const yoy = toYoY(valuesFull, periodsFull, freq)[li];
  return { value: valuesFull[li], yoy, period: periodsFull[li] };
}
