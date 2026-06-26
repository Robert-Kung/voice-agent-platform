## ADDED Requirements

### Requirement: Type scale with three legible tiers

The profile editor SHALL use a type scale with at least three distinct tiers — section title, body/field value, and meta/badge — so visual hierarchy is legible, instead of collapsing labels, help text, values, and badges into a single micro range (`text-xs`/`text-[11px]`/`text-[10px]`). Section titles SHALL be visually heavier than body text (e.g. `text-sm`/semibold), body and field values SHALL sit at a readable body size, and the smallest tier SHALL be reserved for badges and incidental meta. Changing the type scale SHALL NOT alter the data written for any field.

#### Scenario: Section title outranks body and badge

- **WHEN** the user views any right-panel section or the Model & Voice view
- **THEN** the section title is visibly larger/heavier than its body text, and badges/meta use the smallest tier — producing a clear title → body → meta hierarchy rather than a flat micro-type block

#### Scenario: Type scale change is presentation-only

- **WHEN** the type scale is applied
- **THEN** no field's persisted value or `config` shape changes as a result

### Requirement: Header strategy and engine axes are visually grouped

The editor header SHALL visually distinguish the two orthogonal-but-coupled mode axes — `editor_mode` (Prompt / Graph, the strategy source) and `models.mode` (the runtime engine, surfaced via the Stack chip) — using grouping affordances (e.g. short group labels for "策略" / "引擎"), so a first-time viewer can tell they are two different controls in the resting state, not only after a reactive confirmation dialog fires. This grouping SHALL NOT change the existing save-time confirmation behavior for mode switches.

#### Scenario: Two mode axes are distinguishable at rest

- **WHEN** the user views the header
- **THEN** the strategy control (`editor_mode`) and the engine control (`models.mode` / Stack chip) are presented as two labeled groups, making clear they are distinct axes (with graph requiring pipeline as the coupling)

#### Scenario: Grouping does not change confirmation behavior

- **WHEN** the user changes `editor_mode` or `models.mode` and saves
- **THEN** the existing strategy-change confirmation dialog still fires as before (the grouping is presentation-only)

### Requirement: Welcome fields reflect the active engine mode

The editor SHALL present the two welcome fields — Welcome Message (spoken verbatim in pipeline) and Welcome Instructions (generated in realtime) — according to the current `models.mode`, emphasizing the field that takes effect and de-emphasizing (collapsing) the inactive one, instead of showing both at equal weight. The inactive field SHALL remain expandable and editable, and its value SHALL be preserved (never cleared) so it round-trips and is ready when the engine mode changes.

#### Scenario: Active welcome field is emphasized

- **WHEN** the profile's `models.mode` is realtime (resp. pipeline)
- **THEN** Welcome Instructions (resp. Welcome Message) is shown as the active field, and the other is de-emphasized/collapsed with a label explaining which mode it applies to

#### Scenario: Inactive welcome field is preserved and reachable

- **WHEN** the user expands the de-emphasized welcome field and edits it, or switches engine mode
- **THEN** the field is editable, its value is never cleared by the de-emphasis, and it round-trips through save/load

### Requirement: Dirty state is presented consistently across editor and list

The unsaved-changes (dirty) indicator SHALL be presented consistently between the profile editor header and the profiles list page, using the same badge treatment rather than divergent visual languages (e.g. a list-page badge versus a bare colored dot in the editor).

#### Scenario: Editor and list use the same dirty badge

- **WHEN** a profile has unsaved changes
- **THEN** both the editor header and the profiles list row indicate the dirty state with the same badge treatment
