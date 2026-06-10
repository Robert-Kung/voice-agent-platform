## ADDED Requirements

### Requirement: Cost computed from selected model

Cost estimation SHALL derive rates from the model actually selected by the session's profile. When the selected model name is available, the runtime SHALL look it up directly in the rate table; only when unavailable SHALL it fall back to fuzzy matching on the model name reported in usage metrics.

#### Scenario: Pipeline cost uses profile-selected LLM rate
- **WHEN** a pipeline session ran with a profile-selected LLM whose rate is in the table
- **THEN** the LLM cost is computed from that model's per-token rate, not a guessed default

#### Scenario: Realtime cost uses profile-selected Gemini Live rate
- **WHEN** a realtime session ran with a specific Gemini Live model variant
- **THEN** the realtime cost uses that variant's rate when present in the table, falling back to the realtime default rate otherwise

### Requirement: Rate table extensible for new providers

The cost rate tables SHALL support adding new LLM / STT / TTS provider and model entries in one place, covering the providers exposed by the provider runtime.

#### Scenario: New TTS provider rate is honored
- **WHEN** a new TTS provider rate is added to the rate table and a session uses that provider
- **THEN** the TTS cost is computed from the new rate entry

### Requirement: Unknown model marked incomplete

When a session uses a model with no matching rate-table entry, cost estimation SHALL mark the result as incomplete rather than emitting an incorrect estimate.

#### Scenario: Unknown LLM yields incomplete flag
- **WHEN** a pipeline session used an LLM model absent from the rate table
- **THEN** the cost result sets `incomplete=True` and omits a fabricated LLM cost figure

#### Scenario: Known models yield complete cost
- **WHEN** all of a session's models have rate-table entries
- **THEN** the cost result reports `incomplete=False` with a total USD figure
