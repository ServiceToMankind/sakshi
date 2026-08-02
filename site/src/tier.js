// Source epistemic tier (§3) — the FRONTEND MIRROR of pipeline/provenance.SOURCE_TIER.
// A parity test asserts the two maps match so a tier reads the same on the site and in the
// pipeline. Derived only from each source's public source_type — never victim data.
//
//   1 court        — the record (CNR / status / pendency / names)
//   2 legal_press  — court proceedings reported by a legal outlet, with a court citation
//   3 news_article / press_release — incident/arrest/FIR reports; not yet a court record
//   4 live_blog    — rolling coverage (quarantine only)

export const SOURCE_TIER = {
  court: 1,
  legal_press: 2,
  news_article: 3,
  press_release: 3,
  live_blog: 4,
};

/**
 * The record's strongest (lowest) source tier. Uses sources[] when present (case detail);
 * falls back to the precomputed `source_tier` (the recent-feed card has no sources[]); else
 * 3 (media-grade).
 */
export function recordTier(record) {
  if (Array.isArray(record.sources) && record.sources.length) {
    return Math.min(...record.sources.map((s) => SOURCE_TIER[s && s.source_type] ?? 3));
  }
  return typeof record.source_tier === 'number' ? record.source_tier : 3;
}

/** True if the case is traced to the judicial record (a tier-1 court source). */
export function hasCourtSource(record) {
  if (Array.isArray(record.sources) && record.sources.length) {
    return record.sources.some((s) => s && s.source_type === 'court');
  }
  return record.source_tier === 1;
}
