// Data — the full period × entity matrix for the current selection: sortable, Excel-exportable,
// source-labelled. Respects the metric / frequency / range / entity filters.
import { TrendCard, mountCards } from '../trendcard.js';
import { freqBlock, metricBlock, denomSeries, rangeStart } from '../compute.js';
import { fmtInt, periodLabel } from '../format.js';
import { el } from '../ui.js';
import { selEntities, metricLabel, provSet, freqLabel } from './common.js';

const CAP = 120; // max period columns rendered (keeps the DOM light); export still holds all shown

export function render(root, ctx) {
  const { ds, state } = ctx;
  const { metric, freq, range } = state;
  const blk = freqBlock(ds, freq);
  const mb = metricBlock(ds, freq, metric);
  const periodsFull = blk.periods;
  const start = rangeStart(periodsFull, freq, range);
  let periods = periodsFull.slice(start);
  let truncated = false;
  if (periods.length > CAP) { periods = periods.slice(periods.length - CAP); truncated = true; }
  const offset = periodsFull.length - periods.length;
  const prov = provSet(ds, freq);

  let ents = selEntities(ds, state);
  if (!ents.length) ents = ds.entities.filter((e) => e.active);

  const lastIdx = periodsFull.length - 1;
  const rows = ents.map((e) => {
    const arr = mb.entities[e.id] || [];
    const row = { id: e.id, name: e.name };
    periods.forEach((k, i) => { row['c' + i] = arr[offset + i]; });
    row.latest = arr[lastIdx];
    return row;
  });
  // industry total row
  const indArr = (mb.industry && mb.industry.some((v) => v != null)) ? mb.industry : denomSeries(mb.entities, periodsFull.length);
  const indRow = { id: '__industry', name: 'Industry (total)' };
  periods.forEach((k, i) => { indRow['c' + i] = indArr[offset + i]; });
  indRow.latest = indArr[lastIdx];
  rows.unshift(indRow);

  const columns = [
    { key: 'name', label: 'Entity', align: 'left', sortVal: (r) => r.name,
      fmt: (v, r) => el('span', { text: r.name, style: r.id === '__industry' ? { fontWeight: '800' } : null }), exportVal: (r) => r.name },
  ];
  periods.forEach((k, i) => {
    columns.push({
      key: 'c' + i, label: periodLabel(k, freq) + (prov.has(k) ? ' ◐' : ''), align: 'right', sortVal: (r) => r['c' + i],
      fmt: (v) => v == null ? '<span class="na">—</span>' : fmtInt(v), exportVal: (r) => (r['c' + i] == null ? '' : r['c' + i]),
    });
  });

  const subtitle = `${metricLabel(ds, metric)} · ${freqLabel(freq)} · ${periods.length} periods${truncated ? ' (latest ' + CAP + ' shown; export holds these)' : ''} · ◐ provisional`;
  const card = TrendCard({
    title: `${ds.category_label} — data matrix`,
    subtitle, source: ds.source, span: 'span-2',
    table: { columns, rows, sortKey: 'latest', sortDir: 'desc', initialShow: 25 },
    exportName: `${ds.category}_${ds.source}_${metric}_${freq}_matrix`,
  });

  const grid = el('div', { class: 'grid' });
  mountCards(grid, [card]);
  root.appendChild(grid);
}
