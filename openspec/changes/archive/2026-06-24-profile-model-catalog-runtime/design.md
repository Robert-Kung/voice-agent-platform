## Context

The prior change (`profile-editor-model-voice-ux`) delivered the stack UI but was constrained to "zero backend runtime change", forcing three stopgaps: (1) pipeline provider/model came from a tiny hardcoded `FALLBACK_MODEL_CATALOG` / cost-table-derived list; (2) pipeline voice was assumed encoded in the TTS model id (`models.tts.model`), because `runtime/providers.py:_build_one_tts` passes only `model`/`language`/`options` to `inference.TTS`; (3) Google could only run `via:inference` in pipeline (`_build_one_llm` raises for any non-inference provider; `via:direct` google is realtime-only).

We deploy on LiveKit Cloud, so the LiveKit Inference gateway catalog is the runnable set. Research (docs.livekit.io/agents/models/inference and /tts, 2026-06) established: a large enumerable provider/model list across LLM/STT/TTS; **TTS voice is a separate parameter** (`model="cartesia/sonic-3", voice="<id>"`) with a ~24-entry suggested-voices table and custom cloning; and a model-id namespace (`gemini/2.5-flash`, `scribe-v2-realtime`) that differs from our current working strings (`google/gemini-3.1-flash-lite`, `scribe_v2_realtime`). The read-only `GET /api/model-defaults` endpoint and the shared `backend-model-constants.json` fixture (checked from pytest + vitest) already exist and are the extension points.

## Goals / Non-Goals

**Goals:**
- Provider AND model are selectable dropdowns sourced from a curated backend catalog of LiveKit Inference models; never hand-typed for the common case (free-form remains as an escape hatch for cloned/custom ids).
- A first-class voice picker bound to a separate `models.tts.voice` field, surfaced from per-provider suggested voices, with the runtime actually applying it.
- A per-spec `via:inference`/`via:direct` toggle for Google, with the runtime building the direct path.
- All LiveKit models selectable; unpriced ones flagged, not hidden or blocked.
- Verify the catalog's model-id strings against the live LiveKit Cloud project before committing them; keep cost-rate keys aligned to the accepted strings.

**Non-Goals:**
- Per-node (graph) per-model UI; variables/data-collection UI; sample playback/audition.
- Non-LiveKit-Inference arbitrary provider endpoints.
- Auto-discovery of the catalog from a LiveKit API (none is public; the catalog is curated).

## Decisions

### D1. Catalog is a curated backend constant, served by the existing endpoint (not live-fetched)
LiveKit exposes no public "list models" API; the docs are static tables. We maintain the provider/model lists and the per-provider suggested-voice lists as import-light constants in `runtime/constants.py`, surfaced by `routes_model_defaults.build_model_catalog()`, and mirror the stable core into `backend-model-constants.json` for the cross-language contract test. Frontend consumes the endpoint at runtime with the embedded fallback. Alternative (live fetch) rejected: no source of truth to fetch from, and it would add a runtime dependency for a list that changes rarely.

