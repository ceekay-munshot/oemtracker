// app.js — application shell: header tabs, the global filter bar, dataset loading and routing.
// State lives in state.js and is mirrored to the URL hash; any control change re-renders the
// active tab. All charts share the filter bar; each tab consumes the controls relevant to it.

import { loadManifest, loadDataset, entityNames } from './data.js';
import { loadFlash } from './flash.js';
import { getState, setState, setStateSilent, subscribe, readHash } from './state.js';
import { el, clearNode, seg } from './ui.js';
import { disposeAllCards, resizeAllCards } from './trendcard.js';
import { periodLabelLong } from './format.js';

import * as overview from './tabs/overview.js';
import * as sales from './tabs/sales.js';
import * as share from './tabs/share.js';
import * as ev from './tabs/ev.js';
import * as prodmix from './tabs/prodmix.js';
import * as segmix from './tabs/segmix.js';
import * as datatab from './tabs/datatab.js';

const I = {
  overview: 'M3 12h4l3 8 4-16 3 8h4',
  sales: 'M4 19V5M4 19h16M8 16l3-4 3 2 4-6',
  share: 'M12 3v9l7 4M12 3a9 9 0 1 0 7 16',
  ev: 'M7 7h6l1 5H6zM4 12h12v4H4zM6 16v2M14 16v2M17 9l3 1-1 4',
  prodmix: 'M4 20V10M10 20V4M16 20v-7M20 20H2',
  segmix: 'M3 3h8v8H3zM13 3h8v5h-8zM13 10h8v11h-8zM3 13h8v8H3z',
  data: 'M4 5h16M4 12h16M4 19h16M8 5v14',
};
function ico(p) {
  return `<svg class="tab-ico" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="${p}"/></svg>`;
}

const TABS = [
  { id: 'overview', label: 'Overview', icon: I.overview, mod: overview },
  { id: 'sales', label: 'Sales Trends', icon: I.sales, mod: sales },
  { id: 'share', label: 'Market Share', icon: I.share, mod: share },
  { id: 'ev', label: 'EV Tracker', icon: I.ev, mod: ev },
  { id: 'prodmix', label: 'Production · Sales · Exports', icon: I.prodmix, mod: prodmix },
  { id: 'segmix', label: 'Segment Mix', icon: I.segmix, mod: segmix },
  { id: 'data', label: 'Data', icon: I.data, mod: datatab },
];

let MANIFEST = null;

function datasetKey(cat, src) { return `${cat}__${src}`; }
function catMeta(cat) { return MANIFEST.categories.find((c) => c.id === cat); }
function dmetaFor(cat, src) { return MANIFEST.datasets[datasetKey(cat, src)]; }

// Ensure the state is valid for the chosen category (source/metric/freq availability, entities).
function resolveState(ds, dmeta) {
  const s = getState();
  const patch = {};
  const cm = catMeta(s.category);
  if (!cm) { patch.category = MANIFEST.categories[0].id; }
  const sources = (catMeta(patch.category || s.category)).sources;
  let src = patch.source || s.source;
  if (!sources.includes(src)) { src = sources[0]; patch.source = src; }
  // dataset-dependent validation happens after (re)load in render(); here we only fix cat/src.
  return patch;
}

// ---- header tabs --------------------------------------------------------------------
function buildTabbar() {
  const bar = document.getElementById('tabbar');
  clearNode(bar);
  const s = getState();
  for (const t of TABS) {
    const b = el('button', { class: 'tab' + (t.id === s.tab ? ' active' : ''),
      html: ico(t.icon) + `<span>${t.label}</span>`,
      onclick: () => { if (getState().tab !== t.id) setState({ tab: t.id }); } });
    bar.appendChild(b);
  }
}

