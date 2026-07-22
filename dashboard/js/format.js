// format.js — number & period formatting (Indian conventions: Lakh / Crore).

const MONTHS = ['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec'];
const IN_INT = new Intl.NumberFormat('en-IN', { maximumFractionDigits: 0 });

// Full grouped integer, Indian digit grouping (e.g. 24,02,284).
export function fmtInt(n) {
  if (n === null || n === undefined || Number.isNaN(n)) return '—';
  return IN_INT.format(Math.round(n));
}

// Compact volume in Lakh (L) / Crore (Cr) — consistent across auto volumes.
export function compactNum(n) {
  if (n === null || n === undefined || Number.isNaN(n)) return '—';
  const a = Math.abs(n);
  if (a < 1000) return String(Math.round(n));
  if (a < 1e5) return IN_INT.format(Math.round(n));         // up to 1 lakh: grouped
  if (a < 1e7) return (n / 1e5).toFixed(a < 1e6 ? 2 : 1) + ' L';   // lakh
  return (n / 1e7).toFixed(2) + ' Cr';                       // crore
}

// Percentage with sign control.
export function fmtPct(n, dec = 1) {
  if (n === null || n === undefined || Number.isNaN(n)) return '—';
  return n.toFixed(dec) + '%';
}

// Signed delta for YoY etc.
export function fmtDelta(n, dec = 1, unit = '%') {
  if (n === null || n === undefined || Number.isNaN(n)) return '—';
  const s = n > 0 ? '+' : (n < 0 ? '−' : '');
  return s + Math.abs(n).toFixed(dec) + unit;
}

// Signed percentage-point delta (market-share moves).
export function fmtPP(n, dec = 2) {
  if (n === null || n === undefined || Number.isNaN(n)) return '—';
  const s = n > 0 ? '+' : (n < 0 ? '−' : '');
  return s + Math.abs(n).toFixed(dec) + ' pp';
}

// Turn a period key into a compact axis/label string.
//   monthly  "2026-05" -> "May'26"
//   quarterly "Q1FY26" -> "Q1FY26"
//   yearly    "FY26"   -> "FY26"
export function periodLabel(key, freq) {
  if (key == null) return '';
  if (freq === 'monthly') {
    const m = /^(\d{4})-(\d{2})$/.exec(key);
    if (m) return `${MONTHS[+m[2] - 1]}'${m[1].slice(2)}`;
  }
  return key;
}

// Longer, human label for tooltips.
export function periodLabelLong(key, freq) {
  if (key == null) return '';
  if (freq === 'monthly') {
    const m = /^(\d{4})-(\d{2})$/.exec(key);
    if (m) return `${MONTHS[+m[2] - 1]} ${m[1]}`;
  }
  return key;
}

// Prior-year period key for YoY (one fiscal year back), robust to the key format.
export function priorYearKey(key, freq) {
  if (key == null) return null;
  if (freq === 'monthly') {
    const m = /^(\d{4})-(\d{2})$/.exec(key);
    if (m) return `${(+m[1] - 1).toString().padStart(4, '0')}-${m[2]}`;
  } else if (freq === 'quarterly') {
    const m = /^Q(\d)FY(\d{2})$/.exec(key);
    if (m) return `Q${m[1]}FY${(+m[2] - 1).toString().padStart(2, '0')}`;
  } else if (freq === 'yearly') {
    const m = /^FY(\d{2})$/.exec(key);
    if (m) return `FY${(+m[1] - 1).toString().padStart(2, '0')}`;
  }
  return null;
}
