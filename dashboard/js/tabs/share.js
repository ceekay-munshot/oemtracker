// Market Share — share recomputed from raw (single-sourced, sums to 100% across reporting OEMs).
// Left: 100%-stacked share-over-time (top OEMs + Others). Right: per-OEM share line + a table of
// latest share, year-ago share and the YoY change in share (percentage points).
import { TrendCard, mountCards } from '../trendcard.js';
import { stackedOption, lineOption, colorAt } from '../charts.js';
import { freqBlock, metricBlock, denomSeries, toShare, rangeStart } from '../compute.js';
import { priorYearKey, periodLabel, periodLabelLong, fmtPct } from '../format.js';
import { el, provNote } from '../ui.js';
import { selEntities, metricLabel, provSet, freqLabel, deltaNode } from './common.js';

export function render(root, ctx) {
  const { ds, state } = ctx;
  const { metric, freq, range } = state;
  const prov = provSet(ds, freq);
  const ents = selEntities(ds, state);

  const blk = freqBlock(ds, freq);
  const mb = metricBlock(ds, freq, metric);
  if (!blk || !mb || !ents.length) {
    const c = TrendCard({ title: 'Market share', source: ds.source, option: null,
      emptyTitle: 'No OEMs selected', emptyHint: 'Pick OEMs in the filter bar to see share trends.' });
    const g = el('div', { class: 'grid' }); mountCards(g, [c]); root.appendChild(g); return;
  }
  const periodsFull = blk.periods;
  const n = periodsFull.length;
  const denom = denomSeries(mb.entities, n);
  const start = rangeStart(periodsFull, freq, range);
  const periods = periodsFull.slice(start);
  const visProv = periods.filter((k) => prov.has(k));

  // ---- 100%-stacked share over time (selected OEMs + Others) ----
  const groups = ents.map((e, i) => ({ name: e.name, color: colorAt(i), values: (mb.entities[e.id] || []).slice(start) }));
  const othersFull = periodsFull.map((_, i) => {
    if (denom[i] == null) return null;
    let sel = 0, any = false;
    for (const e of ents) { const v = (mb.entities[e.id] || [])[i]; if (v != null) { sel += v; any = true; } }
    const o = denom[i] - sel;
    return o > 0 ? o : (any ? 0 : null);
  });
  groups.push({ name: 'Others', color: '#cbd0dc', values: othersFull.slice(start) });

  const stackOpt = stackedOption({ periods, freq, groups, percent: true, provisional: prov });
  const stackCard = TrendCard({
    title: `${ds.category_label} — market share over time`,
    subtitle: `100% stacked · recomputed from ${metricLabel(ds, metric)} · ${freqLabel(freq)}`,
    source: ds.source, span: 'span-2', height: 'tall', option: stackOpt,
    note: visProv.length ? provNote(visProv) : null,
    exportName: `${ds.category}_${ds.source}_share_stacked`,
    exportAoa: () => shareStackAoa(periods, freq, groups),
  });

  // ---- per-OEM share lines (share %) ----
  const shareByE = ents.map((e, i) => {
    const sh = toShare(mb.entities[e.id] || [], denom);
    return { id: e.id, name: e.name, color: colorAt(i), full: sh, values: sh.slice(start) };
  });
  const lineOpt = lineOption({
    periods, freq, unit: 'pct',
    series: shareByE.map((s) => ({ name: s.name, values: s.values, color: s.color })),
    provisional: prov,
  });
  const lineCard = TrendCard({
    title: 'OEM share trend',
    subtitle: `Each OEM's share of ${metricLabel(ds, metric)} · ${freqLabel(freq)}`,
    source: ds.source, span: 'span-2', height: 'tall', option: lineOpt,
    exportName: `${ds.category}_${ds.source}_share_lines`,
    exportAoa: () => shareLinesAoa(periods, freq, shareByE),
  });

  // ---- share-delta table (pp) ----
  const li = n - 1;
  const pk = priorYearKey(periodsFull[li], freq);
  const pi = pk ? periodsFull.indexOf(pk) : -1;
  const rows = shareByE.map((s) => {
    const latest = s.full[li];
    const prior = pi >= 0 ? s.full[pi] : null;
    const delta = (latest != null && prior != null) ? latest - prior : null;
    return { id: s.id, name: s.name, color: s.color, latest, prior, delta };
  });
  const columns = [
    { key: 'name', label: 'OEM', align: 'left', sortVal: (r) => r.name,
      fmt: (v, r) => el('span', {}, [el('span', { class: 'sw-dot', style: { background: r.color } }), el('span', { text: r.name })]),
      exportVal: (r) => r.name },
    { key: 'latest', label: `Share ${periodLabel(periodsFull[li], freq)}`, align: 'right', sortVal: (r) => r.latest,
      fmt: (v) => v == null ? '<span class="na">—</span>' : fmtPct(v, 2), exportVal: (r) => (r.latest == null ? '' : +r.latest.toFixed(2)) },
    { key: 'prior', label: pk ? `Share ${periodLabel(pk, freq)}` : 'Yr ago', align: 'right', sortVal: (r) => r.prior,
      fmt: (v) => v == null ? '<span class="na">—</span>' : fmtPct(v, 2), exportVal: (r) => (r.prior == null ? '' : +r.prior.toFixed(2)) },
    { key: 'delta', label: 'Δ share (pp)', align: 'right', sortVal: (r) => r.delta,
      fmt: (v) => deltaNode(v, 'pp'), exportVal: (r) => (r.delta == null ? '' : +r.delta.toFixed(2)) },
  ];
  const deltaCard = TrendCard({
    title: 'Share moves — year on year',
    subtitle: `Change in market share, latest vs one year prior (percentage points)`,
    source: ds.source, span: 'span-2',
    table: { columns, rows, sortKey: 'latest', sortDir: 'desc', initialShow: 12 },
    exportName: `${ds.category}_${ds.source}_share_delta`,
  });

  const grid = el('div', { class: 'grid' });
  mountCards(grid, [stackCard, lineCard, deltaCard]);
  root.appendChild(grid);
}

function shareStackAoa(periods, freq, groups) {
  const header = ['Period', ...groups.map((g) => g.name + ' (share %)')];
  const rows = periods.map((k, i) => {
    let sum = 0; for (const g of groups) sum += (g.values[i] || 0);
    return [periodLabelLong(k, freq), ...groups.map((g) => (g.values[i] == null || !sum ? '' : +((g.values[i] / sum) * 100).toFixed(2)))];
  });
  return [header, ...rows];
}
function shareLinesAoa(periods, freq, shareByE) {
  const header = ['Period', ...shareByE.map((s) => s.name + ' (share %)')];
  const rows = periods.map((k, i) => [periodLabelLong(k, freq), ...shareByE.map((s) => (s.values[i] == null ? '' : +s.values[i].toFixed(2)))]);
  return [header, ...rows];
}
