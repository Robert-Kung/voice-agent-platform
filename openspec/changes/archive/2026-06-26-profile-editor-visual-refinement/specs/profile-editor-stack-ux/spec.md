## MODIFIED Requirements

### Requirement: Global-as-base-layer editor information architecture

The profile editor SHALL present global configuration (`global_prompt`, persona/identity, QA, service hours, global tools, and the model/voice stack) as an **always-on base layer that applies to the whole agent in both `prompt` and `graph` modes**, and SHALL present the graph as an **optional branching layer layered on top of global** rather than an alternative to it. This framing SHALL be carried by a concrete layout affordance (e.g. a persistent labeled "global / applies everywhere" container, or the graph canvas rendered inside a labeled "branching layer" frame), **not by copy alone**, so the layout does not visually teach the opposite. The model/voice stack settings SHALL be reachable from the header Stack summary chip, which SHALL present an explicit editable affordance (distinct from a passive status badge) and on activation SHALL open a **dedicated full-width Model & Voice view** giving the model/voice controls room for a multi-column layout, instead of a constrained center modal — so the highest-stakes settings are neither demoted to a low-discoverability collapsed accordion slot nor cramped into an overflowing modal. The full-width view SHALL preserve the in-progress unsaved draft (it does not unmount the editor form state) and SHALL provide an explicit way back to the editor. Global configuration SHALL be preserved unchanged across `prompt`↔`graph` conversion and revert.

#### Scenario: Global config presented as always-on base layer

- **WHEN** the user views the editor in either `prompt` or `graph` mode
- **THEN** the global settings (global prompt, identity, QA, hours, global tools, model/voice stack) are presented via a persistent layout affordance as applying to the whole agent regardless of mode, and the graph is presented as an optional branching layer on top — not as a replacement for global

#### Scenario: Stack chip opens the full-width Model & Voice view

- **WHEN** the user clicks the header Stack summary chip
- **THEN** the editor swaps to a dedicated full-width Model & Voice view showing the engine-mode selection and the per-component (TTS / LLM / STT) controls in a multi-column layout, without opening a center modal and without hunting through collapsed right-panel accordion sections

#### Scenario: Stack chip reads as editable, not as a status badge

- **WHEN** the user looks at the header
- **THEN** the Stack chip is visually distinguished as an interactive entry point (e.g. accent styling plus a settings affordance and hover state), so it does not read as the passive language/status pill next to it

#### Scenario: Full-width view preserves unsaved edits

- **WHEN** the user has unsaved edits, opens the full-width Model & Voice view, and returns to the editor
- **THEN** all unsaved edits and dirty state are preserved (the view swap does not unmount the editor form)

#### Scenario: Global config survives mode conversion

- **WHEN** the user converts a profile to graph mode and later reverts to prompt mode
- **THEN** the global configuration (global prompt, identity, QA, hours, global tools, model/voice stack) is unchanged by the conversion and revert
