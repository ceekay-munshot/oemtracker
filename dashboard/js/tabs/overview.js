// Overview — one hero trend (category total), a top-OEM multi-line, and 3–4 slim stat tiles.
import { TrendCard, mountCards } from '../trendcard.js';
import { lineOption, colorAt } from '../charts.js';
import { industrySeries, seriesForEntities, freqBlock, metricBlock, denomSeries, latestStat } from '../compute.js';
import { compactNum, fmtInt, fmtDelta, fmtPct } from '../format.js';
import { el } from '../ui.js';
import { provNote } from '../ui.js';
import {
  selEntities, metricLabel, provSet, statTile, deltaNode, fytdStat, leaderStat, freqLabel, seriesAoa,
} from './common.js';

export function render(root, ctx) {
  const { ds, state, names } = ctx;
  const { metric, freq, valueMode: mode, range } = state;
  const unit = mode === 'yoy' ? 'pct' : 'num';
  const prov = provSet(ds, freq);
  const base = ds.frequencies[0];

  // ---- stat tiles ----
  const blkBase = freqBlock(ds, base);
  const mbBase = metricBlock(ds, base, metric);
  const industryFull = (mbBase.industry && mbBase.industry.some((v) => v != null))
    ? mbBase.industry : denomSeries(mbBase.entities, blkBase.periods.length);
  const ls = latestStat(blkBase.periods, industryFull, base);
  const fy = fytdStat(ds, metric);
  const leader = leaderStat(ds, metric);

  const tiles = el('div', { class: 'tiles' });
  tiles.appendChild(statTile(
    `Latest · ${ls.period || '—'}`, compactNum(ls.value),
    deltaNode(ls.yoy, '%'), `${metricLabel(ds, metric)} · YoY`));
  if (fy) tiles.appendChild(statTile(
    `FY${String(fy.fy).slice(2)} so far`, compactNum(fy.value),
    deltaNode(fy.yoy, '%'), `${fy.nPeriods} ${base === 'quarterly' ? 'qtr' : 'mo'} · vs same period LY`));
  if (leader) tiles.appendChild(statTile(
    'Market leader', fmtPct(leader.share, 1),
    null, `${leader.name}`));
  // 4th tile: EV penetration if available, else OEMs tracked
  if (ds.ev && ds.ev[base]) {
    const evb = ds.ev[base];
    let li = -1; for (let i = evb.ev_total.length - 1; i >= 0; i--) { if (evb.ev_total[i] != null) { li = i; break; } }
    const pen = (li >= 0 && evb.segment_total[li]) ? (evb.ev_total[li] / evb.segment_total[li]) * 100 : null;
    const prevIdx = li - (base === 'monthly' ? 12 : (base === 'quarterly' ? 4 : 1));
    const prevPen = (prevIdx >= 0 && evb.segment_total[prevIdx]) ? (evb.ev_total[prevIdx] / evb.segment_total[prevIdx]) * 100 : null;
    tiles.appendChild(statTile('EV penetration', pen == null ? '—' : fmtPct(pen, 1),
      deltaNode(pen != null && prevPen != null ? pen - prevPen : null, 'pp'), 'EV ÷ segment · YoY'));
  } else {
    tiles.appendChild(statTile('OEMs tracked', String(ctx.dmeta.n_active),
      null, `of ${ctx.dmeta.n_entities} · active`));
  }
  root.appendChild(tiles);

  // ---- hero + top-OEM ----
  const hero = industrySeries(ds, { metric, freq, valueMode: mode, range });
  const visProv = hero.periods.filter((k) => prov.has(k));
  const heroOpt = hero.periods.length ? lineOption({
    periods: hero.periods, freq, unit, area: mode !== 'yoy', zeroLine: mode === 'yoy',
    series: [{ name: `${ds.category_label} ${metricLabel(ds, metric)}`, values: hero.values, color: '#4f46e5' }],
    provisional: prov,
  }) : null;
  const heroCard = TrendCard({
    title: `${ds.category_label} — ${metricLabel(ds, metric)} trend`,
    subtitle: `Industry total · ${freqLabel(freq)} · ${mode === 'yoy' ? 'YoY %' : 'absolute'}`,
    source: ds.source, span: 'span-2', height: 'tall', option: heroOpt,
    note: visProv.length ? provNote(visProv) : null,
    exportName: `${ds.category}_${ds.source}_${metric}_industry`,
    exportAoa: () => seriesAoa(hero.periods, freq, [{ name: `${ds.category_label} ${metricLabel(ds, metric)}`, values: hero.values }]),
    emptyTitle: 'No industry series', emptyHint: 'Try a different metric or frequency.',
  });

  const ents = selEntities(ds, state).slice(0, 6);
  const rebase = state.rebase && mode === 'abs';
  const so = seriesForEntities(ds, { metric, freq, valueMode: mode, ids: ents.map((e) => e.id), range, rebase, names });
  const topOpt = so.series.length ? lineOption({
    periods: so.periods, freq, unit: rebase ? 'index' : unit, zeroLine: mode === 'yoy',
    series: so.series.map((s, i) => ({ name: s.name, values: s.values, color: colorAt(i) })),
    provisional: prov,
  }) : null;
  const topCard = TrendCard({
    title: 'Top OEMs — trend',
    subtitle: `${ents.length} selected · ${freqLabel(freq)} · ${rebase ? 'indexed to 100' : (mode === 'yoy' ? 'YoY %' : 'absolute')}`,
    source: ds.source, span: 'span-2', height: 'tall', option: topOpt,
    exportName: `${ds.category}_${ds.source}_top_oems`,
    exportAoa: () => seriesAoa(so.periods, freq, so.series),
    emptyTitle: 'No OEMs selected', emptyHint: 'Pick OEMs from the filter bar to compare their trends.',
  });

  const grid = el('div', { class: 'grid grid-2' });
  mountCards(grid, [heroCard, topCard]);
  root.appendChild(grid);
}
