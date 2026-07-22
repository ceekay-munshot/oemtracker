// data.js — manifest + dataset loading via <script> injection (JSONP-style) so the dashboard
// works from file:// with no server and no runtime .xlsx parsing. Datasets are cached and
// lazy-loaded per (category, source) the first time a tab needs them.

const DATA_DIR = 'data';
window.__OEM_DATA = window.__OEM_DATA || {};
const pending = new Map();
window.__OEM_SET = (key, payload) => {
  window.__OEM_DATA[key] = payload;
  if (pending.has(key)) { pending.get(key).forEach((res) => res(payload)); pending.delete(key); }
};

function inject(src) {
  return new Promise((resolve, reject) => {
    const s = document.createElement('script');
    s.src = src; s.async = true;
    s.onload = () => resolve();
    s.onerror = () => reject(new Error('Failed to load ' + src));
    document.head.appendChild(s);
  });
}

let manifestPromise = null;
export function loadManifest() {
  if (window.__OEM_MANIFEST) return Promise.resolve(window.__OEM_MANIFEST);
  if (manifestPromise) return manifestPromise;
  manifestPromise = new Promise((resolve, reject) => {
    window.addEventListener('oem-manifest', () => resolve(window.__OEM_MANIFEST), { once: true });
    inject(`${DATA_DIR}/manifest.js`).catch(reject);
  });
  return manifestPromise;
}

export function loadDataset(key) {
  if (window.__OEM_DATA[key]) return Promise.resolve(trimPartial(window.__OEM_DATA[key]));
  return new Promise((resolve, reject) => {
    if (!pending.has(key)) pending.set(key, []);
    pending.get(key).push((p) => resolve(trimPartial(p)));
    inject(`${DATA_DIR}/${key}.js`).catch(reject);
  });
}

// Drop trailing in-progress (partial) periods from Quarterly/Yearly views.
// A partial period (e.g. FY27 = only Apr+May so far, or the current quarter) is incomplete;
// plotting it next to full periods produces a misleading cliff in the line, a bogus YoY %
// (2 months vs 12), and a distorted market-share move. So it is removed from every
// Q/Y chart, table, segment and EV series here — the single point all tabs read through.
// Monthly views are untouched (months are complete; the latest 1-2 stay flagged provisional).
// Fiscal-year-to-date is surfaced separately, and correctly, by the Overview "FY.. so far"
// tile, which compares like-for-like against the same months of the prior year.
function trimPartial(ds) {
  if (!ds || ds.__trimmed) return ds;
  ds.__trimmed = true;
  for (const freq of ds.frequencies) {
    const blk = ds.series && ds.series[freq];
    if (!blk || !blk.partial) continue;
    let k = 0;
    for (let i = blk.periods.length - 1; i >= 0; i--) { if (blk.partial[i]) k++; else break; }
    if (k === 0) continue;
    const keep = Math.max(0, blk.periods.length - k);
    blk.periods = blk.periods.slice(0, keep);
    blk.partial = blk.partial.slice(0, keep);
    for (const mk in blk.metrics) {
      const m = blk.metrics[mk];
      if (m.industry) m.industry = m.industry.slice(0, keep);
      if (m.entities) for (const id in m.entities) m.entities[id] = m.entities[id].slice(0, keep);
    }
    if (ds.segments && ds.segments[freq]) {
      const sg = ds.segments[freq];
      sg.periods = sg.periods.slice(0, keep);
      for (const g of sg.groups) g.values = g.values.slice(0, keep);
    }
    if (ds.ev && ds.ev[freq]) {
      const ev = ds.ev[freq];
      ev.periods = ev.periods.slice(0, keep);
      ev.ev_total = ev.ev_total.slice(0, keep);
      ev.segment_total = ev.segment_total.slice(0, keep);
      for (const id in ev.makers) ev.makers[id].values = ev.makers[id].values.slice(0, keep);
    }
    ds.latest[freq] = blk.periods.length ? blk.periods[blk.periods.length - 1] : null;
    if (ds.provisional && ds.provisional[freq]) {
      const present = new Set(blk.periods);
      ds.provisional[freq] = ds.provisional[freq].filter((p) => present.has(p));
    }
  }
  return ds;
}

// Build a quick {id: name} lookup for a dataset's entities.
export function entityNames(ds) {
  const m = {};
  for (const e of ds.entities) m[e.id] = e.name;
  return m;
}
