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
  if (window.__OEM_DATA[key]) return Promise.resolve(window.__OEM_DATA[key]);
  return new Promise((resolve, reject) => {
    if (!pending.has(key)) pending.set(key, []);
    pending.get(key).push(resolve);
    inject(`${DATA_DIR}/${key}.js`).catch(reject);
  });
}

// Build a quick {id: name} lookup for a dataset's entities.
export function entityNames(ds) {
  const m = {};
  for (const e of ds.entities) m[e.id] = e.name;
  return m;
}