// ---- filter bar ---------------------------------------------------------------------
function buildFilterBar(ds, dmeta) {
  const bar = document.getElementById('filterbar');
  clearNode(bar);
  const s = getState();

  // Category
  const catSel = el('select', { class: 'sel', onchange: (e) => onCategoryChange(e.target.value) });
  for (const c of MANIFEST.categories) catSel.appendChild(el('option', { value: c.id, text: c.label, selected: c.id === s.category }));
  bar.appendChild(fgroup('Category', catSel));

  // Source (only if >1)
  const sources = catMeta(s.category).sources;
  if (sources.length > 1) {
    const srcSeg = seg(sources.map((x) => ({ v: x, label: x === 'siam' ? 'SIAM' : 'Internal DB' })), s.source,
      (v) => onSourceChange(v));
    bar.appendChild(fgroup('Source', srcSeg));
  } else {
    bar.appendChild(fgroup('Source', el('span', { class: 'chip ' + (sources[0] === 'siam' ? '' : 'ev'),
      text: sources[0] === 'siam' ? 'SIAM' : 'Internal DB' })));
  }
  bar.appendChild(el('div', { class: 'fdiv' }));

  // Metric (dataset metrics)
  if (ds.metrics && ds.metrics.length > 1) {
    const mSel = el('select', { class: 'sel', onchange: (e) => setState({ metric: e.target.value }) });
    for (const m of ds.metrics) mSel.appendChild(el('option', { value: m.id, text: m.label, selected: m.id === s.metric }));
    bar.appendChild(fgroup('Metric', mSel));
  }

  // Frequency
  const freqs = ds.frequencies;
  const freqSeg = seg(
    [{ v: 'monthly', label: 'Monthly' }, { v: 'quarterly', label: 'Quarterly' }, { v: 'yearly', label: 'Yearly (FY)' }]
      .map((o) => ({ ...o, disabled: !freqs.includes(o.v) })),
    s.freq, (v) => setState({ freq: v }));
  bar.appendChild(fgroup('Frequency', freqSeg));

  // Value mode + rebase
  const modeSeg = seg([{ v: 'abs', label: 'Absolute' }, { v: 'yoy', label: 'YoY %' }], s.valueMode,
    (v) => setState({ valueMode: v }));
  bar.appendChild(fgroup('Value', modeSeg));
  const rebaseBtn = el('button', { class: 'seg' });
  const rb = el('button', { class: s.rebase ? 'on' : '', text: 'Index 100',
    onclick: () => setState({ rebase: !getState().rebase }) });
  rebaseBtn.appendChild(rb);
  bar.appendChild(rebaseBtn);

  bar.appendChild(el('div', { class: 'fdiv' }));

  // Entities (multiselect popover) — relevant to Sales / Market Share / Data / Overview tabs.
  bar.appendChild(fgroup('OEMs', entityControl(ds, dmeta)));

  bar.appendChild(el('div', { class: 'fdiv' }));

  // Range
  const rangeSeg = seg([{ v: '1y', label: '1Y' }, { v: '3y', label: '3Y' }, { v: '5y', label: '5Y' }, { v: 'max', label: 'Max' }],
    s.range, (v) => setState({ range: v }));
  bar.appendChild(fgroup('Range', rangeSeg));
}

function fgroup(label, control) {
  return el('div', { class: 'fgroup' }, [el('span', { class: 'flabel', text: label }), control]);
}

// Entity multi-select popover.
function entityControl(ds, dmeta) {
  const s = getState();
  const btn = el('button', { class: 'ent-btn' }, [
    el('span', { text: 'Select' }),
    el('span', { class: 'count', text: String(s.entities.length) }),
    el('span', { html: `<svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round"><path d="M6 9l6 6 6-6"/></svg>` }),
  ]);
  const holder = el('div', { style: { position: 'relative' } }, [btn]);
  let pop = null;
  const close = () => { if (pop) { pop.remove(); pop = null; document.removeEventListener('click', outside, true); } };
  const outside = (e) => { if (pop && !holder.contains(e.target)) close(); };
  btn.addEventListener('click', (e) => {
    e.stopPropagation();
    if (pop) { close(); return; }
    pop = buildEntityPopover(ds, dmeta);
    holder.appendChild(pop);
    setTimeout(() => document.addEventListener('click', outside, true), 0);
  });
  return holder;
}

