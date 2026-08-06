// flash.js — the Company(BSE/NSE) flash overlay: fast, provisional per-OEM monthly sales that
// land days after month-end (weeks before SIAM). It is loaded from data/out/company_flash.js
// (JSONP twin, offline-safe) and rendered as its OWN dashed "tip" on the existing SIAM per-OEM
// monthly trend — NEVER merged into the SIAM values (one source per series). Absent gracefully:
// if the file is missing, or the current view isn't SIAM/monthly/absolute, no overlay is shown.

const DATA_DIR = 'data';
let flashPromise = null;

export function loadFlash() {
  if (window.__OEM_FLASH !== undefined) return Promise.resolve(window.__OEM_FLASH);
  if (flashPromise) return flashPromise;
  flashPromise = new Promise((resolve) => {
    let done = false;
    const finish = (v) => { if (!done) { done = true; window.__OEM_FLASH = v || null; resolve(window.__OEM_FLASH); } };
    window.addEventListener('oem-flash', () => finish(window.__OEM_FLASH), { once: true });
    const s = document.createElement('script');
    s.src = `${DATA_DIR}/out/company_flash.js`; s.async = true;
    s.onerror = () => finish(null);        // overlay simply absent -> dashboard unchanged
    document.head.appendChild(s);
  });
  return flashPromise;
}

export function getFlash() { return window.__OEM_FLASH || null; }

// Match build.py slug(): lowercase, non-alphanumeric -> "_", trim underscores. Used to line the
// flash OEM (canonical name) up with the SIAM entity id (slug of the workbook name).
export function slug(name) {
  return String(name).trim().toLowerCase().replace(/[^a-z0-9]+/g, '_').replace(/^_+|_+$/g, '');
}

const METRIC_MAP = { domestic: 'Domestic', exports: 'Exports', total: 'Total' };

// Derive the flash tip for the current view. Returns null unless it applies (SIAM source +
// a metric the flash carries). Otherwise: { periods:[flash months...], byId:{ entityId:
// {period:{value,provisional}} } } for only the entities that actually have flash data.
export function flashTip(ds, metric, entities) {
  const fl = getFlash();
  if (!fl || !fl.categories || ds.source !== 'siam') return null;
  const fm = METRIC_MAP[metric];
  if (!fm) return null;
  const cat = fl.categories[ds.category];
  if (!cat) return null;

  const want = new Set(entities.map((e) => e.id));
  const byId = {};
  const periods = new Set();
  for (const oem in cat) {
    const id = slug(oem);
    if (!want.has(id)) continue;
    for (const period in cat[oem]) {
      const cell = cat[oem][period][fm];
      if (!cell || cell.value == null) continue;
      (byId[id] = byId[id] || {})[period] = { value: cell.value, provisional: cell.provisional !== false };
      periods.add(period);
    }
  }
  if (!Object.keys(byId).length) return null;
  return { periods: [...periods].sort(), byId };
}
