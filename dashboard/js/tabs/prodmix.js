// Production · Sales · Exports — the SIAM metrics on one trend for the selected category
// (or a single selected OEM), plus the domestic-vs-export mix over time. Adapts to the internal
// DB (which carries domestic & exports only).
import { TrendCard, mountCards } from '../trendcard.js';
import { lineOption, stackedOption } from '../charts.js';
import { freqBlock, metricBlock, denomSeries, toYoY, rangeStart } from '../compute.js';
import { periodLabelLong } from '../format.js';
import { el, provNote } from '../ui.js';
import { metricLabel, provSet, freqLabel, seriesAoa } from './common.js';

const METRIC_COLOR = { production: '#8b5cf6', domestic: '#4f46e5', exports: '#06b6d4', total: '#10b981' };

export function render(root, ctx) {
  const { ds, state } = ctx;
  const { freq, valueMode: mode, range } = state;
  const unit = mode === 'yoy' ? 'pct' : 'num';
  const prov = provSet(ds, freq);
  const blk = freqBlock(ds, freq);
  const periodsFull = blk.periods;
  const start = rangeStart(periodsFull, freq, range);
  const periods = periodsFull.slice(start);
  const visProv = periods.filter((k) => prov.has(k));

  const target = state.entities.length === 1 ? ds.entities.find((e) => e.id === state.entities[0]) : null;
  const targetLabel = target ? target.name : `${ds.category_label} (industry)`;

  const tgt = (mb) => target ? (mb.entities[target.id] || []) : ((mb.industry && mb.industry.some((v) => v != null)) ? mb.industry : denomSeries(mb.entities, periodsFull.length));

  // ---- all-metrics line ----
  const metricIds = ds.metrics.map((m) => m.id);
  const series = metricIds.map((mid) => {
    const mb = metricBlock(ds, freq, mid);
    let full = tgt(mb);
    if (mode === 'yoy') full = toYoY(full, periodsFull, freq);
    return { name: metricLabel(ds, mid), values: full.slice(start), color: METRIC_COLOR[mid] };
  });
  const lineOpt = lineOption({ periods, freq, unit, series, provisional: prov, zeroLine: mode === 'yoy' });
  const lineCard = TrendCard({
    title: `${targetLabel} — production · sales · exports`,
    subtitle: `${ds.source === 'siam' ? 'Production, Domestic, Exports, Total' : 'Domestic & Exports'} · ${freqLabel(freq)} · ${mode === 'yoy' ? 'YoY %' : 'absolute'}`,
    source: ds.source, span: 'span-2', height: 'tall', option: lineOpt,
    note: visProv.length ? provNote(visProv) : null,
    exportName: `${ds.category}_${ds.source}_metrics`,
    exportAoa: () => seriesAoa(periods, freq, series),
  });

  const cards = [lineCard];

  // ---- domestic vs export mix (needs both metrics) ----
  const hasDom = metricIds.includes('domestic'), hasExp = metricIds.includes('exports');
  if (hasDom && hasExp) {
    const dom = metricBlock(ds, freq, 'domestic'), exp = metricBlock(ds, freq, 'exports');
    const groups = [
      { name: 'Domestic', color: '#4f46e5', values: tgt(dom).slice(start) },
      { name: 'Exports', color: '#06b6d4', values: tgt(exp).slice(start) },
    ];
    const mixOpt = stackedOption({ periods, freq, groups, percent: true, provisional: prov });
    cards.push(TrendCard({
      title: 'Domestic vs Exports mix',
      subtitle: `Share of domestic + exports over time · ${freqLabel(freq)}`,
      source: ds.source, span: 'span-2', height: 'tall', option: mixOpt,
      note: visProv.length ? provNote(visProv) : null,
      exportName: `${ds.category}_${ds.source}_dom_exp_mix`,
      exportAoa: () => seriesAoa(periods, freq, groups),
    }));
  } else if (ds.source === 'internal') {
    cards.push(TrendCard({
      title: 'Domestic vs Exports mix', source: ds.source, span: 'span-2', option: null,
      emptyTitle: 'Export split not in this dataset',
      emptyHint: 'The internal DB carries domestic sales for this category. Use the SIAM source for a production/exports breakdown.',
    }));
  }

  const grid = el('div', { class: 'grid' });
  mountCards(grid, cards);
  root.appendChild(grid);
}
