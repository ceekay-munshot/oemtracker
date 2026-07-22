// ui.js — tiny DOM helpers and shared UI atoms (segmented controls, chips, empty states).

export function el(tag, attrs = {}, children = []) {
  const n = document.createElement(tag);
  for (const k in attrs) {
    const v = attrs[k];
    if (k === 'class') n.className = v;
    else if (k === 'html') n.innerHTML = v;
    else if (k === 'text') n.textContent = v;
    else if (k === 'style' && typeof v === 'object') Object.assign(n.style, v);
    else if (k.startsWith('on') && typeof v === 'function') n.addEventListener(k.slice(2), v);
    else if (v === true) n.setAttribute(k, '');
    else if (v !== false && v != null) n.setAttribute(k, v);
  }
  const kids = Array.isArray(children) ? children : [children];
  for (const c of kids) { if (c == null) continue; n.appendChild(typeof c === 'string' ? document.createTextNode(c) : c); }
  return n;
}

export function clearNode(n) { while (n.firstChild) n.removeChild(n.firstChild); }

// Segmented mini-toggle. options:[{v,label,disabled?}]. Returns the element.
export function seg(options, value, onChange) {
  const wrap = el('div', { class: 'seg' });
  for (const o of options) {
    const b = el('button', {
      class: o.v === value ? 'on' : '', text: o.label,
      disabled: !!o.disabled,
      onclick: () => { if (o.v !== value && !o.disabled) onChange(o.v); },
    });
    wrap.appendChild(b);
  }
  return wrap;
}

export function chip(text, kind = '') {
  return el('span', { class: 'chip ' + kind, text });
}

export function sourceTag(source) {
  const label = source === 'siam' ? 'SIAM' : 'Internal DB';
  return el('span', { class: 'src-tag ' + source, text: label, title: source === 'siam'
    ? 'Society of Indian Automobile Manufacturers' : 'Internal OEM database (Spark)' });
}

const EXCEL_ICO = `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><path d="M14 2v6h6"/><path d="M9.5 12l2.5 3.5L14.5 12"/></svg>`;

export function exportBtn(onClick) {
  return el('button', { class: 'icon-btn', title: 'Export to Excel', html: EXCEL_ICO + '<span>Excel</span>', onclick: onClick });
}

export function emptyState(title = 'No data for this selection', hint = 'Try a different metric, frequency, or entity set.') {
  return el('div', { class: 'empty' }, [
    el('div', { html: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"><path d="M3 3v18h18"/><path d="M7 14l4-4 3 3 5-6" stroke-dasharray="2 2"/></svg>` }),
    el('div', { class: 'et', text: title }),
    el('div', { class: 'eh', text: hint }),
  ]);
}

// Provisional note line (shown under charts whose latest points are provisional).
export function provNote(periods) {
  if (!periods || !periods.length) return null;
  return el('div', { class: 'note' }, [
    el('span', { class: 'prov-mark', text: '◐' }),
    el('span', { text: `Latest ${periods.length === 1 ? 'period' : periods.length + ' periods'} provisional (subject to revision / late reporting).` }),
  ]);
}
