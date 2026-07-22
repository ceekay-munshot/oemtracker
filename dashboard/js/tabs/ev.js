// EV Tracker (Internal DB) — EV penetration (volume + % of segment), EV vs ICE split, and
// EV-maker share trends. Only internal datasets carry an EV block (2W, 3W, CV).
import { TrendCard, mountCards } from '../trendcard.js';
import { comboBarLineOption, stackedOption, lineOption, colorAt } from '../charts.js';
import { rangeStart, toShare } from '../compute.js';
import { periodLabel, periodLabelLong, fmtPct, compactNum } from '../format.js';
import { el, provNote } from '../ui.js';
import { provSet, freqLabel, statTile, deltaNode } from './common.js';

export function render(root, ctx) {
  const { ds, state } = ctx;

  if (!ds.ev) {
    const c = TrendCard({ title: 'EV Tracker', source: ds.source, option: null,
      emptyTitle: `No EV data for ${ds.category_label}`,
      emptyHint: 'EV tracking (penetration, EV-vs-ICE, EV-maker share) is available for Two-Wheelers, Three-Wheelers and Commercial Vehicles. Pick one of those categories in the filter bar.' });
    const g = el('div', { class: 'grid' }); mountCards(g, [c]); root.appendChild(g); return;
  }

  const freq = ds.ev[state.freq] ? state.freq : ds.frequencies[0];
  const evb = ds.ev[freq];
  const prov = provSet(ds, freq);
  const periodsFull = evb.periods;
  const n = periodsFull.length;
  const start = rangeStart(periodsFull, freq, state.range);
  const periods = periodsFull.slice(start);
  const visProv = periods.filter((k) => prov.has(k));

  const evTot = evb.ev_total;
  const segTot = evb.segment_total;
  const penFull = periodsFull.map((_, i) => (evTot[i] != null && segTot[i]) ? (evTot[i] / segTot[i]) * 100 : null);

  // ---- tiles ----
  let li = -1; for (let i = n - 1; i >= 0; i--) { if (evTot[i] != null) { li = i; break; } }
  const step = freq === 'monthly' ? 12 : (freq === 'quarterly' ? 4 : 1);
  const pen = li >= 0 ? penFull[li] : null;
  const penPrev = (li - step >= 0) ? penFull[li - step] : null;
  const tiles = el('div', { class: 'tiles' });
  tiles.appendChild(statTile(`EV volume · ${li >= 0 ? periodLabel(periodsFull[li], freq) : '—'}`,
    li >= 0 ? compactNum(evTot[li]) : '—',
    deltaNode(li >= 0 && evTot[li - step] ? (evTot[li] / evTot[li - step] - 1) * 100 : null, '%'), 'EV units · YoY'));
  tiles.appendChild(statTile('EV penetration', pen == null ? '—' : fmtPct(pen, 1),
    deltaNode(pen != null && penPrev != null ? pen - penPrev : null, 'pp'), 'EV ÷ segment · YoY'));
  // leading EV maker
  const makers = Object.entries(evb.makers).map(([id, m]) => ({ id, name: m.name, values: m.values }));
  let leadMaker = null;
  for (const m of makers) { const v = m.values[li]; if (v != null && (!leadMaker || v > leadMaker.v)) leadMaker = { name: m.name, v }; }
  if (leadMaker && evTot[li]) tiles.appendChild(statTile('Top EV maker', fmtPct((leadMaker.v / evTot[li]) * 100, 1), null, `${leadMaker.name} · of EV`));
  root.appendChild(tiles);

  // ---- penetration combo (bars EV vol + line penetration %) ----
  const penOpt = comboBarLineOption({
    periods, freq,
    bars: { name: 'EV volume', values: evTot.slice(start), color: '#10b981' },
    line: { name: 'EV penetration %', values: penFull.slice(start), color: '#4f46e5' },
    provisional: prov,
  });
  const penCard = TrendCard({
    title: `${ds.category_label} — EV penetration`,
    subtitle: `EV volume (bars) & EV % of segment (line) · ${freqLabel(freq)}`,
    source: ds.source, span: 'span-2', height: 'tall', option: penOpt,
    note: visProv.length ? provNote(visProv) : null,
    exportName: `${ds.category}_ev_penetration`,
    exportAoa: () => [['Period', 'EV volume', 'Segment total', 'EV penetration %'],
      ...periods.map((k, i) => [periodLabelLong(k, freq), evTot[start + i] ?? '', segTot[start + i] ?? '',
        penFull[start + i] == null ? '' : +penFull[start + i].toFixed(2)])],
  });

  // ---- EV vs ICE stacked (absolute) ----
  const iceFull = periodsFull.map((_, i) => (segTot[i] != null && evTot[i] != null) ? Math.max(0, segTot[i] - evTot[i]) : null);
  const evIceOpt = stackedOption({
    periods, freq, unit: 'num',
    groups: [
      { name: 'EV', color: '#10b981', values: evTot.slice(start) },
      { name: 'ICE', color: '#94a3b8', values: iceFull.slice(start) },
    ],
    provisional: prov,
  });
  const evIceCard = TrendCard({
    title: 'EV vs ICE',
    subtitle: `Segment volume split · ${freqLabel(freq)} · absolute`,
    source: ds.source, span: 'span-2', height: 'tall', option: evIceOpt,
    exportName: `${ds.category}_ev_vs_ice`,
    exportAoa: () => [['Period', 'EV', 'ICE'], ...periods.map((k, i) => [periodLabelLong(k, freq), evTot[start + i] ?? '', iceFull[start + i] ?? ''])],
  });

  // ---- EV-maker share of EV market ----
  const makerShare = makers.map((m, i) => {
    const sh = toShare(m.values, evTot);
    return { id: m.id, name: m.name, color: colorAt(i), full: sh, values: sh.slice(start) };
  }).filter((m) => m.full.some((v) => v != null));
  const makerOpt = lineOption({
    periods, freq, unit: 'pct',
    series: makerShare.map((m) => ({ name: m.name, values: m.values, color: m.color })),
    provisional: prov,
  });
  const makerCard = TrendCard({
    title: 'EV-maker share trends',
    subtitle: `Each maker's share of ${ds.category_label} EV market · ${freqLabel(freq)}`,
    source: ds.source, span: 'span-2', height: 'tall', option: makerShare.length ? makerOpt : null,
    exportName: `${ds.category}_ev_maker_share`,
    exportAoa: () => [['Period', ...makerShare.map((m) => m.name + ' (share %)')],
      ...periods.map((k, i) => [periodLabelLong(k, freq), ...makerShare.map((m) => (m.values[i] == null ? '' : +m.values[i].toFixed(2)))])],
    emptyTitle: 'No EV-maker breakdown', emptyHint: 'This category has no per-maker EV series.',
  });

  const grid = el('div', { class: 'grid' });
  mountCards(grid, [penCard, evIceCard, makerCard]);
  root.appendChild(grid);
}
