// Segment Mix — segment splits over time (stacked-area absolute) plus share-of-mix (100%).
//   2W → Scooter / Motorcycle / Moped ; PV → PC / UV / Vans ; 3W → Passenger / Goods
//   CV → M&HCV/LCV × Passenger/Goods ; Tractors → HP bands.  (Internal DB.)
import { TrendCard, mountCards } from '../trendcard.js';
import { stackedOption, colorAt } from '../charts.js';
import { rangeStart } from '../compute.js';
import { periodLabelLong, periodLabel, fmtPct } from '../format.js';
import { el, provNote } from '../ui.js';
import { provSet, freqLabel, deltaNode } from './common.js';

export function render(root, ctx) {
  const { ds, state } = ctx;

  if (!ds.segments) {
    const c = TrendCard({ title: 'Segment Mix', source: ds.source, option: null,
      emptyTitle: 'No segment breakdown for this selection',
      emptyHint: 'Segment mix (body-type / class / HP band) is available on the Internal DB source. Switch source in the filter bar.' });
    const g = el('div', { class: 'grid' }); mountCards(g, [c]); root.appendChild(g); return;
  }

  const freq = ds.segments[state.freq] ? state.freq : ds.frequencies[0];
  const seg = ds.segments[freq];
  const prov = provSet(ds, freq);
  const periodsFull = seg.periods;
  const start = rangeStart(periodsFull, freq, state.range);
  const periods = periodsFull.slice(start);
  const visProv = periods.filter((k) => prov.has(k));

  const groups = seg.groups.map((g, i) => ({ name: g.label, color: colorAt(i), ev: g.ev, values: g.values.slice(start), full: g.values }));

  const absOpt = stackedOption({ periods, freq, unit: 'num', groups, provisional: prov });
  const absCard = TrendCard({
    title: `${ds.category_label} — segment volume`,
    subtitle: `Stacked segments · ${freqLabel(freq)} · absolute`,
    source: ds.source, span: 'span-2', height: 'tall', option: absOpt,
    note: visProv.length ? provNote(visProv) : null,
    exportName: `${ds.category}_segment_volume`,
    exportAoa: () => segAoa(periods, freq, groups),
  });

  const pctOpt = stackedOption({ periods, freq, groups, percent: true, provisional: prov });
  const pctCard = TrendCard({
    title: 'Share of segment mix',
    subtitle: `100% stacked · how the mix shifts over time · ${freqLabel(freq)}`,
    source: ds.source, span: 'span-2', height: 'tall', option: pctOpt,
    exportName: `${ds.category}_segment_share`,
    exportAoa: () => segShareAoa(periods, freq, groups),
  });

  // ---- segment table: latest value, share, YoY delta pp ----
  const n = periodsFull.length;
  const li = n - 1;
  const step = freq === 'monthly' ? 12 : (freq === 'quarterly' ? 4 : 1);
  const totLatest = seg.groups.reduce((a, g) => a + (g.values[li] || 0), 0);
  const totPrev = seg.groups.reduce((a, g) => a + (g.values[li - step] || 0), 0);
  const rows = seg.groups.map((g, i) => {
    const latest = g.values[li];
    const share = totLatest ? (latest / totLatest) * 100 : null;
    const prevShare = (li - step >= 0 && totPrev) ? ((g.values[li - step] || 0) / totPrev) * 100 : null;
    return { name: g.label, color: colorAt(i), latest, share, delta: (share != null && prevShare != null) ? share - prevShare : null };
  });
  const columns = [
    { key: 'name', label: 'Segment', align: 'left', sortVal: (r) => r.name,
      fmt: (v, r) => el('span', {}, [el('span', { class: 'sw-dot', style: { background: r.color } }), el('span', { text: r.name })]), exportVal: (r) => r.name },
    { key: 'latest', label: `Volume ${periodLabel(periodsFull[li], freq)}`, align: 'right', sortVal: (r) => r.latest,
      fmt: (v) => v == null ? '<span class="na">—</span>' : new Intl.NumberFormat('en-IN').format(v), exportVal: (r) => r.latest ?? '' },
    { key: 'share', label: 'Mix %', align: 'right', sortVal: (r) => r.share,
      fmt: (v) => v == null ? '—' : fmtPct(v, 1), exportVal: (r) => (r.share == null ? '' : +r.share.toFixed(2)) },
    { key: 'delta', label: 'Δ mix (pp, YoY)', align: 'right', sortVal: (r) => r.delta,
      fmt: (v) => deltaNode(v, 'pp'), exportVal: (r) => (r.delta == null ? '' : +r.delta.toFixed(2)) },
  ];
  const tableCard = TrendCard({
    title: 'Segment shares — latest & YoY move',
    subtitle: 'Mix share of each segment and its year-on-year change (pp)',
    source: ds.source, span: 'span-2',
    table: { columns, rows, sortKey: 'latest', sortDir: 'desc', initialShow: 12 },
    exportName: `${ds.category}_segment_table`,
  });

  const grid = el('div', { class: 'grid' });
  mountCards(grid, [absCard, pctCard, tableCard]);
  root.appendChild(grid);
}

function segAoa(periods, freq, groups) {
  return [['Period', ...groups.map((g) => g.name)],
    ...periods.map((k, i) => [periodLabelLong(k, freq), ...groups.map((g) => (g.values[i] == null ? '' : g.values[i]))])];
}
function segShareAoa(periods, freq, groups) {
  return [['Period', ...groups.map((g) => g.name + ' (mix %)')],
    ...periods.map((k, i) => {
      let sum = 0; for (const g of groups) sum += (g.values[i] || 0);
      return [periodLabelLong(k, freq), ...groups.map((g) => (g.values[i] == null || !sum ? '' : +((g.values[i] / sum) * 100).toFixed(2)))];
    })];
}
