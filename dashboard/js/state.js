// state.js — single source of truth for the filter bar, persisted to the URL hash so views
// are shareable. Changing any control mutates state and notifies subscribers; the active tab
// re-renders. Entity selection is stored as a list of ids scoped to the current dataset.

const DEFAULTS = {
  tab: 'overview',
  category: '2w',
  source: 'siam',
  metric: 'total',
  freq: 'monthly',
  valueMode: 'abs',   // abs | yoy
  rebase: false,
  range: '5y',        // 1y | 3y | 5y | max
  activeOnly: true,
  entities: [],       // ids, dataset-scoped
};

const KEYMAP = { tab: 'tab', category: 'cat', source: 'src', metric: 'metric', freq: 'freq',
  valueMode: 'mode', rebase: 'rb', range: 'range', activeOnly: 'act', entities: 'ents' };

let state = { ...DEFAULTS };
const listeners = new Set();

export function getState() { return state; }

export function subscribe(fn) { listeners.add(fn); return () => listeners.delete(fn); }

let squelch = false;
export function setState(patch, opts = {}) {
  const prev = state;
  state = { ...state, ...patch };
  if (!opts.silent) {
    writeHash();
    for (const fn of listeners) fn(state, prev, patch);
  }
}

// Set without triggering listeners (used during dataset swap bootstrapping).
export function setStateSilent(patch) {
  state = { ...state, ...patch };
  writeHash();
}

function writeHash() {
  if (squelch) return;
  const p = new URLSearchParams();
  for (const k in KEYMAP) {
    const v = state[k];
    if (v === DEFAULTS[k]) continue;
    if (k === 'entities') { if (v && v.length) p.set(KEYMAP[k], v.join(',')); }
    else if (typeof v === 'boolean') p.set(KEYMAP[k], v ? '1' : '0');
    else if (v != null) p.set(KEYMAP[k], v);
  }
  const s = p.toString();
  const newHash = s ? '#' + s : '#';
  if (('#' + (location.hash.replace(/^#/, ''))) !== newHash) {
    history.replaceState(null, '', newHash);
  }
}

export function readHash() {
  const raw = location.hash.replace(/^#/, '');
  if (!raw) return;
  const p = new URLSearchParams(raw);
  const inv = {};
  for (const k in KEYMAP) inv[KEYMAP[k]] = k;
  const patch = {};
  for (const [hk, val] of p.entries()) {
    const k = inv[hk];
    if (!k) continue;
    if (k === 'entities') patch[k] = val ? val.split(',') : [];
    else if (typeof DEFAULTS[k] === 'boolean') patch[k] = val === '1';
    else patch[k] = val;
  }
  squelch = true;
  state = { ...state, ...patch };
  squelch = false;
}
