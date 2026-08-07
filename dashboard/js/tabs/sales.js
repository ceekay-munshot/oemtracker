// Sales Trends — multi-line OEM trend (entities from the filter bar; Absolute/YoY/Index-100 and
// M/Q/Y from the filter bar) plus the period × OEM table with sort + Excel export.
//
// When viewing SIAM monthly in absolute mode, the provisional company-flash overlay
// (data/out/company_flash.js, source "Company(BSE/NSE)") is drawn as its OWN dashed tip per OEM
// — continuing each SIAM line with the latest company-disclosed month(s). It is never merged
// into the SIAM values (one source per series); it has its own legend toggle + source note, and
// is simply absent for OEMs/views where no flash data exists.
import { TrendCard, mountCards } from '../trendcard.js';
import { lineOption, colorAt } from '../charts.js';
import { seriesForEntities } from '../compute.js';
import { flashTip } from '../flash.js';
import { setState } from '../state.js';
import { el, provNote } from '../ui.js';
import { selEntities, metricLabel, provSet, freqLabel, seriesAoa, periodTable } from './common.js';

function combineNotes(a, b) {
  if (a && b) { const w = el('div'); w.appendChild(a); w.appendChild(b); return w; }
  return a || b || null;
}

// Some SIAM "monthly" series are really QUARTERLY: the whole quarter is parked in the quarter-end
// month with 0s in the two months between (e.g. Tata PV). A monthly flash tip on such a series
// would hang a one-month figure off a three-month total — misleading — so we withhold the tip for
// those entities. Tell-tale: a large fraction of reported months are exactly 0.
function looksQuarterly(values) {
  const reported = (values || []).filter((v) => v != null);
  if (reported.length < 6) return false;
  const zeros = reported.filter((v) => v === 0).length;
  return zeros / reported.length > 0.4;   // quarterly-on-monthly ≈ ⅔ zeros; genuine monthly ≈ 0
}

export function render(root, ctx) {
  const { ds, state, names } = ctx;
  const { metric, freq, valueMode: mode, range } = state;
  const unit = mode === 'yoy' ? 'pct' : 'num';
  const rebase = state.rebase && mode === 'abs';
  const prov = provSet(ds, freq);
  const ents = selEntities(ds, state);

  const so = seriesForEntities(ds, { metric, freq, valueMode: mode, ids: ents.map((e) => e.id), range, rebase, names });

  // Base series (solid, one colour per selected OEM — order matches `ents`).
  let periods = so.periods;
  let baseSeries = so.series.map((s, i) => ({ name: s.name, values: s.values, color: colorAt(i) }));
  let chartSeries = baseSeries;
  let provForChart = prov;

  // --- provisional company-flash overlay (SIAM + monthly + absolute only) -------------
  const flashEligible = mode === 'abs' && !rebase && freq === 'monthly';
  const tip = flashEligible ? flashTip(ds, metric, ents) : null;
  const actions = [];
  let flashNote = null;
  // An entity can take a flash tip only if it has flash data AND a genuine-monthly base series.
  const canFlash = (e, i) => !!(tip && tip.byId[e.id] && !looksQuarterly(baseSeries[i].values));
  if (tip && ents.some(canFlash)) {
    actions.push(el('label', { class: 'flash-toggle', title: 'Show/hide the provisional company-disclosure overlay' }, [
      el('input', { type: 'checkbox', ...(state.showFlash ? { checked: true } : {}),
        onchange: (e) => setState({ showFlash: e.target.checked }) }),
      el('span', { text: '⚡ Flash' }),
    ]));
    if (state.showFlash) {
      const extra = tip.periods.filter((p) => !periods.includes(p));      // flash months beyond SIAM
      const allPeriods = periods.concat(extra);
      const pad = (vals) => { const v = vals.slice(); while (v.length < allPeriods.length) v.push(null); return v; };
      baseSeries = baseSeries.map((s) => ({ ...s, values: pad(s.values) }));
      const flashSeries = [];
      ents.forEach((e, i) => {
        const t = tip.byId[e.id];
        if (!t || looksQuarterly(baseSeries[i].values)) return;           // no flash, or quarterly base — skip
        const bv = baseSeries[i].values;
        const vals = allPeriods.map(() => null);
        let anchor = -1;                                                  // last confirmed SIAM point
        for (let j = periods.length - 1; j >= 0; j--) { if (bv[j] != null) { anchor = j; break; } }
        if (anchor >= 0) vals[anchor] = bv[anchor];                       // so the dashed tip continues the line
        for (const p in t) { const idx = allPeriods.indexOf(p); if (idx >= 0) vals[idx] = t[p].value; }
        flashSeries.push({ name: `${e.name} · flash`, values: vals, color: colorAt(i), dashed: true });
      });
      if (flashSeries.length) {
        periods = allPeriods;
        chartSeries = baseSeries.concat(flashSeries);
        provForChart = new Set([...prov, ...tip.periods]);
        flashNote = el('div', { class: 'note',
          html: '⚡ <b>Flash</b> — company disclosure (BSE/NSE), <b>provisional</b> until SIAM-confirmed. '
              + 'Dashed tip = latest company-reported month, shown as its own overlay (not blended into SIAM).' });
      }
    }
  }

  const siamProv = so.periods.filter((k) => prov.has(k));
  const chartOpt = chartSeries.length ? lineOption({
    periods, freq, unit: rebase ? 'index' : unit, zeroLine: mode === 'yoy',
    series: chartSeries.map((s) => ({ name: s.name, values: s.values, color: s.color, dashed: s.dashed })),
    provisional: provForChart,
  }) : null;

  const modeLabel = rebase ? 'indexed to 100' : (mode === 'yoy' ? 'YoY %' : 'absolute');
  const chartCard = TrendCard({
    title: `${ds.category_label} — OEM ${metricLabel(ds, metric)} trend`,
    subtitle: `${ents.length} OEMs · ${freqLabel(freq)} · ${modeLabel}`,
    source: ds.source, span: 'span-2', height: 'tall', option: chartOpt,
    actions,
    note: combineNotes(siamProv.length ? provNote(siamProv) : null, flashNote),
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
