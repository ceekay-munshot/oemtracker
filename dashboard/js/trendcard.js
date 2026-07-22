// trendcard.js — the single reusable card every tab uses. It owns a chart (optional), an
// optional sortable + exportable table, mini-toggles, a source tag and provisional note, plus
// calm empty states. Chart lifecycle (init/resize/dispose) is centrally tracked.

import { el, clearNode, sourceTag, exportBtn, emptyState } from './ui.js';
import { enableClosestSeries } from './charts.js';
import { downloadXlsx } from './xlsx.js';

const registry = new Set();
export function disposeAllCards() { for (const h of registry) { try { h.dispose(); } catch (_) {} } registry.clear(); }
export function resizeAllCards() { for (const h of registry) { try { h.resize(); } catch (_) {} } }

// ---- sortable / exportable table ----------------------------------------------------
// columns: [{ key, label, align, fmt(val,row)->string|Node, sortVal(row)->num|str, cls, exportVal(row) }]
// rows:    [ objects keyed by column.key ]
function buildTable(spec) {
  const { columns, rows, initialShow = 8 } = spec;
  let sortKey = spec.sortKey || null;
  let sortDir = spec.sortDir || 'desc';
  let expanded = rows.length <= initialShow;

  const wrap = el('div', { class: 'tbl-wrap' });
  const table = el('table', { class: 'tbl' });
  const thead = el('thead');
  const tbody = el('tbody');
  table.appendChild(thead); table.appendChild(tbody);
  wrap.appendChild(table);

  function sortRows() {
    if (!sortKey) return rows.slice();
    const col = columns.find((c) => c.key === sortKey);
    const val = (r) => (col && col.sortVal ? col.sortVal(r) : r[sortKey]);
    const arr = rows.slice().sort((a, b) => {
      let av = val(a), bv = val(b);
      if (av == null) av = -Infinity; if (bv == null) bv = -Infinity;
      if (typeof av === 'string' || typeof bv === 'string') return String(av).localeCompare(String(bv));
      return av - bv;
    });
    if (sortDir === 'desc') arr.reverse();
    return arr;
  }

  function renderHead() {
    clearNode(thead);
    const tr = el('tr');
    for (const c of columns) {
      const sorted = c.key === sortKey;
      const arrow = sorted ? (sortDir === 'desc' ? '▼' : '▲') : '↕';
      const th = el('th', { class: (sorted ? 'sorted ' : '') + (c.align === 'left' ? '' : ''),
        style: c.align === 'left' ? { textAlign: 'left' } : null,
        html: `${c.label}<span class="arr">${arrow}</span>` });
      if (c.sortVal !== null) th.addEventListener('click', () => {
        if (sortKey === c.key) sortDir = sortDir === 'desc' ? 'asc' : 'desc';
        else { sortKey = c.key; sortDir = 'desc'; }
        renderHead(); renderBody();
      });
      tr.appendChild(th);
    }
    thead.appendChild(tr);
  }

  function renderBody() {
    clearNode(tbody);
    const sorted = sortRows();
    const shown = expanded ? sorted : sorted.slice(0, initialShow);
    for (const r of shown) {
      const tr = el('tr');
      for (const c of columns) {
        const out = c.fmt ? c.fmt(r[c.key], r) : (r[c.key] == null ? '—' : String(r[c.key]));
        const td = el('td', { style: c.align === 'left' ? { textAlign: 'left' } : null });
        if (out instanceof Node) td.appendChild(out); else td.innerHTML = out;
        tr.appendChild(td);
      }
      tbody.appendChild(tr);
    }
    if (sorted.length > initialShow) {
      const tr = el('tr');
      const td = el('td', { colspan: columns.length, style: { padding: 0 } });
      const btn = el('button', { class: 'tbl-more',
        text: expanded ? 'Show fewer' : `Show all ${sorted.length}` ,
        onclick: () => { expanded = !expanded; renderBody(); } });
      td.appendChild(btn); tr.appendChild(td); tbody.appendChild(tr);
    }
  }

  renderHead(); renderBody();

  function getAoa() {
    const header = columns.map((c) => c.label.replace(/<[^>]+>/g, ''));
    const body = sortRows().map((r) => columns.map((c) => (c.exportVal ? c.exportVal(r) : r[c.key])));
    return [header, ...body];
  }
  return { node: wrap, getAoa };
}

// ---- the card -----------------------------------------------------------------------
// cfg: { title, titleExtra:[Node], subtitle, source, span, height, actions:[Node],
//        option (echarts opt) | empty, note (Node), table (spec), exportAoa (fn|aoa),
//        exportName, emptyTitle, emptyHint }
export function TrendCard(cfg) {
  const actions = el('div', { class: 'card-actions' });
  for (const a of (cfg.actions || [])) if (a) actions.appendChild(a);

  let tableApi = null;
  const wantExport = cfg.table || cfg.exportAoa;
  if (wantExport) {
    actions.appendChild(exportBtn(() => {
      const aoa = cfg.table ? tableApi.getAoa()
        : (typeof cfg.exportAoa === 'function' ? cfg.exportAoa() : cfg.exportAoa);
      const name = (cfg.exportName || cfg.title || 'export').replace(/[^\w]+/g, '_').slice(0, 40);
      downloadXlsx(name, (cfg.title || 'Sheet1').slice(0, 28), aoa);
    }));
  }
  actions.appendChild(sourceTag(cfg.source));

  const titleNode = el('div', { class: 'card-title' }, [document.createTextNode(cfg.title || '')]);
  for (const t of (cfg.titleExtra || [])) titleNode.appendChild(t);

  const head = el('div', { class: 'card-head' }, [
    el('div', {}, [titleNode, cfg.subtitle ? el('div', { class: 'card-sub', text: cfg.subtitle }) : null]),
    actions,
  ]);

  const card = el('div', { class: 'card ' + (cfg.span || '') }, [head]);

  let chartDom = null;
  const isEmpty = cfg.empty || (!cfg.option && !cfg.table);
  if (isEmpty) {
    card.appendChild(emptyState(cfg.emptyTitle, cfg.emptyHint));
  } else {
    if (cfg.option) {
      chartDom = el('div', { class: 'chart ' + (cfg.height || '') });
      card.appendChild(chartDom);
    }
    if (cfg.note) card.appendChild(cfg.note);
    if (cfg.table) { tableApi = buildTable(cfg.table); card.appendChild(tableApi.node); }
  }

  let chart = null;
  const handle = {
    node: card,
    mount() {
      if (!chartDom) return;
      chart = window.echarts.init(chartDom, null, { renderer: 'canvas' });
      chart.setOption(cfg.option);
      if (cfg.option.__meta) enableClosestSeries(chart, chartDom, cfg.option.__meta);
      registry.add(handle);
    },
    resize() { if (chart) chart.resize(); },
    dispose() {
      if (chart) {
        if (chart.__onMove && chart.__moveDom) chart.__moveDom.removeEventListener('mousemove', chart.__onMove);
        chart.dispose(); chart = null;
      }
      registry.delete(handle);
    },
  };
  return handle;
}

// Convenience: a table-only card (no chart) — used by the Data tab.
export function TableCard(cfg) {
  return TrendCard({ ...cfg, option: null, empty: false, __tableOnly: true });
}

// Append a set of card handles into a container, then initialise their charts once the nodes
// are laid out (ECharts needs a sized element).
export function mountCards(container, cards) {
  for (const c of cards) container.appendChild(c.node);
  requestAnimationFrame(() => { for (const c of cards) c.mount(); });
}