### D2. Model-id strings are verified against the live LiveKit Cloud project before commit
The docs and our working defaults disagree on namespace (`gemini/2.5-flash` vs `google/gemini-3.1-flash-lite`; dashes vs underscores). Our current strings demonstrably run, so the catalog MUST be validated against the actual gateway (test each candidate id through `inference.*` against our project, or confirm via the SDK's accepted set) and the cost-table keys aligned to whatever the runtime accepts. The catalog ships only ids confirmed runnable. This is the single highest-risk task and gates the rest.

**Confirmation decays — so verification must be reproducible, not one-time, AND the runtime must not depend on it.** Two backstops (added after autoplan review F2/C1):
1. A **network-gated pytest** (skipped without `LIVEKIT_*` creds) instantiates `inference.LLM/STT/TTS` for every catalog id and asserts construction/handshake; runs in CI/pre-deploy so a renamed/deprecated gateway id fails the build instead of 422-ing a live SIP call.
2. A **runtime preflight fallback**: the pipeline resolver defines a known-good safe model per kind; if a pinned pipeline spec fails to build, it degrades to the safe chain with a loud warning rather than dropping the call. SIP has no `FallbackAdapter` net for a single pinned spec, so this is the actual mitigation for "a wrong id has no fallback" — the contract test (FE==BE==fixture) does not check the gateway and is theater against this specific risk.

### D3. Voice is a separate `models.tts.voice` field; runtime passes it through (corrects v1)
Pipeline voice moves out of the model id into `models.tts.voice`. `_build_one_tts` passes `voice=` to `inference.TTS` when present. The editor shows a per-provider suggested-voice dropdown plus free-form for custom/cloned ids. This is a deliberate correction of the v1 model-id-encoded mapping; old profiles that encoded a voice in the model id keep working (the id is still a valid model string), and the UI migrates them lazily (shows the encoded value, lets the user re-pick into the voice field). Realtime voice is unchanged (`models.realtime.voice`).

### D4. `via:direct` for Google is a per-spec toggle wired in the runtime build path
`_build_one_llm` gains a google-direct branch (provider plugin + `GOOGLE_API_KEY`); `_build_one_tts` likewise if google TTS direct is offered. The spec shape (`{provider, model, via, ...}`) already carries `via`; only the build dispatch and the import-light validator's direct-support matrix change. The UI exposes the toggle only for providers that actually have a direct build path (Google), mirroring the realtime "Gemini-only" discipline.

**Build-call details (autoplan review C3/M3):**
- `inference.LLM` takes `{provider}/{model}` (`_model_id(spec)`); `google.LLM` (direct) takes a **bare** model name. The direct branch MUST use `spec["model"]`, not `_model_id(spec)`, or the Gemini API rejects the build.
- `ResolvedComponents.model_names` keeps recording the canonical `provider/model` form regardless of `via`, and cost-table keys stay `provider/model` — so cost matching survives the direct path. Do NOT migrate cost keys to a bare/`gemini/…` namespace.
- The validator's direct-support is a `(kind, provider)` matrix, not a per-kind `else: raise`: `DIRECT_BUILDABLE = {("stt","deepgram"), ("llm","google")}` in `constants.py`, consumed by `normalize_spec` AND asserted against `providers.build_*` dispatch by a test. `tts via:direct` stays rejected (the realtime `model-provider-runtime` "direct plugin" wording is v1-inaccurate for pipeline TTS — voice passes only to `inference.TTS`).
- Image bloat resolved: `from livekit.plugins import google` is already imported in `providers.py` for realtime, so google-direct LLM adds no new dependency.

### D7. Priced flag is per-model for LLM, per-provider for STT/TTS (documented approximation)
`LLM_RATES` is keyed `provider/model`; `STT_RATES`/`TTS_RATES` are keyed by **provider only**. There is no per-model STT/TTS rate data to flag against, so the catalog's `priced` flag is **model-granular for LLM and provider-granular for STT/TTS**, and the UI/spec say so explicitly (autoplan review F1/H4). A green "priced" badge on an STT/TTS model means "this provider is priced," not "this exact model's rate is known." Restructuring STT/TTS tables to `provider/model` keys is deferred (no rate data to populate them). The catalog is now the authoritative runnable set and cost **annotates** it with the flag — `routes_model_defaults._llm_options()` MUST stop deriving the LLM list from `LLM_RATES` keys (that derivation cannot express unpriced-inclusive models). The namespace is ONE value across cost / catalog / runtime `_model_id` / FE fixture; it changes atomically, guarded by an assertion test (every catalog llm id → `_match_llm_rate ≠ None OR flagged unpriced`).

### D5. Unpriced models are offered and flagged, not gated
The catalog marks each model with whether `db/cost.py` has a rate. The UI shows a "cost estimate unavailable" badge; selection and save proceed. Runtime cost already marks unknown models incomplete (`multi-model-cost`), so this is purely an honesty affordance. We add rate entries for newly-offered models where the rate is known, but do not block the catalog on pricing completeness.

### D6. Backend validator guarantees spec SHAPE, not runnability; runtime preflight catches bad ids
Consistent with the prior change: the import-light validator (`validate_models_block`) is extended to accept `tts.voice` (and add `voice` to the `reserved` options keys so a hand-edited `options.voice` doesn't collide with the explicit kwarg) and google `via:direct`, and remains the save-time gate. **But the validator does NOT validate model-id strings against the catalog** — doing so would break the free-form custom/cloned-id escape hatch the UI deliberately keeps. So the `profile-model-config` invariant is downgraded (autoplan review C2) from "no accepted profile crashes at session start" to "the validator guarantees shape; runnability of a free-form id is caught by D2's runtime preflight fallback, not the validator." The frontend dropdowns are an input affordance; a hand-edited/YAML profile with a bad id passes save but degrades to the safe chain at runtime rather than dropping the call.

### D8. UI states & layout (pipeline TTS block) — autoplan design review C1/C2/H3/H4/H6/M7-M10
The frontend half was field-bindings without a layout. Concretely:
- **Controls stack vertically** in the 40% panel (provider → model → voice → via-toggle → badge); 3-4 inline controls do not fit. Model dropdown options filter to the selected provider; voice dropdown options = provider's suggested voices + a "Custom…" sentinel revealing a free-text input.
- **Provider-change reset rule (required):** changing provider resets model to that provider's catalog default and resets voice to that provider's default voice. No model/voice string survives a provider change (today's `SpecField.onChange` keeps the old model → produces invalid `elevenlabs/sonic-3`). vitest covers it.
- **via toggle:** small segmented control rendered below the model row, only when `catalog.directCapable.includes(provider)`. Human labels, not raw `via:` strings — "透過 LiveKit 閘道（免金鑰）" / "用自己的 GOOGLE_API_KEY".
- **Unpriced badge:** rendered **below the field after selection** (native `<select>` can't style individual `<option>`s). Any cost chip/estimate elsewhere must read "estimate incomplete" for an unpriced selection, never a misleading number.
- **Legacy voice-in-model-id:** the v1 encoding format is `provider/model:<voice-id>` (see `DEFAULT_PIPELINE_TTS` cartesia `sonic-3:9626c31c-...`). On loading a legacy-shaped TTS spec, show an inline notice and pre-fill the parsed voice into the voice field as a non-destructive suggestion (don't rewrite until save).
- **Voice-only round-trip:** `specHasValue`/`pruneModels` must treat `voice` as a meaningful value, or a re-picked voice on an inherited-model TTS spec is silently dropped on save (autoplan review H2). vitest covers `{ tts: { voice: 'x' } }` survives prune.
- **Loading/error/empty:** dropdowns render from the embedded fallback immediately (no empty flash), swap to fresh on load without resetting the user's selection; a pinned value stays selectable even if absent from whichever catalog loaded. A provider with zero suggested voices renders the voice control as free-text directly (no empty dropdown).
- **Realtime vs pipeline voice asymmetry** (realtime = free-form+datalist, pipeline = dropdown+custom) is accepted; one design note records why rather than unifying in v1.

## Risks / Trade-offs

- **[Model-id namespace mismatch — catalog ships an id the gateway rejects]** → D2: verify every candidate id against the live project before commit; ship only confirmed ids; align cost keys. A wrong id has no fallback on a SIP call, so this is gating.
- **[Offering unpriced models silently degrades cost estimates]** → D5: explicit "cost estimate unavailable" flag in the UI + existing incomplete-cost marking; no silent zero.
- **[`via:direct` expands dependency + API-key surface]** → only wire Google direct (key already in `.env`, plugin already vendored for realtime); do not open a general direct registry. Confirm no image bloat.
- **[v1 voice-in-model-id profiles]** → keep accepting the encoded id as a valid model string; surface it and let the user re-pick into `models.tts.voice`; no destructive migration.
- **[Frontend catalog drift]** → shared fixture contract test on both sides, same discipline as the graph validator and the prior change.

## Migration Plan

- Mostly additive: new `models.tts.voice` field + google `via:direct` need no DB migration (free-form config; absent fields fall back).
- Deploy: rebuild api (runtime + endpoint + cost) and frontend; `docker compose up -d --build`.
- Rollback: revert; old profiles unaffected. A profile that pinned a new catalog id or `tts.voice` while the new code is live would, after rollback, fall back to defaults for the unknown field (non-breaking) — except a pinned google `via:direct` pipeline spec, which old code rejects; note this in the release as the one non-trivial rollback edge.
- Verify: pytest (runtime build paths for google-direct + voice passthrough; catalog/cost parity), vitest (expanded round-trip + contract), and browser QA (dropdowns, voice picker round-trip, direct-key toggle, unpriced flag, graph×realtime still gated).

## Open Questions

- Which exact LiveKit Inference model-id namespace does our Cloud project accept (`provider/model` with our current strings, or the docs' `gemini/…` form, or both)? Resolved in D2's verification task before the catalog is committed.
- ~~Does `inference.TTS` accept `voice=` directly?~~ **Resolved (autoplan review M1):** installed `livekit-agents` 1.5.2 `inference.TTS.__init__` accepts `voice: NotGivenOr[str]`. Add a pin-test asserting this so an SDK upgrade regression fails loudly.
- Should Google `via:direct` also cover TTS, or LLM only in v1? **Resolved: LLM only.** `_build_one_tts` keeps rejecting `via:direct`; the `model-provider-runtime` "direct plugin" voice wording is corrected to "inference.TTS only" for v1.
- ~~Image bloat from livekit-plugins-google?~~ **Resolved (M5):** plugin already imported for realtime; no new dependency.

## Autoplan review outcome (2026-06-22)

Scope decision: **combined / full catalog** (user confirmed at gate, against the CEO voice's split recommendation). Full review (CEO + Design + Eng, Claude-subagent-only — Codex unavailable) in `~/.gstack/projects/Robert-Kung-first-livekit/main-profile-model-catalog-runtime-autoplan-review.md`; test plan in the sibling `-test-plan.md`. Must-fix findings folded into D2/D4/D6/D7/D8 above and tasks.md §7.
