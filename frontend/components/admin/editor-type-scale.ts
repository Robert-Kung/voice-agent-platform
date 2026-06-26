// Shared type-scale className constants for the profile editor (design D3).
// Three legible tiers — section title → body/field value → meta/badge — so the
// editor reads as a designed hierarchy, not a flat micro-type block. Only
// font-size / weight live here; spacing/padding stays at the callsites (D3).

/** Section / panel title — heavier than body so it outranks it. */
export const sectionTitle = 'text-sm font-semibold';
/** Field label — readable label tier above body inputs. */
export const fieldLabel = 'text-[13px] font-medium';
/** Body text, help copy, and input values. */
export const bodyText = 'text-sm';
/** Smallest tier — reserved for badges and incidental meta. */
export const badgeText = 'text-[10px]';
