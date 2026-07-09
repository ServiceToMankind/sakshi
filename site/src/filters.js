// The Explore filter bar. Emits (key, value) changes; the Explore view folds
// those into the URL so every filter combination round-trips as a shareable link.

import { el } from './dom.js';
import { t } from './i18n/index.js';
import { statusLabel } from './format.js';
import { SORTS } from './state.js';

function debounce(fn, ms) {
  let timer;
  return (...args) => {
    clearTimeout(timer);
    timer = setTimeout(() => fn(...args), ms);
  };
}

function withAny(values, label) {
  return [
    { value: '', label: t('filter_all') },
    ...values.map((v) => ({ value: v, label: label(v) })),
  ];
}

function selectField(name, label, value, options, onChange) {
  const select = el(
    'select',
    { id: `f-${name}`, name, onchange: (e) => onChange(name, e.target.value) },
    options.map((o) =>
      el(
        'option',
        o.value === value ? { value: o.value, selected: true } : { value: o.value },
        o.label,
      ),
    ),
  );
  return el('label', { class: 'filter' }, [el('span', { class: 'filter__label' }, label), select]);
}

/**
 * @param {object} filters   current filter state
 * @param {{years:string[], districts:string[], statuses:string[]}} opts
 * @param {(key:string, value:string)=>void} onChange   '__clear__' resets all
 */
export function buildFilters(filters, opts, onChange) {
  const identity = (v) => v;
  const search = el('input', {
    type: 'search',
    id: 'f-q',
    name: 'q',
    value: filters.q,
    placeholder: t('filter_search'),
    'aria-label': t('filter_search'),
    oninput: debounce((e) => onChange('q', e.target.value), 250),
  });

  return el('form', { class: 'filters', role: 'search', onsubmit: (e) => e.preventDefault() }, [
    selectField(
      'activity',
      t('filter_activity'),
      filters.activity,
      [
        { value: '', label: t('filter_all') },
        { value: 'active', label: t('activity_active') },
        { value: 'closed', label: t('activity_closed') },
      ],
      onChange,
    ),
    selectField(
      'status',
      t('filter_status'),
      filters.status,
      withAny(opts.statuses, statusLabel),
      onChange,
    ),
    selectField('year', t('filter_year'), filters.year, withAny(opts.years, identity), onChange),
    selectField(
      'district',
      t('filter_district'),
      filters.district,
      withAny(opts.districts, identity),
      onChange,
    ),
    selectField(
      'minor',
      t('filter_minor'),
      filters.minor,
      [
        { value: '', label: t('filter_all') },
        { value: 'yes', label: t('minor_yes') },
        { value: 'no', label: t('minor_no') },
      ],
      onChange,
    ),
    selectField(
      'sort',
      t('filter_sort'),
      filters.sort,
      SORTS.map((s) => ({ value: s, label: t(`sort_${s}`) })),
      onChange,
    ),
    el('label', { class: 'filter filter--search' }, [
      el('span', { class: 'filter__label' }, t('filter_search')),
      search,
    ]),
    el(
      'button',
      {
        type: 'button',
        class: 'btn btn--ghost filter__clear',
        onclick: () => onChange('__clear__', ''),
      },
      t('filter_clear'),
    ),
  ]);
}