function buildEntityPopover(ds, dmeta) {
  const s = getState();
  const pop = el('div', { class: 'popover' });
  const head = el('div', { class: 'po-head' }, [
    el('span', { class: 'flabel', text: 'Select OEMs' }),
    el('div', {}, [
      el('a', { class: 'lnk', text: 'Top ' + MANIFEST.default_top_n, href: 'javascript:void 0',
        onclick: () => { setState({ entities: dmeta.top_default.slice() }); } }),
      el('span', { text: ' · ' }),
      el('a', { class: 'lnk', text: 'None', href: 'javascript:void 0', onclick: () => setState({ entities: [] }) }),
    ]),
  ]);
  pop.appendChild(head);

  // active-only toggle
  const actRow = el('label', { class: 'po-item' }, [
    el('input', { type: 'checkbox', ...(s.activeOnly ? { checked: true } : {}),
      onchange: (e) => setState({ activeOnly: e.target.checked }) }),
    el('span', { class: 'nm', text: 'Active OEMs only (hide defunct)' }),
  ]);
  pop.appendChild(actRow);

  const search = el('input', { class: 'po-search', placeholder: 'Search…' });
  pop.appendChild(search);
  const list = el('div');
  pop.appendChild(list);

  const { colorAt } = window.__oemColor || {};
  function renderList() {
    clearNode(list);
    const q = search.value.trim().toLowerCase();
    const cur = new Set(getState().entities);
    const ents = ds.entities.filter((e) => (getState().activeOnly ? e.active : true))
      .filter((e) => !q || e.name.toLowerCase().includes(q));
    ents.forEach((e, i) => {
      const selIdx = getState().entities.indexOf(e.id);
      const row = el('label', { class: 'po-item' + (e.active ? '' : ' inactive') }, [
        el('input', { type: 'checkbox', ...(cur.has(e.id) ? { checked: true } : {}),
          onchange: () => toggleEntity(e.id) }),
        el('span', { class: 'sw', style: { background: selIdx >= 0 && window.__PALETTE ? window.__PALETTE[selIdx % window.__PALETTE.length] : '#cbd0dc' } }),
        el('span', { class: 'nm', text: e.name, title: e.name }),
        el('span', { class: 'tt', text: e.active ? '' : 'defunct' }),
      ]);
      list.appendChild(row);
    });
    if (!ents.length) list.appendChild(el('div', { class: 'note', text: 'No matches.' }));
  }
  search.addEventListener('input', renderList);
  renderList();
  return pop;
}

function toggleEntity(id) {
  const s = getState();
  const set = s.entities.slice();
  const i = set.indexOf(id);
  if (i >= 0) set.splice(i, 1); else set.push(id);
  setState({ entities: set });
}

// ---- category / source changes reset dependent selections ---------------------------
async function onCategoryChange(cat) {
  const sources = catMeta(cat).sources;
  const s = getState();
  const src = sources.includes(s.source) ? s.source : sources[0];
  const ds = await loadDataset(datasetKey(cat, src));
  const dmeta = dmetaFor(cat, src);
  const patch = { category: cat, source: src, entities: dmeta.top_default.slice() };
  fixMetricFreq(ds, patch);
  setState(patch);
}
async function onSourceChange(src) {
  const s = getState();
  const ds = await loadDataset(datasetKey(s.category, src));
  const dmeta = dmetaFor(s.category, src);
  const patch = { source: src, entities: dmeta.top_default.slice() };
  fixMetricFreq(ds, patch);
  setState(patch);
}
function fixMetricFreq(ds, patch) {
  const s = getState();
  const metrics = ds.metrics.map((m) => m.id);
  if (!metrics.includes(patch.metric || s.metric)) patch.metric = ds.default_metric;
  if (!ds.frequencies.includes(patch.freq || s.freq)) patch.freq = ds.frequencies.includes('monthly') ? 'monthly' : ds.frequencies[0];
}

