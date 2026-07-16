// Severity labels derived from public charge sections — never from victim data.
//
// This is the FRONTEND MIRROR of pipeline/severity.py. Both import the SAME rules
// file (severity_rules.json), and this module reproduces the Python matching
// semantics EXACTLY so the two can never drift (CLAUDE.md §5):
//
//   - haystack(sections): upper-case + collapse internal whitespace of every
//     section, join with " | ", so "BNS 70(2)", "bns 70 (2)" and
//     "Section 70(2), BNS" all reduce to the same searchable string.
//   - severityLabel: the first rule (rules are MOST-SEVERE-FIRST) any of whose
//     UPPER-cased section substrings appears in the haystack wins; else null.
//   - isAggravated: the aggravated flag of that same first-matching rule.
//   - isRepeatOffender: any repeat/habitual-offender section substring appears.
//
// Charge codes (BNS/POCSO/IPC sections) are public court information; mapping them
// to a plain-language label is a projection of the CHARGES only — safe for every
// case, including a minor's (it adds no victim detail).

import rules from './severity_rules.json';

// (label, aggravated, [UPPER-cased section substrings]) — MOST SEVERE FIRST.
const SEVERITY_RULES = rules.rules.map((rule) => ({
  label: rule.label,
  aggravated: Boolean(rule.aggravated),
  needles: rule.sections.map((section) => section.toUpperCase()),
}));
const REPEAT_SECTIONS = rules.repeat_sections.map((section) => section.toUpperCase());

/**
 * Upper-case + space-normalise the sections into one searchable string. Mirrors
 * pipeline.severity._haystack: Python's str.split() (no args) drops empty tokens
 * and collapses runs of whitespace — reproduced here with /\s+/ + filter(Boolean).
 * A non-array input yields "" (a bare string is not a section list).
 */
function haystack(sections) {
  if (!Array.isArray(sections)) return '';
  return sections
    .map((section) => String(section).toUpperCase().split(/\s+/).filter(Boolean).join(' '))
    .join(' | ');
}

/**
 * The single most-severe plain-language label for the charges, or null.
 *
 * null means the sections matched no known rule (the card then falls back to the
 * coarse `category` label). Derived ONLY from the sections — never victim data.
 */
export function severityLabel(offenceSections) {
  const hay = haystack(offenceSections);
  if (!hay) return null;
  for (const rule of SEVERITY_RULES) {
    if (rule.needles.some((needle) => hay.includes(needle))) return rule.label;
  }
  return null;
}

/** True if the matched rule is an aggravated category (dark-red badge weight). */
export function isAggravated(offenceSections) {
  const hay = haystack(offenceSections);
  if (!hay) return false;
  for (const rule of SEVERITY_RULES) {
    if (rule.needles.some((needle) => hay.includes(needle))) return rule.aggravated;
  }
  return false;
}

/** True if a repeat/habitual-offender section is charged (a separate aggravating axis). */
export function isRepeatOffender(offenceSections) {
  const hay = haystack(offenceSections);
  return REPEAT_SECTIONS.some((needle) => hay.includes(needle));
}
