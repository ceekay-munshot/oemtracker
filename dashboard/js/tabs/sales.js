// Sales Trends — multi-line OEM trend (entities from the filter bar; Absolute/YoY/Index-100 and
// M/Q/Y from the filter bar) plus the period × OEM table with sort + Excel export.
import { TrendCard, mountCards } from '../trendcard.js';
import { lineOption, colorAt } from '../charts.js';
import { seriesForEntities } from '../compute.js';
import { el, provNote } from '../ui.js';
import { selEntities, metricLabel, provSet, freqLabel, seriesAoa, periodTable } from './common.js';

export function render(root, ctx) {
  const { ds, state, names } = ctx;
  const { metric, freq, valueMode: mode, range } = state;
  const unit = mode === 'yoy' ? 'pct' : 'num';
  const rebase = state.rebase && mode === 'abs';
  const prov = provSet(ds, freq);
  const ents = selEntities(ds, state);

  const so = seriesForEntities(ds, { metric, freq, valueMode: mode, ids: ents.map((e) => e.id), range, rebase, names });
  const visProv = so.periods.filter((k) => prov.has(k));
  const chartOpt = so.series.length ? lineOption({
    periods: so.periods, freq, unit: rebase ? 'index' : unit, zeroLine: mode === 'yoy',
    series: so.series.map((s, i) => ({ name: s.name, values: s.values, color: colorAt(i) })),
    provisional: prov,
  }) : null;

  const modeLabel = rebase ? 'indexed to 100' : (mode === 'yoy' ? 'YoY %' : 'absolute');
  const chartCard = TrendCard({
    title: `${ds.category_label} — OEM ${metricLabel(ds, metric)} trend`,
    subtitle: `${ents.length} OEMs · ${freqLabel(freq)} · ${modeLabel}`,
    source: ds.source, span: 'span-2', height: 'tall', option: chartOpt,
    note: visProv.length ? provNote(visProv) : null,
    exportName: `${ds.category}_${ds.source}_oem_trend`,
    exportAoa: () => seriesAoa(so.periods, freq, so.series),
    emptyTitle: 'No OEMs selected',
    emptyHint: 'Use the OEMs control in the filter bar to add companies to the trend.',
  });

  const tspec = periodTable(ds, { metric, freq, entities: ents, nCols: 6 });
  const tableCard = TrendCard({
    title: `${freqLabel(freq)} trend by OEM`,
    subtitle: `Last 6 ${freqLabel(freq).toLowerCase()} periods · recomputed YoY % & market share · ◐ = provisional`,
    source: ds.source, span: 'span-2',
    table: (tspec && tspec.rows.length) ? tspec : null,
    exportName: `${ds.category}_${ds.source}_period_table`,
    emptyTitle: 'No OEMs selected', emptyHint: 'Select OEMs to populate the table.',
  });

  const grid = el('div', { class: 'grid' });
  mountCards(grid, [chartCard, tableCard]);
  root.appendChild(grid);
}