// ---- footer -------------------------------------------------------------------------
function updateFooter(ds, dmeta) {
  const meta = document.getElementById('footer-meta');
  const base = ds.frequencies[0];
  const latest = ds.latest[base];
  const asof = periodLabelLong(latest, base);
  meta.textContent = `${dmeta.source_label} · ${dmeta.category_label} · as of ${asof} · FY = Apr–Mar`;
}

// ---- main render --------------------------------------------------------------------
let rendering = false;
async function render() {
  if (!MANIFEST) return;
  rendering = true;
  // resolve category/source validity
  const pre = resolveState();
  if (Object.keys(pre).length) setStateSilent(pre);
  // EV Tracker & Segment Mix exist only on the Internal DB source (SIAM has no EV/segment
  // breakdown). Auto-select that source when the category has one, so those tabs populate
  // instead of showing a "switch source" empty state.
  {
    const st = getState();
    if ((st.tab === 'ev' || st.tab === 'segmix') && st.source !== 'internal'
        && catMeta(st.category).sources.includes('internal')) {
      setStateSilent({ source: 'internal' });
    }
  }
  const s = getState();
  const key = datasetKey(s.category, s.source);
  let ds;
  try { ds = await loadDataset(key); } catch (e) { console.error(e); rendering = false; return; }
  const dmeta = dmetaFor(s.category, s.source);

  // validate metric/freq/entities against the loaded dataset
  const patch = {};
  fixMetricFreq(ds, patch);
  if (!s.entities.length) patch.entities = dmeta.top_default.slice();
  else {
    const valid = new Set(ds.entities.map((e) => e.id));
    const filtered = s.entities.filter((id) => valid.has(id));
    if (filtered.length !== s.entities.length) patch.entities = filtered.length ? filtered : dmeta.top_default.slice();
  }
  if (Object.keys(patch).length) setStateSilent(patch);

  buildTabbar();
  buildFilterBar(ds, dmeta);
  updateFooter(ds, dmeta);

  disposeAllCards();
  const main = document.getElementById('main');
  clearNode(main);

  const tab = TABS.find((t) => t.id === getState().tab) || TABS[0];
  const ctx = { ds, dmeta, manifest: MANIFEST, state: getState(), names: entityNames(ds), key };
  try {
    tab.mod.render(main, ctx);
  } catch (e) {
    console.error('Tab render error', e);
    main.appendChild(el('div', { class: 'card' }, [el('div', { class: 'empty' }, [el('div', { class: 'et', text: 'Something went wrong rendering this view.' }), el('div', { class: 'eh', text: String(e.message || e) })])]));
  }
  rendering = false;
}

// ---- boot ---------------------------------------------------------------------------
async function boot() {
  // expose palette for the entity popover swatches
  const { PALETTE, colorAt } = await import('./charts.js');
  window.__PALETTE = PALETTE; window.__oemColor = { colorAt };

  MANIFEST = await loadManifest();
  await loadFlash().catch(() => {});   // provisional company-flash overlay (optional; absent-safe)
  readHash();
  // ensure a valid starting dataset & entities
  const s = getState();
  if (!catMeta(s.category)) setStateSilent({ category: MANIFEST.categories[0].id });
  const sources = catMeta(getState().category).sources;
  if (!sources.includes(getState().source)) setStateSilent({ source: sources[0] });

  subscribe(() => { if (!rendering) render(); });
  window.addEventListener('hashchange', () => { /* hash is source of truth we write; ignore external */ });
  window.addEventListener('resize', debounce(resizeAllCards, 150));

  await render();
  document.getElementById('veil').classList.add('hidden');
}

function debounce(fn, ms) { let t; return (...a) => { clearTimeout(t); t = setTimeout(() => fn(...a), ms); }; }

boot().catch((e) => {
  console.error(e);
  const veil = document.getElementById('veil');
  if (veil) veil.querySelector('.veil-text').textContent = 'Failed to load: ' + (e.message || e);
});
